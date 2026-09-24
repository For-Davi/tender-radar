"""Worker de ingestão do PNCP.

Uso:
    python -m radar.workers.ingestao                 # loop: a cada N minutos, últimos D dias
    python -m radar.workers.ingestao --once          # uma execução e termina
    python -m radar.workers.ingestao --data-inicial 2025-03-01 --data-final 2025-03-31
                                                     # backfill de um período (uma execução)

Este módulo é a "raiz de composição": o único lugar que conhece as implementações
concretas (httpx, Mongo, RabbitMQ, disco) e as injeta no serviço.
"""

import argparse
import signal
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from types import FrameType
from zoneinfo import ZoneInfo

import httpx
import structlog
from pymongo import MongoClient

from radar.adapters.mongo.bronze import MongoBronzeRepository, MongoDoc
from radar.adapters.pncp.client import PncpClient
from radar.adapters.rabbitmq.publisher import RabbitMqPublisher, connection_parameters
from radar.adapters.storage.local import LocalDocumentStorage
from radar.config import Settings
from radar.logging_setup import configure_logging
from radar.services.ingestao import IngestaoService, JanelaIngestao

# As datas do PNCP são do horário de Brasília: "hoje" precisa ser o dia de lá
BRASILIA = ZoneInfo("America/Sao_Paulo")
USER_AGENT = "radar-licitacoes/0.1 (projeto de estudo; github.com/For-Davi/tender-radar)"

log = structlog.get_logger()

ServiceFactory = Callable[[Settings], tuple[IngestaoService, Callable[[], None]]]


@dataclass(frozen=True, slots=True)
class Args:
    once: bool
    data_inicial: date | None
    data_final: date | None


def parse_args(argv: Sequence[str] | None) -> Args:
    parser = argparse.ArgumentParser(
        prog="python -m radar.workers.ingestao", description="Ingestão do PNCP para a bronze."
    )
    parser.add_argument("--once", action="store_true", help="roda uma vez e termina")
    parser.add_argument("--data-inicial", type=date.fromisoformat, help="AAAA-MM-DD (backfill)")
    parser.add_argument("--data-final", type=date.fromisoformat, help="AAAA-MM-DD (backfill)")
    ns = parser.parse_args(argv)

    if (ns.data_inicial is None) != (ns.data_final is None):
        parser.error("--data-inicial e --data-final devem ser informadas juntas")
    if ns.data_inicial is not None and ns.data_inicial > ns.data_final:
        parser.error("--data-inicial não pode ser depois de --data-final")
    backfill = ns.data_inicial is not None
    # backfill é sempre uma execução só: repetir o mesmo período em loop não faz sentido
    return Args(once=ns.once or backfill, data_inicial=ns.data_inicial, data_final=ns.data_final)


def build_janela(args: Args, settings: Settings, hoje: date) -> JanelaIngestao:
    if args.data_inicial is not None and args.data_final is not None:
        inicio, fim = args.data_inicial, args.data_final
    else:
        # janela de D dias terminando hoje: com D=2, pega ontem e hoje (cobre publicações tardias)
        inicio, fim = hoje - timedelta(days=settings.ingestao_janela_dias - 1), hoje
    return JanelaIngestao(
        data_inicial=inicio,
        data_final=fim,
        modalidades=tuple(settings.ingestao_modalidades),
        ufs=tuple(settings.ingestao_ufs),
    )


def build_service(settings: Settings) -> tuple[IngestaoService, Callable[[], None]]:
    """Cria as dependências reais. Devolve o serviço e uma função que fecha as conexões."""
    http = httpx.Client(timeout=settings.pncp_timeout_seconds, headers={"User-Agent": USER_AGENT})
    source = PncpClient(
        http,
        consulta_url=settings.pncp_consulta_url,
        api_url=settings.pncp_api_url,
        max_attempts=settings.pncp_max_attempts,
        min_interval_seconds=settings.pncp_min_interval_seconds,
        max_download_bytes=settings.documento_max_bytes,
    )
    mongo: MongoClient[MongoDoc] = MongoClient(settings.mongo_url, tz_aware=True)
    bronze = MongoBronzeRepository(mongo[settings.mongo_db])
    bronze.ensure_indexes()
    publisher = RabbitMqPublisher(
        connection_parameters(
            settings.rabbitmq_host,
            settings.rabbitmq_port,
            settings.rabbitmq_user,
            settings.rabbitmq_password.get_secret_value(),
        )
    )
    storage = LocalDocumentStorage(settings.storage_dir)

    def close() -> None:
        publisher.close()
        mongo.close()
        http.close()

    return IngestaoService(source, bronze, storage, publisher), close


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    service_factory: ServiceFactory = build_service,
    today: Callable[[], date] = lambda: datetime.now(BRASILIA).date(),
) -> int:
    settings = settings or Settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    args = parse_args(argv)
    service, close = service_factory(settings)

    # SIGTERM (docker stop) e Ctrl+C: termina a execução atual e sai sem começar outra
    stop = threading.Event()

    def _request_stop(signum: int, _frame: FrameType | None) -> None:
        log.info("ingestao_parando", sinal=signal.Signals(signum).name)
        stop.set()

    previous = {sig: signal.signal(sig, _request_stop) for sig in (signal.SIGTERM, signal.SIGINT)}

    try:
        while not stop.is_set():
            janela = build_janela(args, settings, today())
            log.info(
                "ingestao_iniciada",
                data_inicial=janela.data_inicial.isoformat(),
                data_final=janela.data_final.isoformat(),
                modalidades=list(janela.modalidades),
                ufs=list(janela.ufs),
            )
            started = time.monotonic()
            report = service.run(janela)
            log.info(
                "ingestao_concluida",
                duracao_s=round(time.monotonic() - started, 1),
                contratacoes_lidas=report.contratacoes_lidas,
                versoes_novas=report.versoes_novas,
                inalteradas=report.inalteradas,
                documentos_baixados=report.documentos_baixados,
                eventos_publicados=report.eventos_publicados,
                falhas=len(report.falhas),
            )
            if args.once:
                break
            stop.wait(settings.ingestao_intervalo_minutos * 60)  # acorda antes se receber sinal
    finally:
        close()
        for sig, handler in previous.items():  # devolve os tratadores de sinal originais
            signal.signal(sig, handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
