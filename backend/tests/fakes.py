"""Implementações em memória dos ports, para testar serviços sem infraestrutura.

Não são mocks do código sob teste: são versões simples e reais dos contratos
(`ContratacoesSource`, `BronzeRepository`...), com falhas que o teste pode ligar.
"""

import copy
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime

from radar.domain.entities import Contratacao, Fornecedor, Orgao
from radar.domain.errors import DuplicateEntityError, ReferenceNotFoundError
from radar.domain.value_objects import Cnpj
from radar.events import EditalNovoV1
from radar.ports.bronze import BronzeRecord, BronzeVersion, StoredDocument
from radar.ports.contratacoes_source import (
    ContratacaoRef,
    DocumentoRef,
    JsonDict,
    RawContratacao,
    RawItem,
    SourceUnavailableError,
)
from radar.ports.document_storage import StorageError
from radar.ports.events import PublishError
from radar.ports.silver import Rejeicao


def make_raw(sequencial: int, **payload_extra: object) -> RawContratacao:
    cnpj = "11222333000181"
    numero = f"{cnpj}-1-{sequencial:06d}/2025"
    payload: JsonDict = {"numeroControlePNCP": numero, "objetoCompra": "Objeto"} | payload_extra
    return RawContratacao(ContratacaoRef(numero, cnpj, 2025, sequencial), payload)


def make_edital(sequencial_documento: int = 1, *, eh_edital: bool = True) -> DocumentoRef:
    url = f"https://pncp.test/doc/{sequencial_documento}"
    return DocumentoRef(sequencial_documento, eh_edital, url, {"url": url})


@dataclass
class FakeSource:
    """Fonte configurável: contratações por (modalidade, uf), itens, documentos e arquivos."""

    contratacoes: dict[tuple[int, str], list[RawContratacao]] = field(default_factory=dict)
    itens: dict[str, list[RawItem]] = field(default_factory=dict)
    resultados: dict[tuple[str, int], list[JsonDict]] = field(default_factory=dict)
    documentos: dict[str, list[DocumentoRef]] = field(default_factory=dict)
    arquivos: dict[str, bytes] = field(default_factory=dict)
    fail_listing: set[tuple[int, str]] = field(default_factory=set)
    fail_details_for: set[str] = field(default_factory=set)
    fail_download_for: set[str] = field(default_factory=set)
    downloads: list[str] = field(default_factory=list)

    def list_contratacoes(
        self, data_inicial: date, data_final: date, modalidade: int, uf: str
    ) -> Iterator[RawContratacao]:
        if (modalidade, uf) in self.fail_listing:
            raise SourceUnavailableError(f"listagem indisponível {modalidade}/{uf}")
        yield from self.contratacoes.get((modalidade, uf), [])

    def get_itens(self, ref: ContratacaoRef) -> list[RawItem]:
        if ref.numero_controle_pncp in self.fail_details_for:
            raise SourceUnavailableError(f"itens indisponíveis {ref.numero_controle_pncp}")
        return self.itens.get(ref.numero_controle_pncp, [])

    def get_resultados(self, ref: ContratacaoRef, numero_item: int) -> list[JsonDict]:
        return self.resultados.get((ref.numero_controle_pncp, numero_item), [])

    def get_documentos(self, ref: ContratacaoRef) -> list[DocumentoRef]:
        return self.documentos.get(ref.numero_controle_pncp, [])

    def download(self, url: str) -> bytes:
        self.downloads.append(url)
        if url in self.fail_download_for:
            raise SourceUnavailableError(f"download falhou {url}")
        return self.arquivos.get(url, b"%PDF-1.7 edital de teste")


@dataclass
class InMemoryBronze:
    versions: list[BronzeRecord] = field(default_factory=list)
    documents: dict[tuple[str, int], StoredDocument] = field(default_factory=dict)
    published: dict[tuple[str, int], datetime] = field(default_factory=dict)

    def save_if_changed(self, record: BronzeRecord) -> bool:
        latest = [v for v in self.versions if v.numero_controle_pncp == record.numero_controle_pncp]
        if latest and latest[-1].hash == record.hash:
            return False
        self.versions.append(record)
        return True

    def document_exists(self, numero_controle_pncp: str, sequencial_documento: int) -> bool:
        return (numero_controle_pncp, sequencial_documento) in self.documents

    def register_document(self, document: StoredDocument) -> None:
        key = (document.numero_controle_pncp, document.sequencial_documento)
        self.documents.setdefault(key, document)

    def pending_documents(self) -> list[StoredDocument]:
        return [doc for key, doc in self.documents.items() if key not in self.published]

    def mark_published(
        self, numero_controle_pncp: str, sequencial_documento: int, publicado_em: datetime
    ) -> None:
        self.published[(numero_controle_pncp, sequencial_documento)] = publicado_em


@dataclass
class InMemoryStorage:
    files: dict[str, bytes] = field(default_factory=dict)
    fail: bool = False

    def save(self, key: str, content: bytes) -> str:
        if self.fail:
            raise StorageError("disco cheio")
        self.files[key] = content
        return key


@dataclass
class FakePublisher:
    events: list[EditalNovoV1] = field(default_factory=list)
    failures_left: int = 0

    def publish(self, event: EditalNovoV1) -> None:
        if self.failures_left > 0:
            self.failures_left -= 1
            raise PublishError("broker não confirmou")
        self.events.append(event)


# ------------------------------------------------------------------ bronze -> silver


@dataclass
class InMemoryBronzeReader:
    versions: list[BronzeVersion] = field(default_factory=list)
    calls: list[tuple[datetime | None, datetime]] = field(default_factory=list)

    def versions_between(
        self, depois_de: datetime | None, ate: datetime
    ) -> Iterator[BronzeVersion]:
        self.calls.append((depois_de, ate))
        selected = [
            v
            for v in self.versions
            if (depois_de is None or v.vigente_desde > depois_de) and v.vigente_desde <= ate
        ]
        yield from sorted(selected, key=lambda v: v.vigente_desde)


class _KeyedRepo[K, T]:
    """Repositório em memória genérico: upsert/add/get por uma chave natural."""

    def __init__(self, store: Callable[[], dict[K, T]], key_of: Callable[[T], K]) -> None:
        self._store = store  # função: o dicionário muda quando a UoW faz rollback
        self._key_of = key_of
        self.fail_for: set[K] = set()  # chaves cuja gravação o "banco" recusa

    def add(self, entity: T) -> None:
        if self._key_of(entity) in self._store():
            raise DuplicateEntityError(str(self._key_of(entity)))
        self.upsert(entity)

    def upsert(self, entity: T) -> None:
        key = self._key_of(entity)
        if key in self.fail_for:
            raise ReferenceNotFoundError(f"recusado pelo banco: {key}")
        self._store()[key] = copy.deepcopy(entity)

    def get(self, key: K) -> T | None:
        return self._store().get(key)


@dataclass
class SilverState:
    orgaos: dict[Cnpj, Orgao] = field(default_factory=dict)
    fornecedores: dict[str, Fornecedor] = field(default_factory=dict)
    contratacoes: dict[str, Contratacao] = field(default_factory=dict)
    rejeicoes: dict[tuple[str, str, int | None], Rejeicao] = field(default_factory=dict)
    marcas: dict[str, datetime] = field(default_factory=dict)


class _RejeicaoRepo:
    def __init__(self, uow: "FakeSilverUnitOfWork") -> None:
        self._uow = uow

    def add(self, rejeicao: Rejeicao) -> None:
        key = (rejeicao.numero_controle_pncp, rejeicao.bronze_hash, rejeicao.numero_item)
        self._uow.pending.rejeicoes.setdefault(key, rejeicao)  # idempotente, como o UNIQUE


class _WatermarkRepo:
    def __init__(self, uow: "FakeSilverUnitOfWork") -> None:
        self._uow = uow

    def get(self, pipeline: str) -> datetime | None:
        return self._uow.pending.marcas.get(pipeline)

    def set(self, pipeline: str, marca: datetime) -> None:
        self._uow.pending.marcas[pipeline] = marca


class FakeSilverUnitOfWork:
    """Silver em memória com transação:  só vira  no commit.

    simula uma falha inesperada (ex.: banco caiu) ao gravar aquela contratação.
    """

    def __init__(self) -> None:
        self.committed = SilverState()
        self.pending = SilverState()
        self.commits = 0
        self.rollbacks = 0
        self.crash_on: str | None = None
        self._orgaos = _KeyedRepo[Cnpj, Orgao](lambda: self.pending.orgaos, lambda o: o.cnpj)
        self._fornecedores = _KeyedRepo[str, Fornecedor](
            lambda: self.pending.fornecedores, lambda f: f.documento
        )
        self._contratacoes = _KeyedRepo[str, Contratacao](
            lambda: self.pending.contratacoes, self._contratacao_key
        )

    def _contratacao_key(self, contratacao: Contratacao) -> str:
        if contratacao.numero_controle_pncp == self.crash_on:
            raise RuntimeError("conexão com o banco perdida")
        return contratacao.numero_controle_pncp

    @property
    def orgaos(self) -> _KeyedRepo[Cnpj, Orgao]:
        return self._orgaos

    @property
    def fornecedores(self) -> _KeyedRepo[str, Fornecedor]:
        return self._fornecedores

    @property
    def contratacoes(self) -> _KeyedRepo[str, Contratacao]:
        return self._contratacoes

    @property
    def rejeicoes(self) -> _RejeicaoRepo:
        return _RejeicaoRepo(self)

    @property
    def watermarks(self) -> _WatermarkRepo:
        return _WatermarkRepo(self)

    def commit(self) -> None:
        self.committed = copy.deepcopy(self.pending)
        self.commits += 1

    def rollback(self) -> None:
        self.pending = copy.deepcopy(self.committed)
        self.rollbacks += 1
