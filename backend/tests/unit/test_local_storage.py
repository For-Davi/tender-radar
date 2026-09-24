"""Testes do armazenamento em disco local.

Usam `tmp_path`: um diretório temporário exclusivo de cada teste, criado e apagado
pelo pytest. É I/O de disco, mas isolado e rápido, sem depender de serviço externo.
"""

from pathlib import Path

import pytest

from radar.adapters.storage.local import LocalDocumentStorage
from radar.ports.document_storage import StorageError


def test_save_writes_file_and_returns_key(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)

    key = storage.save("11222333000181/2025/1/1.pdf", b"%PDF conteudo")

    assert key == "11222333000181/2025/1/1.pdf"
    assert (tmp_path / key).read_bytes() == b"%PDF conteudo"


def test_save_same_key_again_replaces_content(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    storage.save("a/1.pdf", b"v1")

    storage.save("a/1.pdf", b"v2")

    assert (tmp_path / "a/1.pdf").read_bytes() == b"v2"


def test_save_leaves_no_temporary_files(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)

    storage.save("a/1.pdf", b"x")

    assert [p.name for p in (tmp_path / "a").iterdir()] == ["1.pdf"]


def test_creates_root_if_missing(tmp_path: Path) -> None:
    root = tmp_path / "nao" / "existe"

    LocalDocumentStorage(root).save("x.pdf", b"x")

    assert (root / "x.pdf").exists()


@pytest.mark.parametrize("key", ["../fora.pdf", "a/../../fora.pdf", "/etc/passwd", "", "a/"])
def test_rejects_keys_outside_root(tmp_path: Path, key: str) -> None:
    # "path traversal": uma chave maliciosa não pode gravar fora da pasta do storage
    storage = LocalDocumentStorage(tmp_path / "root")

    with pytest.raises(StorageError, match="chave inválida"):
        storage.save(key, b"x")

    assert not (tmp_path / "fora.pdf").exists()
