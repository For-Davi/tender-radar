"""Camada bronze no MongoDB: o JSON do PNCP guardado como veio, versionado por hash.

Coleções:
- `pncp_contratacoes`: uma versão por conteúdo distinto de cada contratação.
  `primeira_coleta` = quando esse conteúdo apareceu; `ultima_coleta` = última vez visto;
  `vigente_desde` = quando ele passou a ser o conteúdo atual (lido pelo pipeline silver).
- `pncp_documentos`: documentos baixados + controle do evento (outbox):
  `publicado_em` nulo = evento ainda não confirmado pelo broker.
"""

from collections.abc import Iterator
from dataclasses import asdict
from datetime import datetime
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from radar.ports.bronze import BronzeRecord, BronzeVersion, StoredDocument

CONTRATACOES = "pncp_contratacoes"
DOCUMENTOS = "pncp_documentos"

# Any: documentos do Mongo são dicionários com valores de tipos variados (BSON)
MongoDoc = dict[str, Any]


class MongoBronzeRepository:
    def __init__(self, db: Database[MongoDoc]) -> None:
        self._contratacoes = db[CONTRATACOES]
        self._documentos = db[DOCUMENTOS]

    def ensure_indexes(self) -> None:
        """Cria os índices (idempotente: se já existem, o Mongo não faz nada)."""
        # UNIQUE: o mesmo conteúdo da mesma contratação nunca é gravado duas vezes
        self._contratacoes.create_index(
            [("numero_controle_pncp", ASCENDING), ("hash", ASCENDING)], unique=True
        )
        # acha rápido a versão mais recente de cada contratação
        self._contratacoes.create_index(
            [("numero_controle_pncp", ASCENDING), ("ultima_coleta", DESCENDING)]
        )
        self._documentos.create_index(
            [("numero_controle_pncp", ASCENDING), ("sequencial_documento", ASCENDING)],
            unique=True,
        )
        self._documentos.create_index([("publicado_em", ASCENDING)])
        # leitura incremental do pipeline bronze -> silver
        self._contratacoes.create_index([("vigente_desde", ASCENDING)])
        # documentos gravados antes do campo existir (Etapa 02): a versão é vigente desde
        # que apareceu. Update com pipeline ([...]) permite copiar um campo para outro.
        self._contratacoes.update_many(
            {"vigente_desde": {"$exists": False}},
            [{"$set": {"vigente_desde": "$primeira_coleta"}}],
        )

    def save_if_changed(self, record: BronzeRecord) -> bool:
        latest = self._contratacoes.find_one(
            {"numero_controle_pncp": record.numero_controle_pncp},
            sort=[("ultima_coleta", DESCENDING)],
            projection={"hash": 1},
        )
        if latest is not None and latest["hash"] == record.hash:
            self._touch(record)
            return False
        # upsert pela chave única: se o conteúdo voltou a uma versão antiga (A -> B -> A),
        # a versão A é "reativada" (ultima_coleta atualizada) em vez de duplicada
        self._contratacoes.update_one(
            {"numero_controle_pncp": record.numero_controle_pncp, "hash": record.hash},
            {
                "$setOnInsert": {
                    "payload": record.payload,
                    "fonte": record.fonte,
                    "primeira_coleta": record.coletado_em,
                },
                # vigente_desde só muda aqui (conteúdo novo ou A -> B -> A), nunca no _touch
                "$set": {"ultima_coleta": record.coletado_em, "vigente_desde": record.coletado_em},
            },
            upsert=True,
        )
        return True

    def versions_between(
        self, depois_de: datetime | None, ate: datetime
    ) -> Iterator[BronzeVersion]:
        intervalo: MongoDoc = {"$lte": ate}
        if depois_de is not None:
            intervalo["$gt"] = depois_de
        cursor = self._contratacoes.find(
            {"vigente_desde": intervalo},
            projection={
                "_id": 0,
                "numero_controle_pncp": 1,
                "hash": 1,
                "payload": 1,
                "vigente_desde": 1,
            },
        ).sort([("vigente_desde", ASCENDING), ("numero_controle_pncp", ASCENDING)])
        for doc in cursor:
            yield BronzeVersion(**doc)

    def document_exists(self, numero_controle_pncp: str, sequencial_documento: int) -> bool:
        query = {
            "numero_controle_pncp": numero_controle_pncp,
            "sequencial_documento": sequencial_documento,
        }
        return self._documentos.count_documents(query, limit=1) > 0

    def register_document(self, document: StoredDocument) -> None:
        # $setOnInsert: registrar de novo o mesmo documento não altera nada (idempotente)
        self._documentos.update_one(
            {
                "numero_controle_pncp": document.numero_controle_pncp,
                "sequencial_documento": document.sequencial_documento,
            },
            {"$setOnInsert": asdict(document) | {"publicado_em": None}},
            upsert=True,
        )

    def pending_documents(self) -> list[StoredDocument]:
        cursor = self._documentos.find(
            {"publicado_em": None}, projection={"_id": 0, "publicado_em": 0}
        ).sort("baixado_em", ASCENDING)
        return [StoredDocument(**doc) for doc in cursor]

    def mark_published(
        self, numero_controle_pncp: str, sequencial_documento: int, publicado_em: datetime
    ) -> None:
        self._documentos.update_one(
            {
                "numero_controle_pncp": numero_controle_pncp,
                "sequencial_documento": sequencial_documento,
            },
            {"$set": {"publicado_em": publicado_em}},
        )

    def _touch(self, record: BronzeRecord) -> None:
        self._contratacoes.update_one(
            {"numero_controle_pncp": record.numero_controle_pncp, "hash": record.hash},
            {"$set": {"ultima_coleta": record.coletado_em}},
        )
