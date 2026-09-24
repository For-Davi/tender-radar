"""Ambiente do Alembic: diz como conectar e quais modelos comparar.

Duas formas de rodar:
- linha de comando (`alembic upgrade head`): conecta usando Settings (variáveis de ambiente);
- testes: passam uma conexão pronta em `config.attributes["connection"]`.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from radar.adapters.postgres.database import create_db_engine
from radar.adapters.postgres.models import SCHEMA, Base
from radar.config import Settings

config = context.config

# os testes desligam isto para o Alembic não reconfigurar os logs do pytest
if config.config_file_name and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# os modelos que o autogenerate compara com o banco real
target_metadata = Base.metadata


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    """Só olha o schema da aplicação: tabelas de outros schemas não são nossas."""
    if type_ == "schema":
        return name == SCHEMA
    return True


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        compare_type=True,  # detecta mudança de tipo de coluna, não só coluna nova
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        run_migrations(connection)
        return

    engine = create_db_engine(Settings())
    try:
        with engine.connect() as conn:
            run_migrations(conn)
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Modo offline (--sql) não é usado neste projeto: rode com o banco no ar.")
run_migrations_online()
