"""Testes do worker: argumentos, janela de datas e o loop principal (com fakes)."""

import signal
from collections.abc import Callable, Iterator
from datetime import date

import pytest
import structlog

from radar.config import Settings
from radar.services.ingestao import IngestaoService, JanelaIngestao, RelatorioIngestao
from radar.workers.ingestao import Args, build_janela, main, parse_args
from tests.fakes import FakePublisher, FakeSource, InMemoryBronze, InMemoryStorage

HOJE = date(2025, 9, 10)


@pytest.fixture(autouse=True)
def reset_logging() -> Iterator[None]:
    # main() configura o structlog globalmente; restauramos o padrão depois de cada teste
    yield
    structlog.reset_defaults()


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


# ------------------------------------------------------------------ argumentos


def test_default_is_loop_with_rolling_window() -> None:
    assert parse_args([]) == Args(once=False, data_inicial=None, data_final=None)


def test_once_flag() -> None:
    assert parse_args(["--once"]).once is True


def test_backfill_dates_imply_once() -> None:
    args = parse_args(["--data-inicial", "2025-03-01", "--data-final", "2025-03-31"])

    assert args == Args(once=True, data_inicial=date(2025, 3, 1), data_final=date(2025, 3, 31))


@pytest.mark.parametrize(
    "argv",
    [
        ["--data-inicial", "2025-03-01"],  # falta a final
        ["--data-final", "2025-03-01"],  # falta a inicial
        ["--data-inicial", "2025-03-31", "--data-final", "2025-03-01"],  # invertidas
        ["--data-inicial", "01/03/2025", "--data-final", "2025-03-31"],  # formato errado
    ],
)
def test_invalid_arguments_exit_with_error(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(argv)

    assert exc_info.value.code == 2  # código padrão do argparse para uso incorreto


# ------------------------------------------------------------------ janela


def test_rolling_window_ends_today() -> None:
    janela = build_janela(Args(False, None, None), _settings(ingestao_janela_dias=2), HOJE)

    assert (janela.data_inicial, janela.data_final) == (date(2025, 9, 9), HOJE)


def test_window_of_one_day_is_just_today() -> None:
    janela = build_janela(Args(False, None, None), _settings(ingestao_janela_dias=1), HOJE)

    assert (janela.data_inicial, janela.data_final) == (HOJE, HOJE)


def test_window_uses_configured_modalidades_and_ufs() -> None:
    settings = _settings(ingestao_modalidades=[8], ingestao_ufs=["SP", "RJ"])

    janela = build_janela(Args(False, None, None), settings, HOJE)

    assert janela.modalidades == (8,)
    assert janela.ufs == ("SP", "RJ")


def test_backfill_window_uses_given_dates() -> None:
    args = Args(True, date(2025, 3, 1), date(2025, 3, 31))

    janela = build_janela(args, _settings(), HOJE)

    assert (janela.data_inicial, janela.data_final) == (date(2025, 3, 1), date(2025, 3, 31))


# ------------------------------------------------------------------ loop principal


class RecordingService(IngestaoService):
    """Serviço real com fakes, que anota as janelas pedidas."""

    def __init__(self) -> None:
        super().__init__(FakeSource(), InMemoryBronze(), InMemoryStorage(), FakePublisher())
        self.janelas: list[JanelaIngestao] = []

    def run(self, janela: JanelaIngestao) -> RelatorioIngestao:
        self.janelas.append(janela)
        return super().run(janela)


def _factory(
    service: RecordingService, closed: list[bool]
) -> Callable[[Settings], tuple[IngestaoService, Callable[[], None]]]:
    return lambda _settings: (service, lambda: closed.append(True))


def test_main_once_runs_one_window_and_closes() -> None:
    service = RecordingService()
    closed: list[bool] = []

    code = main(
        ["--once"],
        settings=_settings(),
        service_factory=_factory(service, closed),
        today=lambda: HOJE,
    )

    assert code == 0
    assert [(j.data_inicial, j.data_final) for j in service.janelas] == [(date(2025, 9, 9), HOJE)]
    assert closed == [True]  # conexões fechadas mesmo no modo --once


def test_main_restores_signal_handlers() -> None:
    before = signal.getsignal(signal.SIGINT)

    main(["--once"], settings=_settings(), service_factory=_factory(RecordingService(), []))

    assert signal.getsignal(signal.SIGINT) is before


def test_main_closes_connections_even_if_run_fails() -> None:
    class ExplodingService(RecordingService):
        def run(self, janela: JanelaIngestao) -> RelatorioIngestao:
            raise RuntimeError("Mongo fora do ar")

    closed: list[bool] = []

    with pytest.raises(RuntimeError, match="Mongo"):
        main(["--once"], settings=_settings(), service_factory=_factory(ExplodingService(), closed))

    assert closed == [True]
