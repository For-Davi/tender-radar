"""Testes da montagem da conexão (sem abrir conexão: create_engine é preguiçoso)."""

from radar.adapters.postgres.database import build_url, create_db_engine, create_session_factory
from radar.config import Settings


def test_build_url_uses_psycopg3_driver_and_settings() -> None:
    url = build_url(Settings(postgres_host="db", postgres_port=6543, postgres_db="radar_x"))

    assert url.drivername == "postgresql+psycopg"
    assert (url.host, url.port, url.database) == ("db", 6543, "radar_x")


def test_build_url_escapes_password() -> None:
    url = build_url(Settings(postgres_password="p@ss/w:rd"))

    assert url.password == "p@ss/w:rd"  # valor original preservado
    assert "p%40ss%2Fw%3Ard@" in url.render_as_string(hide_password=False)


def test_engine_hides_password_in_repr() -> None:
    engine = create_db_engine(Settings(postgres_password="super-secreta"))

    assert "super-secreta" not in repr(engine)
    assert create_session_factory(engine).kw["bind"] is engine
