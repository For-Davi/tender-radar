"""Portas de persistência: o que o domínio e os serviços precisam, sem dizer COMO.

São `Protocol`s (tipagem estrutural): qualquer classe com esses métodos satisfaz a
interface, sem precisar herdar dela. O adapter do Postgres implementa estes
contratos, e um fake em memória também pode implementar, nos testes dos serviços.

Semântica comum:
- `add`: insere; se a chave natural já existe -> `DuplicateEntityError`.
- `upsert`: insere ou atualiza pela chave natural (idempotente: rodar 2x = 1 registro).
- `get`: devolve a entidade ou `None`.
- Referência a entidade inexistente -> `ReferenceNotFoundError`.
- O repositório não faz commit: quem chama decide o limite da transação.
"""

from typing import Protocol

from radar.domain.entities import Contratacao, Fornecedor, Orgao
from radar.domain.value_objects import Cnpj


class OrgaoRepository(Protocol):
    def add(self, orgao: Orgao) -> None: ...
    def upsert(self, orgao: Orgao) -> None: ...
    def get(self, cnpj: Cnpj) -> Orgao | None: ...


class FornecedorRepository(Protocol):
    def add(self, fornecedor: Fornecedor) -> None: ...
    def upsert(self, fornecedor: Fornecedor) -> None: ...
    def get(self, documento: str) -> Fornecedor | None: ...


class ContratacaoRepository(Protocol):
    """A contratação é salva junto com os itens (é a raiz do agregado)."""

    def add(self, contratacao: Contratacao) -> None: ...
    def upsert(self, contratacao: Contratacao) -> None: ...
    def get(self, numero_controle_pncp: str) -> Contratacao | None: ...
