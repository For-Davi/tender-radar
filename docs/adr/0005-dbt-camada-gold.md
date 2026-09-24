# ADR 0005 — Camada gold com dbt: projeto separado, star schema e categoria por NCM

- **Status:** aceito
- **Data:** 2026-09-24
- **Etapa:** 04

## Contexto

A silver (Postgres, normalizada em 3FN) é boa para gravar e consultar uma contratação,
mas ruim para análise: toda pergunta ("preço mediano por categoria e mês") exige
vários joins e cálculos repetidos. A API (Etapa 05), o dashboard (06) e o modelo de
sobrepreço (09) precisam de dados prontos para análise, versionados e testados.

Os dados reais impuseram limites:

- `itemCategoriaNome` vem **sempre** "Não se aplica", e o `catalogo` vem sempre nulo.
  Só o código **NCM** classifica, e ele está em cerca de 20% dos itens.
- As unidades de medida são texto livre, com dezenas de variantes (`UND`,
  `UNIDADE (UN)`, `EMBALAGEM 1.0 UNIDADE`).
- Só há um mês de dados, e poucos itens homologados.

## Decisão

1. **dbt em um projeto próprio (`dbt/`)**, com uv, lock e imagem Docker separados do
   backend. Roda como job (`make dbt`) e no CI, com um Postgres de serviço.
2. **Camadas:**
   - `staging`, como views: renomeia, calcula totais, normaliza unidade e data local;
   - `gold`, como tabelas: star schema e marts.
   - Um macro deixa os nomes dos schemas exatamente `staging` e `gold`.
3. **Star schema:**
   - a fato `fato_contratacao_item` tem grão de 1 linha por item;
   - as dimensões são órgão, fornecedor, categoria e tempo;
   - chaves substitutas vêm de `md5(chave natural)`;
   - `fornecedor_key` fica nulo quando o item não tem vencedor.
4. **Categoria = tipo (material/serviço) + capítulo do NCM**, com nomes num seed. Para
   isso, a silver passou a guardar o NCM (migração 0004).
5. **Unidade normalizada** por macro (maiúsculas, sem acento, sem sigla entre
   parênteses, "EMBALAGEM 1.0 X" → X) mais um seed de sinônimos. Os preços só são
   comparados dentro da mesma categoria **e** da mesma unidade.
6. **Marts com janela:**
   - `LAG`, que só compara com o mês imediatamente anterior;
   - `RANK`, com empates;
   - média móvel sobre uma série mensal **sem buracos**;
   - `PERCENT_RANK`, com alerta só em categoria classificada e com amostra ≥ 5.
7. **Três tipos de teste:**
   - genéricos (`unique`, `not_null`, `relationships`, `accepted_values`);
   - singulares em SQL (reconciliação, sem negativos, percentil em [0, 1], fato
     igual à silver);
   - *unit tests* do dbt, com entrada e saída escritas à mão, nos 4 marts de janela.
     Foram validados por mutação: quebrar a regra faz o teste falhar.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| dbt como dependência do backend | O dbt-core fixa muitas dependências (conflitos) e acoplaria o deploy do SQL ao da API |
| Marts em views | Cada leitura da API recalcularia as janelas. Com tabelas, o custo fica no build |
| Marts como `incremental` | Complexidade desnecessária com milhares de linhas; `table` reconstrói tudo em cerca de 2 s |
| Chave = `id` da silver | Acopla a gold ao identificador interno do Postgres. O md5 da chave natural é estável e reproduzível |
| "Membro desconhecido" na dim_fornecedor | Padrão Kimball, mas 98% dos itens ficariam nele. FK nula + `relationships` (que ignora nulos) é mais simples |
| `dbt_utils` (date_spine, surrogate_key) | Exigiria `dbt deps` (rede) no build e no CI. `generate_series` e `md5` fazem o mesmo em poucas linhas |
| Categoria por palavra-chave na descrição | Frágil e difícil de testar. O NCM é oficial |
| Categoria pelo NCM completo (8 dígitos) | Fino demais para cerca de 1.000 itens (grupos de 1 ou 2). Fica para a Etapa 09, com mais dados |
| Unidade normalizada só por regex | Cada variante nova viraria código. O seed é editável e revisável |

## Consequências

- **Positivas:**
  - a API e o dashboard leem tabelas prontas;
  - cada regra analítica é testada com casos escritos à mão;
  - `dbt docs` mostra a linhagem silver → gold;
  - um erro clássico, a média móvel pulando meses vazios, é coberto por teste.
- **Negativas:**
  - mais um projeto Python e mais uma imagem;
  - a gold só atualiza quando se roda `make dbt`, pois não há orquestração.
- **A observar:**
  - com um único mês de dados, `LAG` e a média móvel ainda não mostram variação real;
  - o alerta de percentil por **capítulo** do NCM ainda aponta produtos caros por
    natureza (ex.: medicamentos de alto custo em "30 - Produtos farmacêuticos"). A
    Etapa 09 deve comparar num grão mais fino (NCM completo, semelhança de descrição).
