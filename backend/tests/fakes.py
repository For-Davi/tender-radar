"""Implementações em memória dos ports, para testar serviços sem infraestrutura.

Não são mocks do código sob teste: são versões simples e reais dos contratos
(`ContratacoesSource`, `BronzeRepository`...), com falhas que o teste pode ligar.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime

from radar.events import EditalNovoV1
from radar.ports.bronze import BronzeRecord, StoredDocument
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
