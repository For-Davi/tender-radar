"""Testes da camada bronze no MongoDB real."""

from datetime import UTC, datetime, timedelta

import pytest
from pymongo.database import Database

from radar.adapters.mongo.bronze import CONTRATACOES, DOCUMENTOS, MongoBronzeRepository, MongoDoc
from radar.ports.bronze import BronzeRecord, StoredDocument

T0 = datetime(2025, 9, 1, 12, 0, tzinfo=UTC)
NUMERO = "11222333000181-1-000001/2025"


@pytest.fixture
def repo(mongo_db: Database[MongoDoc]) -> MongoBronzeRepository:
    repository = MongoBronzeRepository(mongo_db)
    repository.ensure_indexes()
    return repository


def _record(hash_: str, when: datetime = T0) -> BronzeRecord:
    return BronzeRecord(NUMERO, {"conteudo": hash_}, hash_, when)


def _document(seq: int = 1, when: datetime = T0) -> StoredDocument:
    return StoredDocument(NUMERO, seq, f"x/{seq}.pdf", "a" * 64, 10, "pdf", when)


# ------------------------------------------------------------------ versões


def test_first_save_stores_version(
    repo: MongoBronzeRepository, mongo_db: Database[MongoDoc]
) -> None:
    assert repo.save_if_changed(_record("h1")) is True

    (doc,) = mongo_db[CONTRATACOES].find()
    assert doc["payload"] == {"conteudo": "h1"}
    assert doc["fonte"] == "pncp"
    assert doc["primeira_coleta"] == T0
    assert doc["ultima_coleta"] == T0


def test_same_content_is_not_stored_again(
    repo: MongoBronzeRepository, mongo_db: Database[MongoDoc]
) -> None:
    repo.save_if_changed(_record("h1"))

    assert repo.save_if_changed(_record("h1", T0 + timedelta(hours=1))) is False

    (doc,) = mongo_db[CONTRATACOES].find()
    assert doc["primeira_coleta"] == T0
    assert doc["ultima_coleta"] == T0 + timedelta(hours=1)  # registra que foi visto de novo


def test_changed_content_creates_new_version(
    repo: MongoBronzeRepository, mongo_db: Database[MongoDoc]
) -> None:
    repo.save_if_changed(_record("h1"))

    assert repo.save_if_changed(_record("h2", T0 + timedelta(hours=1))) is True
    assert mongo_db[CONTRATACOES].count_documents({}) == 2


def test_content_reverting_to_old_version_is_not_duplicated(
    repo: MongoBronzeRepository, mongo_db: Database[MongoDoc]
) -> None:
    repo.save_if_changed(_record("A", T0))
    repo.save_if_changed(_record("B", T0 + timedelta(hours=1)))

    assert repo.save_if_changed(_record("A", T0 + timedelta(hours=2))) is True

    assert mongo_db[CONTRATACOES].count_documents({}) == 2
    latest = mongo_db[CONTRATACOES].find_one(sort=[("ultima_coleta", -1)])
    assert latest is not None
    assert latest["hash"] == "A"


def test_indexes_are_created_idempotently(
    repo: MongoBronzeRepository, mongo_db: Database[MongoDoc]
) -> None:
    repo.ensure_indexes()  # segunda vez: não pode dar erro

    unique_indexes = {
        tuple(key for key, _ in info["key"])
        for info in mongo_db[CONTRATACOES].index_information().values()
        if info.get("unique")
    }
    assert ("numero_controle_pncp", "hash") in unique_indexes


# ------------------------------------------------------------------ documentos (outbox)


def test_register_and_exists(repo: MongoBronzeRepository) -> None:
    assert repo.document_exists(NUMERO, 1) is False

    repo.register_document(_document(1))

    assert repo.document_exists(NUMERO, 1) is True
    assert repo.document_exists(NUMERO, 2) is False


def test_registered_document_is_pending_until_published(repo: MongoBronzeRepository) -> None:
    repo.register_document(_document(1))

    assert repo.pending_documents() == [_document(1)]  # ida e volta sem perder campo

    repo.mark_published(NUMERO, 1, T0)

    assert repo.pending_documents() == []


def test_register_twice_is_idempotent(
    repo: MongoBronzeRepository, mongo_db: Database[MongoDoc]
) -> None:
    repo.register_document(_document(1, T0))
    repo.mark_published(NUMERO, 1, T0)

    repo.register_document(_document(1, T0 + timedelta(days=1)))

    (doc,) = mongo_db[DOCUMENTOS].find()
    assert doc["baixado_em"] == T0  # o registro original foi mantido
    assert doc["publicado_em"] == T0  # e continua publicado (não volta a pendente)


def test_pending_documents_are_ordered_by_download_time(repo: MongoBronzeRepository) -> None:
    repo.register_document(_document(2, T0 + timedelta(minutes=5)))
    repo.register_document(_document(1, T0))

    assert [d.sequencial_documento for d in repo.pending_documents()] == [1, 2]
