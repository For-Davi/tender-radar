"""Tradução de erros do Postgres para erros do domínio.

O Postgres identifica cada tipo de erro por um código de 5 caracteres (SQLSTATE).
Usar o código, e não o texto da mensagem, é estável entre versões e idiomas.
"""

from typing import NoReturn

from sqlalchemy.exc import IntegrityError

from radar.domain.errors import DuplicateEntityError, ReferenceNotFoundError

UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"


def raise_as_domain_error(exc: IntegrityError) -> NoReturn:
    """Relança o erro de integridade como erro de domínio, quando há equivalente.

    Outros erros (ex.: CHECK violado) não são traduzidos de propósito: significam
    que um dado inválido passou pelo domínio, ou seja, um bug que deve aparecer.
    """
    sqlstate = getattr(exc.orig, "sqlstate", None)
    if sqlstate == UNIQUE_VIOLATION:
        raise DuplicateEntityError(str(exc.orig)) from exc
    if sqlstate == FOREIGN_KEY_VIOLATION:
        raise ReferenceNotFoundError(str(exc.orig)) from exc
    raise exc
