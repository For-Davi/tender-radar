"""Configuração da aplicação, lida exclusivamente de variáveis de ambiente (12-factor).

Cada campo de `Settings` corresponde a uma variável de ambiente com o mesmo nome
em maiúsculas (ex.: `log_level` <- `LOG_LEVEL`). Valores inválidos geram um
`ValidationError` na inicialização, apontando o campo com problema: é melhor a
aplicação nem subir do que rodar com configuração errada.
"""

from typing import Literal
from urllib.parse import quote

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    """Configurações tipadas e validadas da aplicação."""

    # frozen: depois de criadas, as settings não podem ser alteradas no meio do código
    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    app_name: str = "radar"
    environment: Environment = "dev"
    log_level: LogLevel = "INFO"
    log_json: bool = False  # True em container: um JSON por linha, fácil de indexar

    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_user: str = "radar"
    postgres_password: SecretStr = SecretStr("radar")  # SecretStr esconde o valor em logs/repr
    postgres_db: str = "radar"

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        """Aceita `info`, `Info` etc.; a validação do Literal acontece depois."""
        return value.upper() if isinstance(value, str) else value

    @property
    def postgres_dsn(self) -> str:
        """URL de conexão do Postgres, com usuário e senha codificados para URL."""
        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password.get_secret_value(), safe="")
        return (
            f"postgresql://{user}:{password}@{self.postgres_host}:{self.postgres_port}"
            f"/{self.postgres_db}"
        )
