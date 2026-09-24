# ADR 0004 — Qualidade de dados e processamento incremental no bronze → silver

- **Status:** aceito
- **Data:** 2026-09-24
- **Etapa:** 03

## Contexto

A bronze (MongoDB) guarda o JSON do PNCP como veio, com uma versão por conteúdo
distinto. A silver (Postgres) precisa de dados limpos e confiáveis para a API, o dbt e
o modelo de sobrepreço. Os dados reais mostraram problemas concretos:

- orçamento sigiloso chega como `0`;
- textos com espaços sobrando e o marcador `"Não se aplica"` no lugar da categoria;
- datas sem fuso;
- valores como float JSON;
- vários resultados por item, alguns cancelados;
- códigos que o domínio não conhecia (`esferaId: "N"`).

## Decisão

1. **Validação em duas camadas.**
   - O Pydantic cuida de formato e completude, e aponta o caminho do campo
     (`contratacao.orgaoEntidade.cnpj`).
   - As entidades do domínio cuidam das regras de negócio.
   - Funções puras de normalização rodam antes das duas (`BeforeValidator`).
2. **Unidade de rejeição.**
   - Se falha um campo da contratação, a contratação inteira é rejeitada.
   - Se falha um item ou o resultado dele, só o item é rejeitado.
   - Toda rejeição vai para `silver.registros_rejeitados` com:
     - um motivo codificado (`campo_invalido`, `regra_negocio`, `item_duplicado`,
       `resultado_invalido`, `persistencia`);
     - os detalhes em JSONB;
     - o hash da versão da bronze (linhagem).
3. **Desconhecido é `NULL`, nunca `0`.** Item sigiloso fica com o valor estimado nulo.
   Um total 0 com todos os itens sigilosos também fica nulo.
4. **Divergência de totais é métrica, não rejeição.** Quando a soma dos itens difere
   do total da contratação em mais de 1%, o caso é contado como `inconsistentes`,
   porque a divergência existe na própria fonte.
5. **Processamento incremental por `vigente_desde`.**
   - Cada versão da bronze tem o instante em que virou a atual.
   - A execução lê o intervalo `(marca, agora − 1 min]` e grava a marca nova em
     `silver.pipeline_watermark`, no mesmo commit do último lote.
   - A cada 100 versões há um commit parcial, para não perder o progresso.
   - Se o processo cai, a marca não avança e o período é relido. Isso é seguro porque
     tudo é idempotente: upsert pela chave natural e rejeição única.
6. **Job sob demanda** (`make pipeline`; `--completo` reprocessa tudo).

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Rejeitar a contratação inteira por qualquer item ruim | Mais "puro", mas perde dados bons (1 item ruim em 200) |
| Só o domínio valida, sem Pydantic | As mensagens sairiam sem o caminho do campo e misturariam formato com regra de negócio |
| Gravar `0` com uma flag `orcamento_sigiloso` | Deixa uma armadilha para quem esquecer de filtrar: médias e sobrepreço envenenados |
| Marca d'água por `ultima_coleta` | Muda a cada coleta, mesmo sem mudança de conteúdo, e reprocessaria tudo sempre |
| Marca d'água por `primeira_coleta` | Perde o caso A → B → A: a volta para A não seria vista |
| Marca = maior `vigente_desde` processado, com commit por lote | Em empates de horário no limite de um lote, a próxima execução (`>` marca) pularia registros |
| Marca d'água no Mongo | Não participaria da transação do Postgres: dados e marca poderiam divergir |
| Modelar N resultados por item | Mais fiel ao registro de preços, mas muda o agregado e não é necessário até a Etapa 09. Hoje fica o 1º colocado |
| Disparar o pipeline por evento ou num loop | Mais peças. Fica para quando houver orquestração (Etapa 04) |

## Consequências

- **Positivas:**
  - a silver só tem dado válido;
  - todo descarte tem motivo consultável em SQL;
  - reprocessar é seguro;
  - uma regra corrigida se aplica ao histórico com `make pipeline-completo`;
  - a métrica de consistência já revelou um bug: a ingestão lia só 10 itens por
    contratação (ver `docs/pncp-api.md`).
- **Negativas:**
  - uma contratação rejeitada numa versão nova mantém na silver a última versão válida,
    que fica desatualizada até a fonte corrigir;
  - rejeições antigas ficam no histórico mesmo depois que uma versão nova é aceita.
- **A observar: códigos novos do PNCP.** Foi o caso do `esferaId "N"`.
  - O enum no Pydantic transforma o código novo em rejeição `campo_invalido`, e o lote
    segue.
  - A correção tem três passos: ajustar o enum, criar uma migração para o CHECK do
    banco e rodar o `make pipeline-completo`.
  - Se só o enum for ajustado, o CHECK do banco derruba a execução. Isso é intencional:
    CHECK violado não vira rejeição, porque indica bug, e ele precisa aparecer.
