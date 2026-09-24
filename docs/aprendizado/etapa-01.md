# Etapa 01 — Domínio e modelo relacional

## O que foi construído (visão geral em 1 parágrafo)

O coração do sistema: as **entidades de negócio** (Órgão, Fornecedor, Contratação e Item)
com suas regras, e o **banco relacional** onde elas são gravadas. O domínio é Python puro
(dataclasses), valida CNPJ (inclusive o novo alfanumérico), CPF e dinheiro exato, e não sabe
que banco existe. O adapter do Postgres traduz essas entidades para 4 tabelas normalizadas
no schema `silver`, com chaves, FKs, índices e `CHECK`s, criadas por uma migração
versionada do Alembic. A gravação é idempotente (`upsert`): gravar a mesma contratação duas
vezes não duplica nada, o que a ingestão do PNCP (Etapa 02) vai precisar.

## Como a lógica funciona (passo a passo, com trechos curtos de código)

O caminho de uma contratação, do objeto em memória até a tabela:

```
Contratacao (domain) ──> SqlContratacaoRepository ──> mappers ──> SQL ──> silver.contratacao
      ▲                        (adapter)                                   silver.item_contratacao
      └── implementa o Protocol ContratacaoRepository (ports)
```

### 1. Value objects: `domain/value_objects.py`

Um *value object* é um valor imutável que se valida sozinho ao ser criado. Se existe um
`Cnpj` em memória, ele é válido.

```python
@dataclass(frozen=True, slots=True)
class Cnpj:
    value: str

    def __post_init__(self) -> None:
        normalized = _strip_mask(self.value)  # tira . / - e espaços, põe em maiúsculas
        if not _is_valid_cnpj(normalized):
            raise InvalidValueError(f"CNPJ inválido: {self.value!r}")
        object.__setattr__(self, "value", normalized)
```

- `frozen=True`: não dá para alterar depois de criado. Por isso a normalização usa
  `object.__setattr__`, o único jeito de gravar dentro do próprio `__post_init__`.
- Como a classe guarda o valor já normalizado, `Cnpj("11.222.333/0001-81") == Cnpj("11222333000181")`.

**Dígito verificador do CNPJ** (vale para o numérico e o alfanumérico): cada caractere
vale `ASCII − 48` (`'0'`→0, `'9'`→9, `'A'`→17). Multiplica pelos pesos, soma, pega o resto
por 11. Resto < 2 → dígito 0; senão, 11 − resto. O primeiro dígito usa os 12 primeiros
caracteres; o segundo usa os 12 + o primeiro dígito.

**`Dinheiro`** guarda um `Decimal` com 4 casas e **recusa `float`**:

```python
Dinheiro.de("0.1") + Dinheiro.de("0.2") == Dinheiro.de("0.3")  # True
0.1 + 0.2 == 0.3  # False com float!
Dinheiro.de(0.1)  # InvalidValueError: use str, int ou Decimal, nunca float
```

### 2. Entidades: `domain/entities.py`

Dataclasses cujas regras rodam no `__post_init__`:

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class ItemContratacao:
    ...

    def __post_init__(self) -> None:
        if quantidade <= 0:
            raise BusinessRuleError(f"quantidade deve ser positiva: {quantidade}")
        _non_negative(self.valor_unitario_estimado, "valor_unitario_estimado")
        if (self.fornecedor_documento is None) != (
            self.valor_unitario_homologado is None
        ):
            raise BusinessRuleError("... devem vir juntos (resultado do item)")

    @property
    def valor_total_estimado(self) -> Dinheiro:  # calculado, nunca guardado
        return self.valor_unitario_estimado * self.quantidade
```

A `Contratacao` é a **raiz do agregado**: os itens só entram por `add_item`, que recusa
número de item repetido. `itens` é uma tupla, então quem lê não consegue dar `append` e
pular a validação. `ano` e `sequencial` são extraídos do número de controle
(`11222333000181-1-000123/2025`) e nunca podem divergir dele.

Dois tipos de erro, com significados diferentes:
- `InvalidValueError`: **formato** errado (CNPJ com dígito errado, UF inexistente);
- `BusinessRuleError`: formato certo, mas **regra** violada (quantidade zero, valor negativo).

### 3. Ports: `ports/repositories.py`

Interfaces (`Protocol`) do que o sistema precisa da persistência:

```python
class ContratacaoRepository(Protocol):
    def add(
        self, contratacao: Contratacao
    ) -> None: ...  # duplicado -> DuplicateEntityError
    def upsert(self, contratacao: Contratacao) -> None: ...  # idempotente
    def get(self, numero_controle_pncp: str) -> Contratacao | None: ...
```

Os serviços das próximas etapas dependem **disto**, não do Postgres. Nos testes deles,
um repositório em memória com esses três métodos serve.

### 4. Modelos ORM: `adapters/postgres/models.py`

As tabelas, descritas em Python (SQLAlchemy 2.0, estilo `Mapped[...]`):

```python
class ContratacaoModel(_AuditMixin, Base):
    __tablename__ = "contratacao"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    numero_controle_pncp: Mapped[str] = mapped_column(String(30), unique=True)
    orgao_id: Mapped[int] = mapped_column(ForeignKey(OrgaoModel.id), index=True)
    valor_total_estimado: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    orgao: Mapped[OrgaoModel] = relationship(lazy="raise")
```

- `Mapped[Decimal | None]` → coluna que aceita NULL; `Mapped[str]` → `NOT NULL`.
- Os `CHECK` de modalidade e situação são **gerados a partir dos Enums** (`_in_check`), então
  domínio e banco nunca divergem na lista de códigos.
- A `NAMING_CONVENTION` dá nomes previsíveis às constraints (`uq_orgao_cnpj`,
  `fk_contratacao_orgao_id`...). Sem ela, o Postgres inventa nomes, e uma migração futura
  não conseguiria achar a constraint para alterar ou remover.

### 5. Mappers: `adapters/postgres/mappers.py`

Funções puras de conversão, nos dois sentidos:

```python
contratacao_values(contratacao, orgao_id) -> dict   # entidade -> colunas (para INSERT)
contratacao_to_domain(model) -> Contratacao          # modelo carregado -> entidade
```

Na volta (`to_domain`), as regras do domínio rodam de novo: um dado corrompido no banco
vira erro, e não uma entidade inválida circulando pelo sistema.

### 6. Repositórios: `adapters/postgres/repositories.py`

**Upsert atômico** com o `ON CONFLICT` do Postgres:

```python
stmt = pg_insert(model).values(rows)
stmt.on_conflict_do_update(
    index_elements=["numero_controle_pncp"],  # a chave natural (UNIQUE)
    set_={col: stmt.excluded[col] for col in ...} | {"atualizado_em": func.now()},
)
```

`excluded` é a linha que tentou entrar. No conflito, o Postgres copia os valores dela para
a linha existente. Tudo acontece num único comando, sem corrida entre dois workers.

**Savepoint + tradução de erro**, em todas as escritas:

```python
@contextmanager
def _savepoint(self) -> Iterator[None]:
    try:
        with self._session.begin_nested():  # SAVEPOINT
            yield
    except IntegrityError as exc:
        raise_as_domain_error(
            exc
        )  # 23505 -> DuplicateEntityError, 23503 -> ReferenceNotFound
```

Se uma escrita falha, só o savepoint é desfeito: a transação de quem chamou continua viva.
Na Etapa 03, isso permite registrar um registro ruim como rejeitado e seguir com o lote.

**O upsert da contratação sincroniza os itens**: grava os que vieram e **apaga os que não
vieram mais** (o agregado é a fonte da verdade). Tudo no mesmo savepoint: se um item
referencia um fornecedor inexistente, nem a contratação fica gravada.

**Leitura** com carregamento explícito, porque os relacionamentos são `lazy="raise"`:

```python
select(ContratacaoModel).options(
    joinedload(ContratacaoModel.orgao),  # JOIN
    selectinload(ContratacaoModel.itens).joinedload(
        ItemContratacaoModel.fornecedor
    ),  # 2ª consulta
)
```

### 7. Migração: `backend/alembic/`

- `env.py` pega a conexão de `Settings`. Nos testes, recebe uma conexão pronta via
  `config.attributes["connection"]`.
- `versions/0001_schema_inicial.py` foi **gerada** com `alembic revision --autogenerate`
  (o Alembic compara os modelos com o banco e escreve a diferença) e **revisada à mão**:
  o autogenerate não cria o schema, então acrescentei `CREATE SCHEMA` e `DROP SCHEMA`.
- No Compose, o serviço `migrate` roda `alembic upgrade head` e termina. A API só sobe
  depois que ele termina com sucesso (`service_completed_successfully`).

## Decisões e alternativas (por que assim e não de outro jeito)

As decisões estruturais estão no [ADR 0002](../adr/0002-dominio-separado-do-orm.md), e o
modelo completo, com a normalização explicada, está em [modelo-relacional.md](../modelo-relacional.md).

| Decisão | Alternativa | Por quê |
|---|---|---|
| Aceitar **CNPJ alfanumérico** | Só dígitos (o plano original rejeitava letras) | Desde julho de 2026 a Receita emite CNPJs com letras (IN RFB 2.229/2024); rejeitá-los descartaria órgãos e fornecedores válidos. Conferido com o exemplo oficial `12.ABC.345/01DE-35` |
| `Dinheiro` com **4 casas** e `ROUND_HALF_EVEN` | 2 casas e `ROUND_HALF_UP` | Preço unitário do PNCP pode ter fração de centavo (R$ 0,0345); o "meio para o par" (ABNT NBR 5891) não puxa somas grandes para cima |
| **`Cpf` também** (fornecedor PF) | Só `Cnpj` | O PNCP tem fornecedores pessoa física; sem isso a Etapa 03 rejeitaria dados válidos |
| Escrita com **SQL Core**, leitura com **ORM** | Tudo pelo ORM (`session.add`/`merge`) | O `merge` do ORM faz SELECT e depois INSERT/UPDATE (duas idas ao banco e condição de corrida); o `ON CONFLICT` é uma ida só e atômico |
| **`add` e `upsert`** separados | Só `upsert` | O `add` diz "isto é novo; se já existe, é erro". É útil quando duplicar indica problema, e é o que permite testar a tradução do erro de `UNIQUE` |
| **`populate_existing`** nos `get` | Nada | O upsert em SQL Core não atualiza objetos já carregados na sessão. Hoje isso não causa bug (ver "Erros comuns"), mas a opção deixa a garantia explícita |
| **Serviço `migrate`** separado | Rodar a migração no startup da API | Com 2 réplicas da API, as duas tentariam migrar ao mesmo tempo. Um passo único antes é o padrão mais seguro |
| **Um banco novo por teste de migração** | Reusar o banco dos testes de repositório | Os testes de migração derrubam o schema (`downgrade base`); isolar evita um teste quebrar o outro |

## Conceitos novos (explicação didática de cada conceito/biblioteca usada)

- **Ports & adapters (arquitetura hexagonal)**: o núcleo (domínio) define *portas*
  (interfaces) do que precisa; o mundo externo entra por *adaptadores* que implementam
  essas portas. A dependência aponta **para dentro**: `adapters` importa `domain`, nunca o
  contrário. Trocar Postgres por outro banco = escrever outro adapter.
- **Padrão Repository**: um objeto que "parece uma coleção" de entidades (`add`, `get`),
  escondendo o SQL. Quem usa pensa em `Contratacao`, não em tabelas.
- **Entidade × value object**: a entidade tem identidade que persiste mesmo se os dados
  mudam (a contratação `...-000123/2025` continua sendo ela mesma se o objeto muda). O value
  object é definido só pelo conteúdo (dois `Dinheiro("10")` são intercambiáveis).
- **Agregado e raiz do agregado**: grupo de objetos tratado como uma unidade (contratação +
  itens). Só a raiz é acessada de fora, e ela garante as regras do grupo (item único).
- **Normalização (1FN–3FN)**: organizar as tabelas para cada fato ficar em um lugar só;
  detalhes em [modelo-relacional.md](../modelo-relacional.md).
- **Chave natural × chave substituta**: a natural vem do negócio (CNPJ); a substituta é
  um número gerado pelo banco (`id`). Aqui a substituta é a PK e a natural é `UNIQUE`.
- **Integridade referencial (FK)**: o banco impede referência a algo que não existe e
  define o que acontece ao apagar (`RESTRICT` bloqueia; `CASCADE` apaga junto).
- **Índice**: estrutura (árvore B) que faz o banco achar linhas sem ler a tabela inteira,
  como o índice remissivo de um livro. Custa espaço e deixa a escrita um pouco mais lenta,
  então vai só nas colunas muito usadas em filtro (`orgao_id`, `data_publicacao`, `uf`).
  `UNIQUE` cria um índice automaticamente.
- **Migrações versionadas (Alembic)**: cada mudança no banco é um arquivo com `upgrade()`
  e `downgrade()`, numerado e commitado. A tabela `alembic_version` guarda em que versão o
  banco está; `alembic upgrade head` aplica o que falta.
- **Upsert (`ON CONFLICT DO UPDATE`)**: "insira; se a chave já existir, atualize". É a base
  da idempotência.
- **Savepoint**: um "ponto de restauração" dentro de uma transação; dá para desfazer até
  ele sem perder o resto.
- **SQLSTATE**: código padrão de 5 caracteres para cada tipo de erro SQL (`23505` = unique,
  `23503` = FK, `23514` = check). É estável entre versões e idiomas, ao contrário do texto
  da mensagem.
- **Identity map**: a sessão do SQLAlchemy guarda no máximo um objeto por linha do banco.
  Se você carregar a mesma contratação duas vezes, recebe o mesmo objeto.
- **Problema N+1 e `lazy="raise"`**: carregar 100 contratações e acessar `.orgao` em cada
  uma faria 1 + 100 consultas escondidas. Com `lazy="raise"`, esse acesso vira erro, e o
  código precisa declarar o carregamento (`joinedload`/`selectinload`).
- **`Protocol` (tipagem estrutural)**: uma classe satisfaz a interface se tiver os métodos
  certos, sem herdar dela. O mypy confere.

## Testes (o que cada teste verifica e por que ele importa)

**Unitários novos — 100 testes, sem banco**

| Arquivo | Qtde | O que prova |
|---|---|---|
| `test_cnpj_cpf.py` | 24 | CNPJ/CPF válidos com e sem máscara; **CNPJ alfanumérico** (exemplo oficial da Receita, minúsculas aceitas); rejeita dígito errado, tamanho errado, dígitos repetidos, letra no dígito verificador e caractere estranho; formatação com máscara; igualdade entre com e sem máscara; imutabilidade |
| `test_dinheiro.py` | 22 | `0,1 + 0,2 == 0,3` exato; aceita `str`, `int` e `Decimal`; **recusa `float` e `bool`**; recusa texto inválido, `NaN` e `Infinity`; arredondamento meio-para-o-par em 4 casas; multiplicação, soma de lista, subtração, comparação; hashable e imutável |
| `test_entities.py` | 40 | Códigos do PNCP viram enums (e código desconhecido é recusado); órgão e fornecedor normalizam o documento conforme o tipo de pessoa; item: quantidade > 0, valores ≥ 0, total calculado, resultado completo ou ausente; contratação: número de controle (inclusive alfanumérico), UF, data com fuso, valor sigiloso (`None`), item duplicado (no construtor e no `add_item`), `itens` somente leitura |
| `test_postgres_mappers.py` | 11 | Ida e volta domínio → modelo → domínio sem perder nada (Decimal exato, resultado do item, fornecedores PJ/PF/estrangeiro); colunas derivadas (`ano`, `sequencial`); tradução de SQLSTATE: 23505 e 23503 viram erro de domínio, **23514 não é escondido** |
| `test_database.py` | 3 | URL com driver psycopg 3, senha com caracteres especiais codificada, senha fora do `repr` |

**Integração novos — 25 testes, Postgres real**

| Arquivo | Qtde | O que prova |
|---|---|---|
| `test_migrations.py` | 4 | `upgrade head` cria as 4 tabelas; `downgrade base` remove tudo (inclusive o schema); subir de novo funciona; **a migração bate com os modelos** (se alguém mudar um modelo e esquecer a migração, falha) |
| `test_repositories.py` | 21 | Ida e volta real de cada entidade; `get` inexistente → `None`; `add` duplicado → `DuplicateEntityError`; **a sessão continua usável após o erro** (savepoint); `upsert` 2x = 1 linha, com valores atualizados; upsert sincroniza itens (remove os que saíram); contratação de órgão inexistente e item de fornecedor inexistente → `ReferenceNotFoundError`, **sem gravar nada pela metade**; `CHECK` do banco barra valor negativo mesmo via SQL direto; `CASCADE` apaga itens; `RESTRICT` protege o órgão; leitura após upsert na mesma sessão não vem desatualizada |

**Totais do projeto:** 121 unitários (cobertura 87%) + 29 de integração.

**Verificações manuais** (saídas reais):

```
$ make up                               → migrate: Exited (0); api: healthy
$ docker compose logs migrate           → Running upgrade  -> 0001, Schema inicial da camada silver...
$ psql ... "\dt silver.*"               → contratacao | fornecedor | item_contratacao | orgao
$ psql ... "select version_num from alembic_version"   → 0001
$ make migrate                          → nada a aplicar (idempotente), exit 0
```

## Como rodar e ver funcionando (comandos exatos)

```bash
make up                         # sobe tudo; o serviço migrate aplica as migrações
docker compose logs migrate     # vê a migração rodando
docker compose exec postgres psql -U radar -d radar -c "\dt silver.*"
docker compose exec postgres psql -U radar -d radar -c "\d silver.item_contratacao"

make check                      # lint + tipos + unitários + cobertura
make test-integration           # migrações e repositórios com Postgres real

make migrate                    # aplica migrações pendentes
make migration m="adiciona coluna x"   # gera a próxima migração (0002_...) a partir dos modelos
```

Brincar com o domínio no terminal:

```bash
cd backend && uv run python
>>> from radar.domain.value_objects import Cnpj, Dinheiro
>>> Cnpj("12.abc.345/01de-35").formatted()
'12.ABC.345/01DE-35'
>>> Dinheiro.de("0.1") + Dinheiro.de("0.2")
Dinheiro(valor=Decimal('0.3000'))
>>> Dinheiro.de(0.1)
radar.domain.errors.InvalidValueError: Dinheiro: use str, int ou Decimal, nunca float/bool (0.1)
```

## Erros comuns e como depurar

| Sintoma | Causa provável | Como resolver |
|---|---|---|
| `sqlalchemy.exc.InvalidRequestError: 'ContratacaoModel.itens' is not available due to lazy='raise'` | Acessou um relacionamento sem carregá-lo | Adicione `joinedload`/`selectinload` na consulta. É o `lazy="raise"` evitando um N+1 escondido |
| `test_models_match_migrations` falha | Um modelo mudou e a migração não | `make migration m="..."`, **revise** o arquivo gerado e commite |
| `alembic upgrade` diz "Can't locate revision" | O banco está numa versão que não existe no código (ex.: migração apagada) | Nunca apague uma migração já aplicada; em dev, `make down-volumes && make up` recomeça do zero |
| `migrate` sai com erro e a API não sobe | Migração com erro, ou Postgres inacessível | `docker compose logs migrate` mostra o traceback |
| Autogenerate gera migração vazia ou com tabelas de outros schemas | `include_name` filtra só o schema `silver` | Confira se o modelo herda de `Base` e se está importado em `models.py` |
| `DuplicateEntityError` inesperado na ingestão | Usou `add` onde deveria usar `upsert` | Para dados que podem chegar de novo (PNCP), use `upsert` |
| Um teste do projeto falhou por esperar o valor errado | Aconteceu nesta etapa: `test_contratacao_add_item_and_total` esperava 0,5, mas a fábrica usa quantidade 10, e o certo era 1,4 | O código estava certo; o teste passou a declarar a quantidade que supõe. Lição: fábricas de teste escondem valores, então declare no teste os campos que o `assert` usa |

**Uma investigação que vale registrar:** suspeitei que o `get` depois de um upsert (SQL
Core) na mesma sessão devolveria dados antigos, por causa do identity map. Escrevi o teste
de regressão e rodei **sem** a correção: ele passou. O motivo é que o identity map guarda
**referências fracas**. Como o repositório converte o modelo para entidade e o descarta, o
Python o libera, e o próximo SELECT monta objetos novos. O `populate_existing` ficou como
garantia explícita, e o teste ficou como proteção do comportamento. Lição: um teste de
regressão precisa **falhar sem a correção**; se não falha, você ainda não entendeu o bug.

## Perguntas de revisão

1. Por que `Contratacao.itens` é uma tupla e os itens só entram por `add_item`? Que regra
   seria possível burlar se `itens` fosse uma lista pública?
2. A tabela `contratacao` tem uma PK `id` e um `UNIQUE` em `numero_controle_pncp`. Qual o
   papel de cada um? O que aconteceria com a ingestão sem o `UNIQUE`?
3. O domínio já recusa valor negativo. Por que o banco também tem um `CHECK` para isso?
   Qual teste prova que ele funciona?
4. No `upsert` da contratação, o que acontece com um item que existia no banco e não veio
   na nova versão? Por que essa é a escolha certa para um agregado?
5. Por que `Dinheiro.de(0.1)` é recusado, se `0.1` "parece" um número normal? O que
   `Decimal(0.1)` devolveria?
