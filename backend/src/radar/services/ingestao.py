"""Caso de uso: ingestão do PNCP para a camada bronze, com aviso de editais novos.

Orquestra os ports (fonte, bronze, storage, publicador) sem saber quem os implementa.
Regras de robustez:
- falha em uma contratação, documento ou combinação modalidade/UF vira registro no
  relatório, e o lote continua;
- idempotente: rodar de novo a mesma janela não duplica versões, arquivos nem eventos;
- outbox: o evento de um documento sai logo depois que ele é gravado, e só é marcado
  como publicado após a confirmação do broker. O que ficou pendente (broker fora do
  ar) é republicado no início da execução seguinte.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import structlog

from radar.events import EditalNovoV1
from radar.ports.bronze import BronzeRecord, BronzeRepository, StoredDocument
from radar.ports.contratacoes_source import (
    ContratacoesSource,
    DocumentoRef,
    JsonDict,
    RawContratacao,
    SourceError,
)
from radar.ports.document_storage import DocumentStorage, StorageError
from radar.ports.events import EventPublisher, PublishError

log = structlog.get_logger()

_EXTENSIONS = {"pdf": "pdf", "zip": "zip", "desconhecido": "bin"}


def payload_hash(payload: JsonDict) -> str:
    """SHA-256 do JSON canônico (chaves ordenadas): mesma informação -> mesmo hash."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def detect_file_type(content: bytes) -> str:
    """Identifica o arquivo pelos primeiros bytes ("magic number"), não pelo cabeçalho HTTP."""
    if content.startswith(b"%PDF"):
        return "pdf"
    if content.startswith(b"PK\x03\x04"):
        return "zip"
    return "desconhecido"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class JanelaIngestao:
    data_inicial: date
    data_final: date
    modalidades: tuple[int, ...]
    ufs: tuple[str, ...]


@dataclass(slots=True)
class RelatorioIngestao:
    contratacoes_lidas: int = 0
    versoes_novas: int = 0
    inalteradas: int = 0
    documentos_baixados: int = 0
    eventos_publicados: int = 0
    falhas: list[str] = field(default_factory=list)


class IngestaoService:
    def __init__(
        self,
        source: ContratacoesSource,
        bronze: BronzeRepository,
        storage: DocumentStorage,
        publisher: EventPublisher,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._source = source
        self._bronze = bronze
        self._storage = storage
        self._publisher = publisher
        self._clock = clock
        # se o broker falhar no meio de uma execução, não insiste até a próxima
        self._broker_available = True

    def run(self, janela: JanelaIngestao) -> RelatorioIngestao:
        report = RelatorioIngestao()
        self._broker_available = True
        # primeiro, o que ficou pendente de execuções anteriores
        for doc in self._bronze.pending_documents():
            self._publish(doc, report)
        for modalidade in janela.modalidades:
            for uf in janela.ufs:
                self._ingest_listing(janela, modalidade, uf, report)
        return report

    # ------------------------------------------------------------------ etapas

    def _ingest_listing(
        self, janela: JanelaIngestao, modalidade: int, uf: str, report: RelatorioIngestao
    ) -> None:
        try:
            contratacoes = self._source.list_contratacoes(
                janela.data_inicial, janela.data_final, modalidade, uf
            )
            for raw in contratacoes:
                report.contratacoes_lidas += 1
                self._ingest_contratacao(raw, report)
        except SourceError as exc:
            self._fail(report, f"listagem {modalidade}/{uf}: {exc}")

    def _ingest_contratacao(self, raw: RawContratacao, report: RelatorioIngestao) -> None:
        ref = raw.ref
        try:
            itens = self._source.get_itens(ref)
            resultados = {
                str(item.numero_item): self._source.get_resultados(ref, item.numero_item)
                for item in itens
                if item.tem_resultado
            }
            documentos = self._source.get_documentos(ref)
        except SourceError as exc:
            self._fail(report, f"detalhes de {ref.numero_controle_pncp}: {exc}")
            return

        payload: JsonDict = {
            "contratacao": raw.payload,
            "itens": [item.payload for item in itens],
            "resultados": resultados,
            "arquivos": [doc.payload for doc in documentos],
        }
        record = BronzeRecord(
            numero_controle_pncp=ref.numero_controle_pncp,
            payload=payload,
            hash=payload_hash(payload),
            coletado_em=self._clock(),
        )
        versao_nova = self._bronze.save_if_changed(record)
        if versao_nova:
            report.versoes_novas += 1
        else:
            report.inalteradas += 1
        log.info(
            "contratacao_ingerida",
            numero_controle_pncp=ref.numero_controle_pncp,
            itens=len(itens),
            versao_nova=versao_nova,
            lidas_ate_agora=report.contratacoes_lidas,
        )

        for documento in documentos:
            if documento.eh_edital:
                self._store_document(raw, documento, report)

    def _store_document(
        self, raw: RawContratacao, documento: DocumentoRef, report: RelatorioIngestao
    ) -> None:
        ref = raw.ref
        if self._bronze.document_exists(ref.numero_controle_pncp, documento.sequencial_documento):
            return
        try:
            content = self._source.download(documento.url)
            tipo = detect_file_type(content)
            key = (
                f"{ref.cnpj}/{ref.ano}/{ref.sequencial}/"
                f"{documento.sequencial_documento}.{_EXTENSIONS[tipo]}"
            )
            caminho = self._storage.save(key, content)
        except (SourceError, StorageError) as exc:
            self._fail(report, f"documento {documento.url}: {exc}")
            return

        stored = StoredDocument(
            numero_controle_pncp=ref.numero_controle_pncp,
            sequencial_documento=documento.sequencial_documento,
            caminho=caminho,
            sha256=hashlib.sha256(content).hexdigest(),
            tamanho_bytes=len(content),
            tipo_arquivo=tipo,
            baixado_em=self._clock(),
        )
        # registra ANTES de publicar: se o processo cair aqui, o documento fica pendente
        # e o evento sai na próxima execução (at-least-once)
        self._bronze.register_document(stored)
        report.documentos_baixados += 1
        self._publish(stored, report)

    def _publish(self, doc: StoredDocument, report: RelatorioIngestao) -> None:
        if not self._broker_available:
            return  # fica pendente para a próxima execução
        event = EditalNovoV1.for_document(
            numero_controle_pncp=doc.numero_controle_pncp,
            sequencial_documento=doc.sequencial_documento,
            caminho=doc.caminho,
            sha256=doc.sha256,
            occurred_at=self._clock(),
        )
        try:
            self._publisher.publish(event)
        except PublishError as exc:
            self._broker_available = False
            self._fail(report, f"publicação de {doc.numero_controle_pncp}: {exc}")
            return
        self._bronze.mark_published(
            doc.numero_controle_pncp, doc.sequencial_documento, self._clock()
        )
        report.eventos_publicados += 1

    @staticmethod
    def _fail(report: RelatorioIngestao, message: str) -> None:
        log.warning("ingestao_falha", detalhe=message)
        report.falhas.append(message)
