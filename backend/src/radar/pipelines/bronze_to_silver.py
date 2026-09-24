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

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog

from radar.domain.errors import DomainError
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
