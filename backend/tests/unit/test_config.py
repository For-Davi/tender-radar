"""Testes de `Settings`: padrões, leitura do ambiente e erros claros."""

import pytest
from pydantic import ValidationError

from radar.config import Settings

# Todas as variáveis que Settings lê. Apagá-las antes de cada teste garante que
# o resultado não depende do ambiente de quem roda (máquina local ou CI).
_ENV_VARS = (
    "APP_NAME",
    "ENVIRONMENT",
    "LOG_LEVEL",
    "LOG_JSON",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "radar"
    assert settings.environment == "dev"
    assert settings.log_level == "INFO"
    assert settings.log_json is False
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5432


def test_settings_reads_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_JSON", "true")
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "6543")

    settings = Settings()

    assert settings.environment == "prod"
    assert settings.log_level == "DEBUG"
    assert settings.log_json is True
    assert settings.postgres_host == "postgres"
    assert settings.postgres_port == 6543  # convertido de texto para int


def test_settings_log_level_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "warning")

    assert Settings().log_level == "WARNING"


def test_settings_invalid_log_level_fails_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "banana")

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["loc"] == ("log_level",)  # o erro aponta o campo culpado


@pytest.mark.parametrize("port", ["abc", "0", "70000"])
def test_settings_invalid_port_fails_clearly(monkeypatch: pytest.MonkeyPatch, port: str) -> None:
    monkeypatch.setenv("POSTGRES_PORT", port)

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert exc_info.value.errors()[0]["loc"] == ("postgres_port",)


def test_settings_invalid_environment_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")

    with pytest.raises(ValidationError):
        Settings()


def test_postgres_dsn_is_built_from_parts() -> None:
    settings = Settings(
        postgres_host="db",
        postgres_port=5433,
        postgres_user="app",
        postgres_password="segredo",  # pydantic converte str -> SecretStr
        postgres_db="radar_test",
    )

    assert settings.postgres_dsn == "postgresql://app:segredo@db:5433/radar_test"


def test_postgres_dsn_escapes_special_chars_in_password() -> None:
    # "@" e "/" na senha quebrariam a URL se não fossem codificados
    settings = Settings(postgres_password="p@ss/word")

    assert "p%40ss%2Fword@" in settings.postgres_dsn


def test_password_is_not_exposed_in_repr() -> None:
    settings = Settings(postgres_password="super-secreta")

    assert "super-secreta" not in repr(settings)
