"""Cliente da API pública do PNCP (implementa `ContratacoesSource`).

Peculiaridades da API, verificadas em chamadas reais (ver docs/pncp-api.md):
- `codigoModalidadeContratacao` é obrigatório na consulta de publicações;
- `tamanhoPagina` vai no máximo até 50;
- página além da última e listas vazias respondem 204, sem corpo;
- o download do edital responde `application/octet-stream`, às vezes com redirect.
"""

import time
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any, TypeVar

import httpx
import structlog
from pydantic import BaseModel, ValidationError
from tenacity import (
    RetryCallState,
    RetryError,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from radar.adapters.pncp.schemas import (
    TIPO_DOCUMENTO_EDITAL,
    ArquivoPncp,
    ContratacaoPublicada,
    ItemPncp,
    PaginaPublicacao,
)
from radar.ports.contratacoes_source import (
    ContratacaoRef,
    DocumentoRef,
    DocumentTooLargeError,
    JsonDict,
    RawContratacao,
    RawItem,
    SourceRequestError,
    SourceSchemaError,
    SourceUnavailableError,
)

PAGE_SIZE = 50  # máximo aceito pelo PNCP
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_AFTER_SECONDS = 60.0

_Model = TypeVar("_Model", bound=BaseModel)
_T = TypeVar("_T")
log = structlog.get_logger()


class _TransientError(Exception):
    """Falha que vale tentar de novo (5xx, 429, timeout, conexão)."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None or not value.isdigit():
        return None
    return min(float(value), _MAX_RETRY_AFTER_SECONDS)


def _describe_validation(exc: ValidationError) -> str:
    """Transforma o erro do Pydantic em algo legível: `orgaoEntidade.cnpj: Input should be...`."""
    parts = [f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}" for error in exc.errors()]
    return "; ".join(parts)


class PncpClient:
    def __init__(
        self,
        http: httpx.Client,
        *,
        consulta_url: str,
        api_url: str,
        max_attempts: int,
        min_interval_seconds: float,
        max_download_bytes: int,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._consulta_url = consulta_url.rstrip("/")
        self._api_url = api_url.rstrip("/")
        self._max_attempts = max_attempts
        self._min_interval = min_interval_seconds
        self._max_download_bytes = max_download_bytes
        # sleep e monotonic injetáveis: os testes controlam o tempo sem esperar de verdade
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None

    # ------------------------------------------------------------------ API pública (port)

    def list_contratacoes(
        self, data_inicial: date, data_final: date, modalidade: int, uf: str
    ) -> Iterator[RawContratacao]:
        url = f"{self._consulta_url}/v1/contratacoes/publicacao"
        params: dict[str, str | int] = {
            "dataInicial": data_inicial.strftime("%Y%m%d"),
            "dataFinal": data_final.strftime("%Y%m%d"),
            "codigoModalidadeContratacao": modalidade,
            "uf": uf,
            "tamanhoPagina": PAGE_SIZE,
        }
        pagina = 1
        while True:
            response = self._get(url, params | {"pagina": pagina})
            if response.status_code == httpx.codes.NO_CONTENT:
                return  # sem resultados, ou passou da última página
            page = self._parse(PaginaPublicacao, self._json(response), url)
            for record in page.data:
                yield self._to_raw_contratacao(record, url)
            if page.paginas_restantes == 0 or not page.data:
                return
            pagina += 1

    def get_itens(self, ref: ContratacaoRef) -> list[RawItem]:
        url = f"{self._compra_url(ref)}/itens"
        items: list[RawItem] = []
        for record in self._get_list(url):
            parsed = self._parse(ItemPncp, record, url)
            items.append(RawItem(parsed.numero_item, parsed.tem_resultado, record))
        return items

    def get_resultados(self, ref: ContratacaoRef, numero_item: int) -> list[JsonDict]:
        return self._get_list(f"{self._compra_url(ref)}/itens/{numero_item}/resultados")

    def get_documentos(self, ref: ContratacaoRef) -> list[DocumentoRef]:
        url = f"{self._compra_url(ref)}/arquivos"
        documentos: list[DocumentoRef] = []
        for record in self._get_list(url):
            parsed = self._parse(ArquivoPncp, record, url)
            documentos.append(
                DocumentoRef(
                    sequencial_documento=parsed.sequencial_documento,
                    eh_edital=parsed.tipo_documento_id == TIPO_DOCUMENTO_EDITAL,
                    url=parsed.url,
                    payload=record,
                )
            )
        return documentos

    def download(self, url: str) -> bytes:
        return self._with_retry(url, lambda: self._download_once(url))

    # ------------------------------------------------------------------ HTTP com retry

    def _get(self, url: str, params: dict[str, str | int] | None = None) -> httpx.Response:
        return self._with_retry(url, lambda: self._request_once(url, params))

    def _get_list(self, url: str) -> list[JsonDict]:
        response = self._get(url)
        if response.status_code == httpx.codes.NO_CONTENT:
            return []
        body = self._json(response)
        if not isinstance(body, list):
            raise SourceSchemaError(f"resposta inesperada de {url}: esperava lista JSON")
        return body

    def _with_retry(self, url: str, attempt: Callable[[], _T]) -> _T:
        retrying = Retrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=self._wait,
            retry=retry_if_exception(lambda exc: isinstance(exc, _TransientError)),
            sleep=self._sleep,
            before_sleep=lambda state: self._log_retry(state, url),
        )
        try:
            return retrying(attempt)
        except RetryError as exc:
            last = exc.last_attempt.exception()
            raise SourceUnavailableError(
                f"PNCP indisponível após {self._max_attempts} tentativas em {url}: {last}"
            ) from last

    def _wait(self, state: RetryCallState) -> float:
        """Usa o Retry-After do servidor se houver; senão, backoff exponencial com jitter."""
        exc = state.outcome.exception() if state.outcome else None
        if isinstance(exc, _TransientError) and exc.retry_after is not None:
            return exc.retry_after
        return wait_exponential_jitter(initial=1, max=30, jitter=1)(state)

    def _log_retry(self, state: RetryCallState, url: str) -> None:
        exc = state.outcome.exception() if state.outcome else None
        log.warning("pncp_nova_tentativa", tentativa=state.attempt_number, url=url, erro=str(exc))

    def _request_once(self, url: str, params: dict[str, str | int] | None) -> httpx.Response:
        self._throttle()
        try:
            response = self._http.get(url, params=params)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise _TransientError(f"{type(exc).__name__}: {exc}") from exc
        self._raise_for_status(response, url)
        return response

    def _download_once(self, url: str) -> bytes:
        self._throttle()
        try:
            with self._http.stream("GET", url, follow_redirects=True) as response:
                self._raise_for_status(response, url)
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self._max_download_bytes:
                        raise DocumentTooLargeError(
                            f"documento maior que {self._max_download_bytes} bytes: {url}"
                        )
                    chunks.append(chunk)
                return b"".join(chunks)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise _TransientError(f"{type(exc).__name__}: {exc}") from exc

    def _raise_for_status(self, response: httpx.Response, url: str) -> None:
        status = response.status_code
        if status in _RETRYABLE_STATUS:
            raise _TransientError(f"HTTP {status}", retry_after=_retry_after_seconds(response))
        if status >= 400:
            response.read()
            raise SourceRequestError(f"PNCP recusou {url}: HTTP {status} {response.text[:200]}")

    def _throttle(self) -> None:
        """Garante um intervalo mínimo entre requisições (educação com a API pública)."""
        now = self._monotonic()
        if self._last_request_at is not None:
            wait = self._min_interval - (now - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
                now += wait
        self._last_request_at = now

    # ------------------------------------------------------------------ parsing

    def _compra_url(self, ref: ContratacaoRef) -> str:
        return f"{self._api_url}/v1/orgaos/{ref.cnpj}/compras/{ref.ano}/{ref.sequencial}"

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise SourceSchemaError(
                f"resposta do PNCP não é JSON válido ({response.url}): {response.text[:100]!r}"
            ) from exc

    @staticmethod
    def _parse(model: type[_Model], data: Any, url: str) -> _Model:
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise SourceSchemaError(
                f"resposta inesperada do PNCP em {url}: {_describe_validation(exc)}"
            ) from exc

    def _to_raw_contratacao(self, record: JsonDict, url: str) -> RawContratacao:
        parsed = self._parse(ContratacaoPublicada, record, url)
        ref = ContratacaoRef(
            numero_controle_pncp=parsed.numero_controle_pncp,
            cnpj=parsed.orgao_entidade.cnpj,
            ano=parsed.ano_compra,
            sequencial=parsed.sequencial_compra,
        )
        return RawContratacao(ref=ref, payload=record)
