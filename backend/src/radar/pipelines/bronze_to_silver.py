"""Pipeline incremental bronze (MongoDB) -> silver (Postgres).

Uso:
    python -m radar.pipelines.bronze_to_silver              # só o que é novo
    python -m radar.pipelines.bronze_to_silver --completo   # reprocessa toda a bronze

Como funciona:
1. lê a marca d'água (até onde a última execução chegou);
2. pede à bronze as versões que viraram a atual entre a marca e "agora - atraso";
3. transforma cada uma (`transformacao.py`) e grava entidades e rejeições;
4. faz commit a cada lote; no final grava a nova marca junto com o último lote.

Se o processo cair no meio, a marca não avança e a próxima execução relê o período.
Isso é seguro porque tudo é idempotente (upsert pela chave natural, rejeição única).
"""

import argparse
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import structlog
from pymongo import MongoClient

from radar.adapters.mongo.bronze import MongoBronzeRepository, MongoDoc
from radar.adapters.postgres.database import create_db_engine, create_session_factory
from radar.adapters.postgres.silver import SqlSilverUnitOfWork
from radar.config import Settings
from radar.domain.errors import DomainError
from radar.logging_setup import configure_logging
from radar.pipelines.transformacao import ContratacaoLimpa, transformar
from radar.ports.bronze import BronzeReader, BronzeVersion
from radar.ports.silver import MotivoRejeicao, Problema, Rejeicao, SilverUnitOfWork

PIPELINE = "bronze_to_silver"

log = structlog.get_logger()


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class RelatorioPipeline:
    lidas: int = 0
    gravadas: int = 0
    rejeitadas: int = 0  # contratações inteiras
    itens_gravados: int = 0
    itens_rejeitados: int = 0
    inconsistentes: int = 0  # total da contratação diverge da soma dos itens
    duracao_segundos: float = 0.0
    marca: datetime | None = None


class BronzeToSilverPipeline:
    def __init__(
        self,
        bronze: BronzeReader,
        silver: SilverUnitOfWork,
        *,
        tamanho_lote: int = 100,
        # a ingestão carimba `vigente_desde` um instante antes de gravar: uma versão com
        # horário T pode ficar visível só depois de T. Ler só até "agora - atraso" garante
        # que nada com horário anterior à marca ainda esteja a caminho.
        atraso_seguranca: timedelta = timedelta(minutes=1),
        clock: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._bronze = bronze
        self._silver = silver
        self._tamanho_lote = tamanho_lote
        self._atraso = atraso_seguranca
        self._clock = clock
        self._monotonic = monotonic

    def run(self, *, completo: bool = False) -> RelatorioPipeline:
        inicio = self._monotonic()
        report = RelatorioPipeline()
        depois_de = None if completo else self._silver.watermarks.get(PIPELINE)
        ate = self._clock() - self._atraso
        try:
            versoes = self._bronze.versions_between(depois_de, ate)
            for numero, versao in enumerate(versoes, start=1):
                self._processar(versao, report)
                if numero % self._tamanho_lote == 0:
                    self._silver.commit()  # progresso salvo; a marca só no final
            self._silver.watermarks.set(PIPELINE, ate)
            self._silver.commit()
        except Exception:
            # falha inesperada (banco caiu, bug): desfaz o lote atual e deixa o erro subir
            self._silver.rollback()
            raise
        report.marca = ate
        report.duracao_segundos = round(self._monotonic() - inicio, 3)
        return report

    # ------------------------------------------------------------------ uma versão

    def _processar(self, versao: BronzeVersion, report: RelatorioPipeline) -> None:
        report.lidas += 1
        resultado = transformar(versao)
        if resultado.limpa is None:
            report.rejeitadas += 1  # a única rejeição é a da contratação inteira
        else:
            self._gravar(versao, resultado.limpa, report)
            report.itens_rejeitados += len(resultado.rejeicoes)  # aqui, todas são de itens
        for rejeicao in resultado.rejeicoes:
            self._rejeitar(rejeicao)

    def _gravar(
        self, versao: BronzeVersion, limpa: ContratacaoLimpa, report: RelatorioPipeline
    ) -> None:
        try:
            self._silver.orgaos.upsert(limpa.orgao)
            for fornecedor in limpa.fornecedores:
                self._silver.fornecedores.upsert(fornecedor)
            self._silver.contratacoes.upsert(limpa.contratacao)
        except DomainError as exc:
            # o banco recusou algo que passou pela validação: vira rejeição, lote segue
            report.rejeitadas += 1
            self._rejeitar(
                Rejeicao(
                    numero_controle_pncp=versao.numero_controle_pncp,
                    bronze_hash=versao.hash,
                    motivo=MotivoRejeicao.PERSISTENCIA,
                    problemas=(Problema("contratacao", str(exc)),),
                )
            )
            return
        report.gravadas += 1
        report.itens_gravados += len(limpa.contratacao.itens)
        report.inconsistentes += limpa.inconsistente

    def _rejeitar(self, rejeicao: Rejeicao) -> None:
        log.warning(
            "registro_rejeitado",
            numero_controle_pncp=rejeicao.numero_controle_pncp,
            numero_item=rejeicao.numero_item,
            motivo=rejeicao.motivo.value,
            problemas=[f"{p.campo}: {p.erro}" for p in rejeicao.problemas],
        )
        self._silver.rejeicoes.add(rejeicao)


# ------------------------------------------------------------------ linha de comando
# Raiz de composição: o único trecho deste módulo que conhece Mongo e Postgres.


class PipelineRunner(Protocol):
    def run(self, *, completo: bool = False) -> RelatorioPipeline: ...


PipelineFactory = Callable[[Settings], tuple[PipelineRunner, Callable[[], None]]]


def build_pipeline(settings: Settings) -> tuple[PipelineRunner, Callable[[], None]]:
    """Cria o pipeline com as dependências reais e uma função que fecha as conexões."""
    mongo: MongoClient[MongoDoc] = MongoClient(settings.mongo_url, tz_aware=True)
    bronze = MongoBronzeRepository(mongo[settings.mongo_db])
    bronze.ensure_indexes()  # garante o índice (e o backfill) de vigente_desde
    engine = create_db_engine(settings)
    session = create_session_factory(engine)()

    def close() -> None:
        session.close()
        engine.dispose()
        mongo.close()

    return BronzeToSilverPipeline(bronze, SqlSilverUnitOfWork(session)), close


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    pipeline_factory: PipelineFactory = build_pipeline,
) -> int:
    settings = settings or Settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    parser = argparse.ArgumentParser(
        prog="python -m radar.pipelines.bronze_to_silver",
        description="Pipeline incremental bronze (MongoDB) -> silver (Postgres).",
    )
    parser.add_argument(
        "--completo", action="store_true", help="ignora a marca d'água e reprocessa tudo"
    )
    args = parser.parse_args(argv)

    pipeline, close = pipeline_factory(settings)
    log.info("pipeline_iniciado", pipeline=PIPELINE, completo=args.completo)
    try:
        report = pipeline.run(completo=args.completo)
    finally:
        close()
    log.info(
        "pipeline_concluido",
        pipeline=PIPELINE,
        lidas=report.lidas,
        gravadas=report.gravadas,
        rejeitadas=report.rejeitadas,
        itens_gravados=report.itens_gravados,
        itens_rejeitados=report.itens_rejeitados,
        inconsistentes=report.inconsistentes,
        duracao_s=report.duracao_segundos,
        marca=report.marca.isoformat() if report.marca else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
