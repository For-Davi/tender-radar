# ADR 0006 — API REST de leitura: CQRS leve, silver + gold, id público e problem+json

- **Status:** aceito
- **Data:** 2026-09-24
- **Etapa:** 05

## Contexto

O frontend (Etapa 06) precisa de uma API para:

- listar e filtrar contratações;
- ver o detalhe de cada uma;
- listar órgãos;
- ler as métricas analíticas.

Havia quatro questões em aberto:

1. **Modelo de leitura.** Os repositórios da Etapa 01 gravam e leem o agregado inteiro,
   como entidade de domínio. A entidade não tem o nome do órgão nem o do fornecedor, e
   listar 20 contratações carregaria todos os itens de cada uma.
2. **Silver ou gold.**
   - A silver está sempre atualizada, porque o pipeline grava nela.
   - A gold só muda quando alguém roda `make dbt` (ADR 0005), mas tem os cálculos
     prontos.
3. **Identificador na URL.**
   - O `id` numérico é interno (ADR 0002).
   - O número de controle do PNCP (`...-000173/2025`) tem uma `/`.
4. **Contrato com o dbt.** A gold é criada pelo dbt, e não pelas migrações do backend.
   Nada impede um modelo do dbt de mudar uma coluna que a API lê.

## Decisão

1. **CQRS leve.**
   - Ports de leitura próprios: `ports/consultas.py` (silver) e `ports/metricas.py` (gold).
   - Eles devolvem *read models*: dataclasses imutáveis com exatamente o que a tela usa.
   - Os adapters usam SQL Core (colunas escolhidas, joins explícitos), e não o ORM.
   - Os repositórios da Etapa 01 continuam só para escrita.
2. **Cada dado vem da camada certa.**
   - Contratações e órgãos vêm da **silver**.
   - Métricas e categorias vêm da **gold**.
   - O filtro `categoria` usa a mesma regra do dbt, aplicada na silver:
     `left(ncm_nbs, 2)` com `EXISTS`.
   - Se a gold não existir (SQLSTATE `42P01`/`3F000`), a API responde **503** com
     `Retry-After`, e não 500. As rotas da silver continuam funcionando.
3. **Id público = número de controle com `-` no lugar de `/`.**
   - É reversível, estável e o mesmo número que o PNCP mostra.
   - Um id malformado dá **422** (`Path(pattern=...)`); um id válido que não existe dá **404**.
4. **Paginação por offset**, com o envelope
   `{itens, total, pagina, tamanho_pagina, total_paginas}`.
   - O tamanho máximo é 100.
   - Uma página além da última devolve 200 com `itens: []`.
   - Toda ordenação termina no `id`, para desempatar de forma estável.
   - Nulos (sigilosos) ficam por último nos dois sentidos.
5. **Validação na borda com Pydantic**, usando modelos de query
   (`Annotated[Params, Query()]`).
   - Regras de um campo ficam em `AfterValidator`: UF, CNPJ (com o value object do
     domínio), capítulo.
   - Regras entre campos ficam em `model_validator`: datas e valores invertidos.
   - As datas de filtro são dias de **Brasília**, convertidos para um intervalo
     meio-aberto em UTC.
6. **Erros em `application/problem+json` (RFC 9457)**, para 404, 405, 422, 503 e 500.
   - O 422 lista cada campo inválido em `erros`.
   - O 500 não expõe a mensagem interna; ela vai para o log.
   - No OpenAPI, os erros são documentados só como problem+json.
7. **Dinheiro sai como texto decimal**, sempre com 4 casas: o `Dinheiro` do domínio
   arredonda os totais calculados e as somas da gold.
8. **CORS** com as origens vindas de `CORS_ORIGINS` (padrão `http://localhost:3000`).
   Só `GET`; `*` é recusado na configuração.
9. **Injeção com `Depends`.**
   - `create_app(settings, engine=None)` cria o engine e a fábrica de sessões. O
     `lifespan` libera o engine no fim, mas só se foi a app que o criou.
   - Há uma sessão por requisição.
   - Os testes trocam os ports por fakes com `dependency_overrides`.
10. **Contrato API × gold.**
    - `adapters/postgres/gold.py` descreve só as colunas que a API lê, como `Table`s
      num `MetaData` separado (fora do Alembic).
    - Os testes de integração criam a gold a partir dessa descrição.
    - O teste de contrato (`tests/contract/`, marcador `contract`) roda no job `dbt`
      do CI, depois do `dbt build`. Ele compara colunas e tipos com as tabelas reais e
      executa cada consulta.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Reusar `ContratacaoRepository.get` e as entidades | Faltam nomes de órgão e fornecedor; listar carregaria agregados inteiros |
| Contratações lidas da `fato_contratacao_item` | Defasagem até o próximo `make dbt`; o grão é de item, e não de contratação |
| `id` numérico da silver na URL | Detalhe interno; muda se o banco for recriado e quebra links salvos |
| `{id:path}` com a barra original | O `%2F` é decodificado antes do roteamento; a URL fica ambígua e frágil |
| Paginação por cursor (keyset) | Melhor em volumes grandes, mas não dá "página X de Y". Com ~100 contratações, o offset basta |
| Endpoints `async` com asyncpg | Outra pilha de driver e sessão, sem ganho neste volume; o FastAPI roda os `def` num threadpool |
| Formato de erro próprio | O RFC 9457 é padrão, tem content-type próprio e é reconhecido por clientes HTTP |
| Gold só descrita nos testes | O dbt poderia mudar uma coluna sem ninguém perceber; o contrato no CI pega isso |
| `contract: enforced` nos modelos do dbt | Também resolveria, mas mexe na Etapa 04 e só protege o lado do dbt. Fica como próximo passo |

## Consequências

- **Positivas:**
  - o frontend recebe tipos estáveis, documentados e validados no OpenAPI;
  - os filtros são testados contra o SQL real (fuso, nulos, empates);
  - a API continua útil mesmo sem a gold;
  - uma mudança no dbt que quebre a API derruba o CI.
- **Negativas:**
  - há mais tipos para manter (read model + schema de resposta);
  - a descrição da gold duplica nomes de coluna do dbt, embora o contrato vigie a
    divergência.
- **A observar:**
  - com milhares de contratações por dia, o `count(*)` do total e o `OFFSET` alto
    ficam caros; aí, trocar para keyset e total estimado;
  - o filtro de categoria por `left(ncm_nbs, 2)` não usa índice. Se ficar lento,
    criar um índice de expressão ou uma coluna do capítulo.
