"""Erros do domínio.

Quem usa o domínio (serviços, API, workers) captura estes erros, e nunca erros de
bibliotecas como SQLAlchemy ou psycopg. Os adapters traduzem os erros técnicos
para esta hierarquia.
"""


class DomainError(Exception):
    """Base de todos os erros de domínio."""


class InvalidValueError(DomainError, ValueError):
    """Valor com formato inválido (CNPJ, dinheiro, UF...)."""


class BusinessRuleError(DomainError):
    """Valor bem formado, mas que viola uma regra de negócio."""


class DuplicateEntityError(DomainError):
    """Já existe uma entidade com a mesma chave natural."""


class ReferenceNotFoundError(DomainError):
    """A entidade referencia outra que não existe (ex.: contratação de órgão não cadastrado)."""
