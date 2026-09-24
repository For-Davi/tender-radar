# Etapa 04 — Camada analítica com dbt (gold)

## O que foi construído (visão geral em 1 parágrafo)

Um projeto **dbt** (`dbt/`) transforma a silver (normalizada, boa para gravar) numa
camada **gold** (dimensional, boa para analisar):

- views de **staging**, que padronizam e calculam;
- um **star schema**, com a fato `fato_contratacao_item` e 4 dimensões;
- **4 marts** com funções de janela:
  - variação de preço mês a mês (`LAG`);
  - ranking de fornecedores por órgão (`RANK`);
  - média móvel de 3 meses;
  - percentil do preço do item na categoria (`PERCENT_RANK`), a base do sobrepreço.

Tudo é testado de três formas:

- **genéricos**: chaves únicas, não nulas, relacionamentos e valores aceitos;
- **singulares em SQL**: reconciliação e regras;
- **unit tests** do dbt, com entrada e saída escritas à mão, validados por mutação.

Roda com `make dbt` e no CI. Como os dados reais não traziam categoria útil, a silver
passou a guardar o código **NCM**, que virou a base da dimensão de categoria.

## Como a lógica funciona (passo a passo, com trechos curtos de código)

```
silver (Etapa 03)            staging (views)            gold (tabelas)
 orgao ───────────────────> stg_orgao ────────────────> dim_orgao
 fornecedor ──────────────> stg_fornecedor ───────────> dim_fornecedor
 contratacao ─────────────> stg_contratacao ──┐          dim_tempo  (generate_series)
 item_contratacao ────────> stg_item ─────────┼───────> dim_categoria  <── seed ncm_capitulos
        seed unidades_sinonimos ──┘            └───────> fato_contratacao_item
                                                           ├─> mart_preco_categoria_mensal   (LAG)
                                                           ├─> mart_ranking_fornecedor_orgao (RANK)
                                                           ├─> mart_valor_contratado_mensal  (média móvel)
                                                           └─> mart_percentil_preco_item     (PERCENT_RANK)
```

### 1. Staging: padronizar sem mudar o grão

Cada `stg_*` é 1 para 1 com uma tabela da silver: renomeia colunas, traduz códigos para
nomes e calcula o que é derivado. Dois cuidados:

```sql
-- stg_contratacao: o "dia" da publicação é o dia em Brasília, não em UTC
(data_publicacao at time zone 'America/Sao_Paulo')::date as data_publicacao_local
```

Publicado às 22h de 31/03 em Brasília é 01h de 01/04 em UTC. Sem essa conversão, o
item cairia no mês errado.

```sql
-- stg_item: unidade padronizada = sinônimo do seed, ou a forma base da macro
coalesce(sinonimos.unidade, itens.unidade_base) as unidade_normalizada
```

Nos dados reais, 10 variantes (`UND`, `UN`, `UNIDADE (UN)`, `EMBALAGEM 1.0 UNIDADE`...)
viraram `UNIDADE`, que reúne 537 itens.

### 2. Star schema

- **Grão da fato: 1 linha por item de contratação.** É a primeira decisão de qualquer
  modelo dimensional: todas as medidas (quantidade, preço, total) valem para esse grão.
- **Dimensões** respondem "quem, o quê, quando": órgão, fornecedor, categoria e tempo.
- **Dimensões degeneradas** (modalidade, UF, número de controle) ficam na própria fato,
  porque não têm atributos que justifiquem uma tabela.
- **Chaves substitutas** vêm de `md5(chave natural)`. A fato e a dimensão calculam a
  mesma chave sem precisar de join, e ela não muda entre rebuilds.

```sql
-- macro categoria_key: usada na dim_categoria E na fato (tem que dar o mesmo valor)
md5({{ material_ou_servico }} || '|' || coalesce({{ ncm_capitulo }}, '--'))
```

O `coalesce` é necessário porque `md5(NULL)` é NULL e a chave não pode ser nula.

A `dim_tempo` sai do próprio Postgres, com um dia por linha de 2021 até o fim do ano
que vem:

```sql
generate_series(date '2021-01-01', <fim do ano que vem>, interval '1 day')
```

### 3. As funções de janela, com entrada e saída

Uma **função de janela** calcula um valor para cada linha olhando para outras linhas
relacionadas, a "janela", **sem juntar as linhas** como o `GROUP BY` faz. A janela é
definida por `OVER (PARTITION BY ... ORDER BY ... [ROWS ...])`:

- `PARTITION BY` separa os grupos, cada um com seu cálculo;
- `ORDER BY` ordena dentro do grupo;
- `ROWS` limita quantas linhas entram no cálculo.

#### LAG: variação mês a mês (`mart_preco_categoria_mensal`)

`LAG(x)` devolve o valor de `x` na **linha anterior** da partição.

```sql
lag(mes) over janela as mes_da_linha_anterior,
lag(preco_mediano) over janela as preco_da_linha_anterior
...
window janela as (partition by categoria_key, unidade_normalizada order by mes)
```

| categoria | unidade | mês | mediana | LAG(mediana) | variação |
|---|---|---|---|---|---|
| A | UNIDADE | jan | 15,00 | — (1ª linha) | nula |
| A | UNIDADE | fev | 16,50 | 15,00 | **+10,00%** |
| A | UNIDADE | abr | 12,00 | 16,50 (de fev!) | **nula** |
| A | CAIXA | fev | 50,00 | — (outra partição) | nula |

A armadilha está na linha de abril. `LAG` olha a *linha* anterior, não o *mês*
anterior: sem itens em março, a linha anterior a abril é fevereiro. Por isso o mart
só calcula a variação quando `mes_da_linha_anterior = mes - 1 mês`.

#### RANK: ranking de fornecedores por órgão (`mart_ranking_fornecedor_orgao`)

```sql
rank() over (partition by orgao_key order by valor_total_homologado desc) as ranking,
round(valor_total_homologado
      / nullif(sum(valor_total_homologado) over (partition by orgao_key), 0) * 100, 2)
```

| órgão | fornecedor | valor | RANK | DENSE_RANK | ROW_NUMBER | participação |
|---|---|---|---|---|---|---|
| O1 | F1 | 1000 | 1 | 1 | 1 | 40% |
| O1 | F2 | 1000 | 1 | 1 | 2 (arbitrário) | 40% |
| O1 | F3 | 500 | **3** | 2 | 3 | 20% |
| O2 | F1 | 50 | 1 | 1 | 1 | 100% |

- O `RANK` dá a mesma posição aos empatados e **pula** as seguintes. É o ranking de
  pódio: não existe 2º lugar se dois empataram em 1º.
- O `SUM(...) OVER (PARTITION BY orgao_key)` põe o total do órgão em cada linha, sem
  `GROUP BY`, o que permite calcular a participação na mesma consulta.

#### Média móvel de 3 meses (`mart_valor_contratado_mensal`)

```sql
avg(valor) over (order by mes rows between 2 preceding and current row) as media_movel_3m
```

| mês | valor | janela (3 linhas) | média móvel | meses na média |
|---|---|---|---|---|
| jan | 300 | jan | 300 | 1 |
| fev | **0** (mês vazio, preenchido) | jan, fev | 150 | 2 |
| mar | 600 | jan, fev, mar | 300 | 3 |
| abr | 300 | fev, mar, abr | **300** | 3 |

- `ROWS BETWEEN 2 PRECEDING` conta **linhas**. Se fevereiro não existisse como linha,
  a janela de abril seria jan, mar e abr, e a média daria **400**, sobre um período
  de 4 meses chamado de "3".
- Por isso o mart primeiro monta todos os meses a partir da `dim_tempo` e usa 0 onde
  não houve contratação.
- Confirmei com uma mutação: removendo o preenchimento, o unit test falha mostrando
  exatamente 400 em vez de 300.

#### PERCENT_RANK: percentil do preço (`mart_percentil_preco_item`)

`PERCENT_RANK = (posição − 1) / (linhas da partição − 1)`: 0 é o mais barato e 1 o
mais caro.

| grupo | preço | posição | PERCENT_RANK | itens comparáveis | alerta (≥ 0,9) |
|---|---|---|---|---|---|
| A/UNIDADE | 10 | 1 | 0,00 | 5 | não |
| A/UNIDADE | 20 | 2 | 0,25 | 5 | não |
| A/UNIDADE | 30 | 3 | 0,50 | 5 | não |
| A/UNIDADE | 40 | 4 | 0,75 | 5 | não |
| A/UNIDADE | 50 | 5 | 1,00 | 5 | **sim** |
| B/UNIDADE | 1000 | 2 | 1,00 | 2 | não (amostra < 5) |
| S (sem NCM) | 500 | 5 | 1,00 | 5 | não (sem categoria) |

O alerta só vale se a comparação faz sentido: categoria com NCM e ao menos 5 itens
comparáveis (`var('min_itens_comparaveis')`).

## Decisões e alternativas (por que assim e não de outro jeito)

Resumo; o detalhe está no [ADR 0005](../adr/0005-dbt-camada-gold.md).

| Decisão | Alternativa descartada | Por quê |
|---|---|---|
| Projeto dbt separado | Dependência do backend | Conflitos de dependências; deploys acoplados |
| Staging em view, gold em tabela | Tudo em view | A API recalcularia as janelas a cada leitura |
| Chave `md5(chave natural)` | `id` da silver | Estável e independente do banco transacional |
| FK de fornecedor nula | "Membro desconhecido" | 98% dos itens não têm vencedor ainda |
| `generate_series` e `md5` | Pacote `dbt_utils` | Sem `dbt deps` (rede) no build e no CI |
| Categoria por capítulo do NCM | `itemCategoriaNome` / palavra-chave | O campo do PNCP vem sempre vazio; palavra-chave é frágil |
| Comparar preço por categoria **e** unidade | Só por categoria | R$/unidade e R$/caixa não são comparáveis |
| Mediana | Só média | Um preço absurdo puxa a média, mas quase não move a mediana |
| Alerta só com NCM e amostra ≥ 5 | Alerta para todos | Nos dados reais, 70 "alertas" eram só itens caros por natureza; ficaram 15 |

**Mudança em relação ao plano:** o alerta de percentil passou a exigir categoria
classificada. O motivo foi a validação com dados reais (ver acima); o teste foi escrito
antes da mudança.

## Conceitos novos (explicação didática de cada conceito/biblioteca usada)

- **dbt (data build tool):** cada modelo é um `SELECT` num arquivo `.sql`. O dbt cria a
  view ou tabela, descobre a ordem pelas dependências (`ref()` e `source()`), roda os
  testes e gera documentação com a linhagem. Principais comandos:
  - `dbt build`: seeds, modelos e testes, na ordem certa;
  - `dbt test`: só os testes;
  - `dbt docs generate` / `dbt docs serve`: a documentação navegável.
- **`source()` e `ref()`:** `source('silver', 'orgao')` aponta para uma tabela que o dbt
  **não** cria. `ref('stg_orgao')` aponta para um modelo do projeto, e é isso que monta
  o grafo de dependências.
- **Seed:** um CSV versionado no repositório que o dbt carrega como tabela
  (`dbt seed`). Serve para dados de referência pequenos e editáveis (capítulos do NCM,
  sinônimos de unidade).
- **Macro (Jinja):** uma função que gera SQL. Por exemplo, `normalizar_unidade(col)`
  vira uma expressão com `regexp_replace`, e `categoria_key(...)` garante que a fato e
  a dimensão calculam a mesma chave.
- **Modelagem dimensional (Kimball):**
  - a **fato** guarda eventos mensuráveis num **grão** definido;
  - as **dimensões** descrevem o contexto (quem, o quê, quando);
  - o **star schema** é a fato no centro e as dimensões em volta, com consultas de
    poucos joins.
  - Contraste com a 3FN da silver: a 3FN evita redundância para *gravar*; o star
    schema aceita alguma redundância para *ler* rápido e de forma simples.
- **Funções de janela:** ver a seção acima. A diferença para o `GROUP BY` é que a
  janela **mantém todas as linhas**.
- **Três tipos de teste no dbt:**
  - *genérico*: uma regra reutilizável aplicada a uma coluna no YAML;
  - *singular*: um `SELECT` que devolve as linhas que violam a regra; o teste passa
    quando não volta nada;
  - *unit test*: entrada fixa (`given`) e saída esperada (`expect`) para um modelo,
    sem depender dos dados reais. É o equivalente dbt de um teste unitário do pytest.
- **Teste de mutação:** quebrar a regra de propósito e confirmar que o teste falha.
  Prova que o teste testa alguma coisa.
- **NCM:** Nomenclatura Comum do Mercosul, o código de 8 dígitos de toda mercadoria.
  Os 2 primeiros formam o **capítulo** (30 = farmacêuticos, 90 = instrumentos
  médicos...).

## Testes (o que cada teste verifica e por que ele importa)

**dbt:** `dbt build` = 87 nós, todos verdes.

| Tipo | Quantos | O que prova |
|---|---|---|
| Genéricos nas sources e seeds | 13 + 4 | A silver cumpre o que a gold assume (ids únicos, FK item → contratação); capítulos e variantes sem repetição |
| Genéricos em staging e gold | 15 + 32 | Chaves únicas e não nulas em cada dimensão e na fato; `relationships` da fato para as 4 dimensões; `accepted_values` para modalidade, UF, esfera, tipo de pessoa e material/serviço |
| Singulares (`tests/`) | 4 | Mart mensal reconcilia com a fato; nenhum preço, quantidade ou total negativo; percentil em [0, 1]; **fato tem exatamente os itens da silver** (nenhum perdido em join, nenhum duplicado) |
| Unit tests | 4 | `LAG` só compara com o mês imediatamente anterior; média móvel conta mês vazio como 0; `RANK` com empate (1, 1, 3) e participação; `PERCENT_RANK` por grupo, amostra mínima e sem alerta fora de categoria classificada |

Os unit tests foram **validados por mutação**:

- sem a checagem de mês, o teste do `LAG` falha;
- sem o preenchimento de meses, o da média móvel falha, mostrando 400 em vez de 300.

**Backend (NCM na silver):** 17 testes unitários novos (329 no total) e 1 de integração
(62 no total).

- Normalização do NCM: com máscara, só o capítulo, número JSON, NBS com 9 dígitos, e
  códigos inválidos viram nulo.
- Domínio: o formato é validado.
- Transformação: um NCM inválido não rejeita o item.
- Mapper e integração: o código é gravado limpo no banco.

**CI:** job `dbt` com Postgres de serviço, migrações do backend e `dbt build`.
Simulado localmente num banco vazio: 87 de 87.

## Como rodar e ver funcionando (comandos exatos)

```bash
make migrate              # aplica a 0004 (NCM)
make pipeline-completo    # reprocessa a silver para preencher o NCM dos itens antigos
make dbt                  # silver -> gold (seeds + modelos + testes), no container
make dbt-test             # só os testes
make dbt-docs             # documentação e linhagem em http://localhost:8080
```

Fora do Docker, rodando da pasta `dbt/`:

```bash
cd dbt && set -a && . ../.env && set +a
uv run dbt build --select mart_preco_categoria_mensal+   # um modelo e o que depende dele
uv run dbt test --select test_type:unit                  # só os unit tests
```

Conferir no banco (`docker compose exec postgres psql -U radar -d radar`):

```sql
select count(*) from gold.fato_contratacao_item;           -- = silver.item_contratacao
select categoria_nome, count(*) from gold.fato_contratacao_item
  join gold.dim_categoria using (categoria_key) group by 1 order by 2 desc;
select * from gold.mart_valor_contratado_mensal;
select * from gold.mart_ranking_fornecedor_orgao order by orgao_key, ranking;
select * from gold.mart_percentil_preco_item where acima_p90;
```

**Execução real** (2026-09-24):

| Item | Resultado |
|---|---|
| Fato | 1.010 itens, igual à silver |
| Órgãos | 45, igual à silver |
| Fornecedores | 3 |
| Categorias | 10: "Material sem classificação" 688, "Serviço sem classificação" 116, "90 - Instrumentos médicos" 112, "30 - Farmacêuticos" 81... |
| Mês | 1 só (setembro/2026): 114 contratações, R$ 148,9 milhões estimados |
| Ranking | 3 linhas (2 órgãos) |
| Percentil | 700 itens com preço conhecido, 15 alertas |

## Erros comuns e como depurar

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `relation "silver.item_contratacao" does not exist` | Migrações não aplicadas no banco | `make migrate` |
| `column "ncm_nbs" does not exist` | Falta a migração 0004 | `make migrate` |
| Unit test: `each UNION query must have the same number of columns` | Linhas do `given`/`expect` com colunas diferentes | Todas as linhas com as mesmas chaves (use `null`) |
| Unit test: `300.0 → 300.00` | O YAML leu o número como float | Escreva decimais como texto: `"300.00"` |
| Unit test com linhas `+++` a mais | O `expect` não listou todas as linhas da saída | Liste todas (o teste compara o conjunto inteiro) |
| `relationships` falhando na fato | A chave foi calculada diferente na fato e na dimensão | Use a mesma macro (`categoria_key`) nos dois lugares |
| Schema `gold_staging` em vez de `staging` | Faltou o macro `generate_schema_name` | Ver `macros/generate_schema_name.sql` |
| Unidade nova aparecendo crua | Variante nova sem sinônimo | Adicionar em `seeds/unidades_sinonimos.csv` e rodar `make dbt` |
| Gold desatualizada | O dbt não roda sozinho | `make pipeline && make dbt` |

## Perguntas de revisão

1. Qual é o grão da `fato_contratacao_item`? Por que ele precisa ser decidido **antes**
   das medidas?
2. Por que `LAG` sozinho dá uma variação errada quando falta um mês? Como o mart evita
   isso?
3. Se a série mensal não fosse preenchida com os meses vazios, qual seria a média móvel
   de abril no exemplo (jan 300, mar 600, abr 300)? Por quê?
4. Qual a diferença entre `RANK`, `DENSE_RANK` e `ROW_NUMBER` com dois empatados em 1º?
5. Por que o alerta de percentil exige categoria classificada e amostra mínima? Que
   limitação ainda sobra para a Etapa 09?
