"""Testes do contrato do evento edital.novo."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from radar.events import EditalNovoV1

_SHA = "a" * 64


def _event(**overrides: object) -> EditalNovoV1:
    fields: dict[str, object] = {
        "numero_controle_pncp": "11222333000181-1-000123/2025",
        "sequencial_documento": 1,
        "caminho": "11222333000181/2025/123/1.pdf",
        "sha256": _SHA,
        "occurred_at": datetime(2025, 9, 1, 12, 0, tzinfo=UTC),
    }
    return EditalNovoV1.for_document(**(fields | overrides))  # type: ignore[arg-type]


def test_json_roundtrip() -> None:
    event = _event()

    assert EditalNovoV1.model_validate_json(event.model_dump_json()) == event


def test_json_has_type_and_version() -> None:
    body = json.loads(_event().model_dump_json())

    assert body["event_type"] == "edital.novo"
    assert body["schema_version"] == 1


def test_event_id_is_deterministic_per_document() -> None:
    # republicar o mesmo documento (at-least-once) gera o mesmo id -> consumidor deduplica
    first = _event(occurred_at=datetime(2025, 9, 1, tzinfo=UTC))
    again = _event(occurred_at=datetime(2025, 9, 2, tzinfo=UTC))

    assert first.event_id == again.event_id


def test_different_document_has_different_event_id() -> None:
    assert _event(sequencial_documento=1).event_id != _event(sequencial_documento=2).event_id
    assert _event().event_id != _event(sha256="b" * 64).event_id


@pytest.mark.parametrize(
    "overrides",
    [
        {"sha256": "nao-e-hash"},
        {"sequencial_documento": 0},
        {"caminho": ""},
        {"occurred_at": datetime(2025, 9, 1, 12, 0)},  # sem fuso
    ],
)
def test_invalid_fields_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _event(**overrides)


def test_unknown_fields_are_rejected() -> None:
    body = json.loads(_event().model_dump_json()) | {"campo_novo": 1}

    with pytest.raises(ValidationError, match="campo_novo"):
        EditalNovoV1.model_validate(body)


def test_other_schema_version_is_rejected() -> None:
    body = json.loads(_event().model_dump_json()) | {"schema_version": 2}

    with pytest.raises(ValidationError):
        EditalNovoV1.model_validate(body)


def test_event_is_immutable() -> None:
    with pytest.raises(ValidationError):
        _event().caminho = "outro"  # type: ignore[misc]
