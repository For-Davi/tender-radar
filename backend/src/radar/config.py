"""Configuração da aplicação, lida exclusivamente de variáveis de ambiente (12-factor).

Cada campo de `Settings` corresponde a uma variável de ambiente com o mesmo nome
em maiúsculas (ex.: `log_level` <- `LOG_LEVEL`). Valores inválidos geram um
`ValidationError` na inicialização, apontando o campo com problema: é melhor a
aplicação nem subir do que rodar com configuração errada.
"""

from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from radar.domain.entities import UFS
from radar.domain.enums import Modalidade

Environment = Literal["dev", "test", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# NoDecode: a lista vem do ambiente como texto "CE,SP" (e não como JSON); o validator divide
CommaList = Annotated[list[str], NoDecode]
CommaIntList = Annotated[list[int], NoDecode]


class Settings(BaseSettings):
    """Configurações tipadas e validadas da aplicação."""

    # frozen: depois de criadas, as settings não podem ser alteradas no meio do código
    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    app_name: str = "radar"
    environment: Environment = "dev"
    log_level: LogLevel = "INFO"
    log_json: bool = False  # True em container: um JSON por linha, fácil de indexar

    # ---------- API ----------
    # origens (esquema + host + porta) que o navegador pode usar para chamar a API
    cors_origins: CommaList = ["http://localhost:3000"]

    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_user: str = "radar"
    postgres_password: SecretStr = SecretStr("radar")  # SecretStr esconde o valor em logs/repr
    postgres_db: str = "radar"

    # ---------- MongoDB (camada bronze) ----------
    mongo_host: str = "localhost"
    mongo_port: int = Field(default=27017, ge=1, le=65535)
    # o mesmo usuário que a imagem do Mongo cria (MONGO_ROOT_*); em produção, um usuário só da app
    mongo_root_user: str = "radar"
    mongo_root_password: SecretStr = SecretStr("radar")
    mongo_db: str = "radar_bronze"

    # ---------- RabbitMQ ----------
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = Field(default=5672, ge=1, le=65535)
    rabbitmq_user: str = "radar"
    rabbitmq_password: SecretStr = SecretStr("radar")

    # ---------- API do PNCP ----------
    pncp_consulta_url: str = "https://pncp.gov.br/api/consulta"
    pncp_api_url: str = "https://pncp.gov.br/api/pncp"
    # a API de detalhes do PNCP já foi medida respondendo em ~33 s: 30 s estourava sempre
    pncp_timeout_seconds: float = Field(default=90.0, gt=0)
    pncp_max_attempts: int = Field(default=5, ge=1)
    pncp_min_interval_seconds: float = Field(default=0.2, ge=0)

    # ---------- Ingestão ----------
    ingestao_ufs: CommaList = ["CE"]
    ingestao_modalidades: CommaIntList = [6, 8]  # pregão eletrônico e dispensa
    ingestao_janela_dias: int = Field(default=2, ge=1)
    ingestao_intervalo_minutos: int = Field(default=60, ge=1)
    storage_dir: Path = Path("storage/editais")
    documento_max_bytes: int = Field(default=30 * 1024 * 1024, ge=1)

    @field_validator("ingestao_ufs", mode="before")
    @classmethod
    def _parse_ufs(cls, value: object) -> object:
        if isinstance(value, str):
            value = [uf.strip().upper() for uf in value.split(",") if uf.strip()]
        if isinstance(value, list):
            if not value:
                raise ValueError("informe ao menos uma UF")
            invalid = [uf for uf in value if uf not in UFS]
            if invalid:
                raise ValueError(f"UF(s) inválida(s): {invalid}")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            value = [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            if not value:
                raise ValueError("informe ao menos uma origem para o CORS")
            if "*" in value:
                # "*" liberaria qualquer site a ler a API pelo navegador do usuário
                raise ValueError("CORS com '*' não é permitido: liste as origens")
        return value

    @field_validator("ingestao_modalidades", mode="before")
    @classmethod
    def _parse_modalidades(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                value = [int(code) for code in value.split(",") if code.strip()]
            except ValueError as exc:
                raise ValueError(f"modalidades devem ser códigos numéricos: {value!r}") from exc
        if isinstance(value, list):
            valid = {m.value for m in Modalidade}
            invalid = [code for code in value if code not in valid]
            if not value or invalid:
                raise ValueError(f"modalidade(s) inválida(s): {invalid or value}")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        """Aceita `info`, `Info` etc.; a validação do Literal acontece depois."""
        return value.upper() if isinstance(value, str) else value

    @property
    def mongo_url(self) -> str:
        user = quote(self.mongo_root_user, safe="")
        password = quote(self.mongo_root_password.get_secret_value(), safe="")
        # authSource=admin: o usuário root é criado no banco "admin"
        return f"mongodb://{user}:{password}@{self.mongo_host}:{self.mongo_port}/?authSource=admin"

    @property
    def postgres_dsn(self) -> str:
        """URL de conexão do Postgres, com usuário e senha codificados para URL."""
        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password.get_secret_value(), safe="")
        return (
            f"postgresql://{user}:{password}@{self.postgres_host}:{self.postgres_port}"
            f"/{self.postgres_db}"
        )
