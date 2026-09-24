"""Conexão com o Postgres: engine e fábrica de sessões.

- Engine: guarda o pool de conexões. Uma por processo.
- Session: uma "conversa" com o banco (uma unidade de trabalho). Uma por requisição/tarefa.
"""

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from radar.config import Settings

# driver psycopg 3 (o SQLAlchemy usaria o psycopg2, legado, com "postgresql://")
_DRIVER = "postgresql+psycopg"


def build_url(settings: Settings) -> URL:
    """Monta a URL a partir das partes; o URL.create codifica caracteres especiais da senha."""
    return URL.create(
        _DRIVER,
        username=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )


def create_db_engine(settings: Settings) -> Engine:
    # pool_pre_ping: testa a conexão antes de usar (evita erro após o banco reiniciar)
    return create_engine(build_url(settings), pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False: objetos continuam legíveis depois do commit
    return sessionmaker(bind=engine, expire_on_commit=False)
