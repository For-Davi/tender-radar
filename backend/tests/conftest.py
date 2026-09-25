"""Configuração compartilhada do pytest.

Marca cada teste automaticamente pela pasta onde ele está:
`tests/unit/` recebe `unit`, `tests/integration/` recebe `integration` e
`tests/contract/` recebe `contract`.
Assim ninguém precisa lembrar de decorar cada teste, e `pytest -m unit`
nunca executa, por engano, um teste que depende de container.
"""

from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        folder = item.path.relative_to(_TESTS_DIR).parts[0]
        if folder in ("unit", "integration", "contract"):
            item.add_marker(folder)
