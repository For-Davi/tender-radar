# ADR 0002 — Entidades de domínio separadas dos modelos ORM

- **Status:** aceito
- **Data:** 2026-09-24
- **Etapa:** 01

## Contexto

O projeto precisa representar órgãos, fornecedores, contratações e itens com regras de
negócio (CNPJ válido, item sem valor negativo, número de item único na contratação) e
gravá-los no PostgreSQL. A arquitetura escolhida no `CLAUDE.md` é *ports & adapters*
(hexagonal): o domínio não pode importar nada de `adapters`.

Existem duas formas comuns de fazer isso com SQLAlchemy:

1. **Uma classe só**: o modelo ORM (`class Contratacao(Base)`) é também a entidade de negócio.
2. **Duas classes**: entidade de domínio (dataclass pura) + modelo ORM, com um *mapper*
   convertendo entre elas.

## Decisão

Usar **duas classes**:

- `radar.domain.entities`: dataclasses da biblioteca padrão, com as regras de negócio
  validadas na criação. Não conhecem banco, `id` numérico nem datas de auditoria.
- `radar.adapters.postgres.models`: modelos SQLAlchemy 2.0, com colunas, constraints e índices.
- `radar.adapters.postgres.mappers`: funções puras que convertem entre os dois.
- `radar.adapters.postgres.repositories`: implementam os `Protocol`s de `radar.ports` e
  **devolvem sempre entidades de domínio**, nunca modelos ORM.

Decisões ligadas a esta:

- **Chave substituta** (`id` gerado pelo banco) nas tabelas + `UNIQUE` na chave natural
  (CNPJ, número de controle). As FKs usam o `id`; a idempotência usa a chave natural.
- **Escritas com SQL Core** (`INSERT ... ON CONFLICT DO UPDATE`) e leituras com o ORM
  (`select` + `joinedload`/`selectinload`), com relacionamentos `lazy="raise"`.
- **Erros de banco traduzidos** para erros de domínio pelo código SQLSTATE
  (`23505` → `DuplicateEntityError`, `23503` → `ReferenceNotFoundError`).
- **Resultado do item** (fornecedor + valor homologado) como colunas do próprio item,
  supondo um vencedor por item.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Modelo ORM como entidade | O domínio passaria a depender do SQLAlchemy; as regras de negócio precisariam de banco (ou de sessão) para serem testadas; e o modelo carregaria detalhes de persistência (`id`, `criado_em`, relacionamentos lazy) para toda a aplicação |
| Mapeamento imperativo do SQLAlchemy (mapear a dataclass do domínio direto para a tabela) | Uma classe só, sem acoplar o código do domínio. Mas o SQLAlchemy instrumenta a classe em tempo de execução (atributos, estado), o que conflita com `frozen=True`/`slots=True` e torna o comportamento menos óbvio para quem está aprendendo |
| Pydantic para as entidades | Validação pronta e boa, mas prende o núcleo do sistema a uma biblioteca; dataclasses bastam para as regras atuais. Pydantic continua sendo usado nas bordas (config, API, eventos) |
| PK natural (o próprio CNPJ ou número de controle) | FKs mais largas (texto de 14 a 28 caracteres em toda linha de item) e presas a um formato externo, que já mudou uma vez (CNPJ alfanumérico em 2026) |
| Tabela `resultado_item` separada | Seria o modelo correto para vários vencedores por item, o que é raro no PNCP. Adiada até os dados reais (Etapa 02) mostrarem se é necessária |

## Consequências

- **Positivas:** as regras de negócio são testadas em milissegundos, sem banco (86 testes
  unitários de domínio); trocar o banco ou o ORM afeta só `adapters/postgres`; o resto do
  sistema só conhece erros de domínio.
- **Negativas:** há código a mais (os mappers) e, a cada campo novo, três lugares para
  mudar: entidade, modelo e mapper. Os testes de ida e volta (`test_postgres_mappers.py` e
  `test_contratacao_add_and_get_roundtrip`) existem para pegar um campo esquecido.
- **A observar:** se os dados reais mostrarem vários vencedores por item, criar
  `resultado_item` numa nova migração e ajustar entidade, modelo e mapper.
