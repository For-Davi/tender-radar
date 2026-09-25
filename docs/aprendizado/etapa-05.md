# Etapa 05 — API REST

## O que foi construído (visão geral em 1 parágrafo)

Uma API REST de leitura em FastAPI expõe os dados para o frontend:

- as **contratações**, com filtros combináveis, paginação, ordenação e detalhe com itens
  e vencedores;
- os **órgãos**;
- as **categorias**;
- as **métricas** dos marts do dbt.

Contratações e órgãos vêm da silver, que está sempre atualizada. Métricas e categorias
vêm da gold, que fica pronta para análise.

Todo erro sai no formato padrão `application/problem+json`, o CORS libera só o
frontend, e as dependências entram por `Depends`. Os testes cobrem três níveis:

- **unitários**, com fakes;
- **integração**, com Postgres real;
- **contrato**, que roda no CI depois do `dbt build` e garante que as colunas lidas pela
  API existem de verdade na gold.

## Como a lógica funciona (passo a passo, com trechos curtos de código)

```
requisição HTTP
   │
   ▼
rota (api/routers)  ── valida a query com Pydantic (422 se inválida)
   │   pede o port por Depends
   ▼
port de leitura (ports/consultas.py, ports/metricas.py)   ← nos testes: fake em memória
   │
   ▼
adapter SQL (adapters/postgres/consultas.py → silver, gold.py → gold)
   │   devolve read models (dataclasses)
   ▼
schema de resposta (api/schemas) ── converte, põe rótulos, id público
   │
   ▼
JSON (ou problem+json, se deu erro)
```

### 1. A query string vira um objeto validado

```python
class ContratacoesParams(PaginacaoParams):
    uf: UfParam | None = None                  # AfterValidator: maiúscula e está em UFS
    orgao: CnpjParam | None = None             # usa o value object Cnpj do domínio
    categoria: CapituloParam | None = None     # pattern ^\d{2}$
    data_inicio: date | None = None
    ...
    @model_validator(mode="after")
    def _intervalos_coerentes(self) -> Self: ...   # data_inicio <= data_fim etc.

@router.get("")
def listar_contratacoes(params: Annotated[ContratacoesParams, Query()], queries: ContratacaoQueriesDep):
```

Se algo estiver errado, o FastAPI nem chama a função: lança `RequestValidationError`, e
o handler monta o 422.

### 2. O filtro vira SQL

Cada filtro presente vira uma condição:

```python
if filtro.categoria is not None:
    # EXISTS: entra se ALGUM item for do capítulo, sem duplicar a contratação
    conditions.append(
        exists().where(
            I.contratacao_id == C.id, func.left(I.ncm_nbs, 2) == filtro.categoria
        )
    )
if filtro.data_fim is not None:
    conditions.append(
        C.data_publicacao < inicio_do_dia(filtro.data_fim + timedelta(days=1))
    )
```

**O fuso.** Uma contratação publicada às 23h30 de 10/03 em Brasília está gravada como
02h30 de 11/03 em UTC.

- `inicio_do_dia` monta 00:00 **de Brasília**, e o Postgres compara em UTC.
- Com isso, `data_fim=2025-03-10` inclui essa contratação.
- O intervalo é meio-aberto, `[início do 1º dia, início do dia seguinte ao último)`.
  Não perde o `23:59:59.999` e usa o índice da coluna.

### 3. Ordenar e paginar

```python
case Ordenacao.VALOR_DESC:
    return (C.valor_total_estimado.desc().nulls_last(), C.id.desc())
...
.limit(pedido.tamanho).offset(pedido.offset)     # offset = (pagina - 1) * tamanho
```

**O desempate por `id`.** Sem ele, duas contratações com a mesma data podem trocar de
lugar entre uma requisição e outra, e uma delas apareceria em duas páginas enquanto a
outra sumiria. O Postgres não garante nenhuma ordem entre linhas empatadas.

O total vem de um `count(*)` com as **mesmas** condições. O envelope calcula
`total_paginas` com uma divisão arredondada para cima, sem float:
`-(-total // tamanho)`.

### 4. O read model vira JSON

```python
class ContratacaoResponse(BaseModel):
    id: str  # "…-000173-2025" (a "/" virou "-")
    modalidade: int
    modalidade_nome: str  # "Pregão eletrônico" (api/rotulos.py)
    valor_total_estimado: Decimal | None  # JSON: "1500.0000" (texto), null = sigiloso
```

O Pydantic serializa `Decimal` como **texto**. É de propósito: o `number` do JSON vira
um float de 64 bits no JavaScript, e `0.1 + 0.2 != 0.3`.

### 5. Erros no formato problem+json

```json
{"type": "about:blank", "title": "Unprocessable Entity", "status": 422,
 "detail": "parâmetros inválidos", "instance": "/contratacoes",
 "erros": [{"campo": "query.uf", "mensagem": "UF inválida: 'XX'"}]}
```

Os handlers ficam em `api/errors.py`:

| Handler | Status | O que faz |
|---|---|---|
| HTTP | 404, 405 | Mantém o header `Allow` do 405 |
| Validação | 422 | Lista cada campo inválido em `erros` |
| Gold ausente | 503 | Manda `Retry-After: 60` |
| Qualquer outra exceção | 500 | A mensagem vai só para o log |

### 6. Injeção de dependência

```python
def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:  # uma por requisição
        yield session


def get_contratacao_queries(session: SessionDep) -> ContratacaoQueries:
    return SqlContratacaoQueries(session)


ContratacaoQueriesDep = Annotated[ContratacaoQueries, Depends(get_contratacao_queries)]
```

Nos testes, basta uma linha para trocar a implementação:

```python
app.dependency_overrides[get_contratacao_queries] = lambda: fake_contratacoes
```

## Decisões e alternativas (por que assim e não de outro jeito)

Resumo; o detalhe está no [ADR 0006](../adr/0006-api-rest-leitura.md).

| Decisão | Alternativa descartada | Por quê |
|---|---|---|
| Ports de leitura com read models (CQRS leve) | Reusar os repositórios e as entidades | A entidade não tem nomes de órgão e fornecedor; listar carregaria todos os itens |
| Contratações da silver, métricas da gold | Tudo da gold | A gold só atualiza no `make dbt` |
| Id público com `-` no lugar de `/` | `id` numérico; `{id:path}` | O numérico é interno e muda se o banco for recriado; o `%2F` vira `/` antes do roteamento |
| Paginação por offset com `total` | Cursor (keyset) | O dashboard precisa de "página X de Y"; o volume é pequeno |
| Endpoints `def` (síncronos) | `async def` + asyncpg | Seria outra pilha de banco, sem ganho aqui |
| problem+json (RFC 9457) | Formato próprio | É padrão, com content-type próprio |
| Gold ausente → 503 | Deixar virar 500 | Não é bug: o dbt só não rodou. 503 com `Retry-After` diz "tente depois" |
| Contrato API × gold no CI | Confiar nos testes de integração | Eles usam a mesma descrição da API, então nunca veriam uma divergência com o dbt |

**Mudanças descobertas na execução real** (cada uma ganhou antes um teste que a
reproduzia):

- a mensagem do 422 saía como `"Value error, UF inválida: 'XX'"`. Agora sai só o texto
  do nosso `ValueError`;
- as somas de dinheiro da gold vinham com 8 casas (`"148851981.78880000"`, de
  `quantidade × preço`). Agora passam pelo `Dinheiro` e ficam com 4.

## Conceitos novos (explicação didática de cada conceito/biblioteca usada)

### REST

- **Design REST:** cada *recurso* tem uma URL (`/contratacoes`, `/contratacoes/{id}`),
  e o método HTTP diz a ação (`GET` = ler). Os filtros de uma coleção vão na *query
  string*. O status diz o resultado:
  - 200: ok;
  - 404: o recurso não existe;
  - 405: método não permitido;
  - 422: a entrada é inválida;
  - 503: indisponível no momento;
  - 500: bug.
- **404 × 422 × lista vazia:**
  - `GET /contratacoes/{id}` com um id que não existe dá **404**: o recurso não existe;
  - com um id malformado dá **422**: a *pergunta* está errada;
  - `GET /contratacoes?uf=RJ` sem resultados dá **200 com lista vazia**: a coleção
    existe, só não tem nada nesse filtro.
- **Paginação por offset:** `LIMIT tamanho OFFSET (pagina - 1) * tamanho`. É simples e
  permite pular direto para uma página. O custo cresce com o offset, porque o banco lê
  e descarta as linhas puladas. A alternativa para volumes grandes é o *keyset*
  ("depois do id X").

### Leitura e arquitetura

- **CQRS (Command Query Responsibility Segregation):** o modelo de escrita, que valida e
  protege regras, é separado do modelo de leitura, feito para exibir. Aqui a versão é
  "leve": o mesmo banco, com classes e consultas diferentes.
- **Read model:** um dataclass com o formato de que a tela precisa (ex.:
  `ContratacaoResumo`, com a razão social do órgão já junto).

### FastAPI e Pydantic

- **Injeção de dependência com `Depends`:** a rota declara do que precisa, e o FastAPI
  monta isso para cada requisição. Com `dependency_overrides`, o teste troca a peça sem
  alterar a rota.
- **Modelo de query do FastAPI:** `Annotated[ContratacoesParams, Query()]` transforma
  todos os campos de um modelo Pydantic em parâmetros de query, com validação e
  documentação.
- **`AfterValidator` e `model_validator`:**
  - o primeiro valida **um** campo depois da conversão de tipo;
  - o segundo roda depois de todos os campos e valida regras entre eles.
  - O `model_validator` só roda se cada campo for válido. Por isso `uf=XX` com as datas
    invertidas mostra só o erro da UF.
- **OpenAPI:** o FastAPI gera o schema (`/openapi.json`) e a tela `/docs` a partir dos
  tipos. O teste `test_api_openapi.py` valida o schema com o `openapi-spec-validator`,
  porque o frontend vai gerar tipos TypeScript a partir dele.

### HTTP

- **Problem Details (RFC 9457):** o formato padrão de erro HTTP, com `type`, `title`,
  `status`, `detail` e `instance`, e o content-type `application/problem+json`.
- **CORS:** o navegador bloqueia uma página de `localhost:3000` que tente ler a resposta
  de `localhost:8000` (outra *origem*), a menos que a API autorize com o header
  `Access-Control-Allow-Origin`.
  - Em requisições "não simples", o navegador manda antes um **preflight** (`OPTIONS`)
    perguntando se pode.
  - O CORS protege o **usuário**, e não a API: `curl` ignora CORS.
- **SQLSTATE:** o código de erro padrão do Postgres. `42P01` = tabela não existe.
  `3F000` = schema não existe.

### Testes

- **Teste de contrato:** verifica o acordo entre duas partes que evoluem separadas.
  Aqui, a API (que lê) e o dbt (que cria a tabela).
- **Teste de mutação:** quebrar o código de propósito e confirmar que algum teste falha.
  Foi feito três vezes nesta etapa:
  - trocar o fuso de Brasília por UTC: 3 testes de filtro de data falharam;
  - remover o `NULLS LAST`: o teste de ordenação falhou;
  - renomear uma coluna em `gold.py`: o contrato falhou com "colunas que a API lê e o
    dbt não gera".

## Testes (o que cada teste verifica e por que ele importa)

**Unitários** (462 no total, 133 novos; cobertura 87,5%), sem banco:

| Arquivo | O que prova |
|---|---|
| `test_api_contratacoes.py` | Cada parâmetro vira o `FiltroContratacoes` certo, sozinho e combinado (UF em minúscula, CNPJ com máscara); padrões de página e ordenação; paginação na primeira, na última e além da última; 422 para cada parâmetro inválido e para intervalos invertidos, **sem chegar a consultar**; JSON completo do item e do detalhe; dinheiro como texto e sigiloso como `null`; 404 e 422 do detalhe |
| `test_api_orgaos.py` | Formato, filtro de UF normalizado, paginação, 422 |
| `test_api_metricas.py` | Formato de cada métrica; filtros; 422; **503 em todas as rotas da gold** quando ela não existe, sem vazar o nome da tabela |
| `test_api_errors.py` | problem+json em 404, 405 (com `Allow`) e 422; o 500 não vaza a mensagem interna, mas a registra no log; mensagens de 422 sem o prefixo do Pydantic; CORS: permite a origem configurada, recusa outra origem e outro método |
| `test_api_openapi.py` | O schema é OpenAPI 3.1 válido; todas as rotas estão documentadas; os erros aparecem só como problem+json; dinheiro é `string` no schema |
| `test_api_rotulos.py` | Todo membro de cada enum tem nome (um código novo daria 500) |
| `test_api_app.py` | O `lifespan` libera o engine da app e não libera o injetado; `42P01`/`3F000` viram "indisponível", mas outros erros SQL não são escondidos |
| `test_api_ids.py`, `test_consultas_ports.py` | Ida e volta do id público; offset e total de páginas; total do item calculado e nulo quando sigiloso |
| `test_config.py` (+6) | `CORS_ORIGINS` separado por vírgula; vazio e `*` recusados |

**Integração** (99 no total, 37 novos), com Postgres real:

- `test_api_contratacoes_db.py`: um cenário de 4 contratações com empate de data,
  sigiloso e publicação às 23h30 de Brasília.
  - Cada filtro no SQL real, inclusive a borda do fuso e a regra "sigiloso nunca entra
    em filtro de valor".
  - As ordenações com nulos no fim.
  - As páginas cobrem tudo uma vez só, mesmo com o limite da página caindo no meio de
    um empate.
  - O detalhe com vencedor.
  - Órgãos com contagem, filtro por UF e paginação.
- `test_api_metricas_db.py`: gold criada a partir de `gold.py`, com linhas escritas à
  mão.
  - Joins com as dimensões, filtros, ordenação e paginação dos alertas.
  - 503 sem a gold, enquanto as rotas da silver continuam de pé.
  - Dinheiro com 4 casas.

**Contrato** (9 testes, marcador `contract`): no job `dbt` do CI, depois do
`dbt build`.

- Cada tabela descrita em `gold.py` existe, tem as colunas que a API lê e cada coluna
  tem um tipo compatível.
- Cada consulta de métrica roda sobre as tabelas reais.

## Como rodar e ver funcionando (comandos exatos)

```bash
make up                 # a API sobe em http://localhost:8000
make pipeline && make dbt   # garante silver e gold atualizadas
make test-contract      # contrato API x gold (depois do make dbt)
```

Abra **http://localhost:8000/docs** para ver e testar todas as rotas. Pelo terminal:

```bash
curl "localhost:8000/contratacoes?tamanho_pagina=2"
curl "localhost:8000/contratacoes?uf=CE&categoria=30&valor_max=100000&ordenar=-valor_total_estimado"
curl "localhost:8000/contratacoes/07954480000179-1-024883-2026"
curl "localhost:8000/orgaos?uf=CE"
curl "localhost:8000/categorias"
curl "localhost:8000/metricas/valor-mensal"
curl "localhost:8000/metricas/precos-acima-p90?tamanho_pagina=5"
curl -i "localhost:8000/contratacoes?uf=XX"        # 422 em problem+json
```

**Execução real** (2026-09-24, dados da Etapa 04):

| Item | Resultado |
|---|---|
| `/contratacoes` | 114 contratações, 57 páginas de 2 |
| `/orgaos` | 45 órgãos (ESTADO DO CEARA com 49 contratações) |
| `/categorias` | 10 categorias |
| `/metricas/valor-mensal` | setembro/2026: 114 contratações, 1.010 itens, R$ 148.851.981,7888 |
| `/metricas/ranking-fornecedores` | 3 linhas (Granja: 97,59% e 2,41%; Ipu: 100%) |
| `/metricas/precos-acima-p90` | 15 alertas |
| CORS | Preflight de `localhost:3000` → 200 com `access-control-allow-origin` |

## Erros comuns e como depurar

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| 503 nas rotas `/metricas` e `/categorias` | A gold não existe (o dbt não rodou neste banco) | `make dbt` |
| Métricas desatualizadas | A gold só muda no `make dbt` | `make pipeline && make dbt` |
| 404 com um id copiado do PNCP | O id tem `/` | Troque a última `/` por `-` |
| 422 em `orgao` | CNPJ com dígito verificador errado | Confira o CNPJ; máscara é aceita |
| 422 com `campo: "query"` | Regra entre dois campos (datas ou valores invertidos) | Veja a `mensagem` |
| No navegador: "blocked by CORS policy" | A origem do frontend não está em `CORS_ORIGINS` | Ajuste o `.env` (sem `/` no fim) e reinicie a API |
| `make test-contract` falha com "não existe" | O dbt não rodou no banco do `.env` | `make dbt` antes |
| `make test-contract` falha com "colunas que a API lê e o dbt não gera" | Um modelo do dbt renomeou ou removeu a coluna | Ajuste `gold.py` **e** as consultas, ou reverta o dbt |
| 500 com "erro interno" | Bug ou banco fora do ar | `make logs s=api` e procure `erro_inesperado`: o traceback está lá |
| 500 com `KeyError` no log depois de um código novo do PNCP | Um enum ganhou um membro sem nome em `api/rotulos.py` | Some o nome; `test_api_rotulos.py` também acusa |

## Perguntas de revisão

1. Por que a API lê as contratações da silver e as métricas da gold? O que o usuário
   veria se as contratações viessem da `fato_contratacao_item`?
2. Uma contratação foi publicada às 23h30 de 31/03 em Brasília. Ela aparece com
   `data_fim=2025-03-31`? Explique o que `inicio_do_dia` e o intervalo meio-aberto
   fazem.
3. Por que toda ordenação termina em `id`? Descreva o que poderia acontecer entre a
   página 1 e a página 2 sem isso.
4. Qual a diferença entre responder 404, 422 e 200 com lista vazia? Dê um exemplo de
   requisição para cada um.
5. Os testes de integração criam a gold a partir de `gold.py`. Por que isso sozinho não
   protege contra uma mudança no dbt, e como o teste de contrato resolve?
