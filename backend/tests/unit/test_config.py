"""Testes de `Settings`: padrões, leitura do ambiente e erros claros."""

import pytest
from pydantic import ValidationError

from radar.config import Settings

# Todas as variáveis que Settings lê (derivadas dos próprios campos, para nenhuma ficar
# de fora). Apagá-las antes de cada teste garante que o resultado não depende do
# ambiente de quem roda (máquina local ou CI).
_ENV_VARS = tuple(name.upper() for name in Settings.model_fields)


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


# ------------------------------------------------------------------ Etapa 02


def test_ingestao_defaults() -> None:
    settings = Settings()

    assert settings.ingestao_ufs == ["CE"]
    assert settings.ingestao_modalidades == [6, 8]
    assert settings.ingestao_janela_dias == 2
    assert settings.ingestao_intervalo_minutos == 60


def test_lists_are_read_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INGESTAO_UFS", " ce, sp ,RJ")
    monkeypatch.setenv("INGESTAO_MODALIDADES", "6,8, 9")

    settings = Settings()

    assert settings.ingestao_ufs == ["CE", "SP", "RJ"]
    assert settings.ingestao_modalidades == [6, 8, 9]


@pytest.mark.parametrize(
    ("var", "value", "field"),
    [
        ("INGESTAO_UFS", "CE,XX", "ingestao_ufs"),
        ("INGESTAO_UFS", "", "ingestao_ufs"),
        ("INGESTAO_MODALIDADES", "6,99", "ingestao_modalidades"),
        ("INGESTAO_MODALIDADES", "seis", "ingestao_modalidades"),
        ("INGESTAO_JANELA_DIAS", "0", "ingestao_janela_dias"),
        ("PNCP_MAX_ATTEMPTS", "0", "pncp_max_attempts"),
    ],
)
def test_invalid_ingestao_settings_fail_clearly(
    monkeypatch: pytest.MonkeyPatch, var: str, value: str, field: str
) -> None:
    monkeypatch.setenv(var, value)

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert exc_info.value.errors()[0]["loc"][0] == field


def test_mongo_url_escapes_credentials() -> None:
    settings = Settings(mongo_host="mongo", mongo_root_user="ra dar", mongo_root_password="p@ss")

    assert settings.mongo_url == "mongodb://ra%20dar:p%40ss@mongo:27017/?authSource=admin"


def test_secrets_not_exposed_in_repr() -> None:
    settings = Settings(mongo_root_password="segredo-mongo", rabbitmq_password="segredo-rabbit")

    assert "segredo-mongo" not in repr(settings)
    assert "segredo-rabbit" not in repr(settings)


def test_cors_origins_default_is_local_frontend() -> None:
    assert Settings().cors_origins == ["http://localhost:3000"]


def test_cors_origins_read_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000/, https://radar.exemplo.com.br")

    # espaços e a barra final são removidos: o navegador manda a origem sem barra
    assert Settings().cors_origins == ["http://localhost:3000", "https://radar.exemplo.com.br"]


@pytest.mark.parametrize("value", ["", " , ", "*", "http://localhost:3000,*"])
def test_invalid_cors_origins_fail_clearly(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("CORS_ORIGINS", value)

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert exc_info.value.errors()[0]["loc"][0] == "cors_origins"
