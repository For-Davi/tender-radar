# Etapa 03 — Pipeline bronze → silver com qualidade de dados

## O que foi construído (visão geral em 1 parágrafo)

Um **pipeline incremental** lê as versões novas da bronze (MongoDB), limpa e valida cada
contratação e grava o resultado nas tabelas da **silver** (Postgres), usando os
repositórios da Etapa 01.

- **Limpeza:** datas ganham o fuso de Brasília; valores viram `Decimal` exato;
  `"1.234,56"` é entendido; textos são aparados; `"Não se aplica"` vira nulo.
- **Rejeição:** o que não passa vai para `silver.registros_rejeitados` com o **motivo** e
  o **caminho do campo**, sem interromper o lote.
- **Incremental:** uma **marca d'água** lembra até onde a última execução chegou, então
  cada execução processa só o que é novo.
- **Relatório:** o fim de cada execução registra no log lidas, gravadas, rejeitadas,
  itens, inconsistentes e duração.

Os dados reais mudaram o plano em três pontos, cada um com teste antes da correção:

1. a ingestão da Etapa 02 lia **só 10 itens** por contratação (o PNCP pagina itens);
2. **orçamento sigiloso** chegava como `0` e agora é `NULL`;
3. órgãos com **esfera "N"** (consórcios públicos) eram recusados.

## Como a lógica funciona (passo a passo, com trechos curtos de código)

```
make pipeline
  └─ bronze_to_silver.main()                 (raiz de composição: Mongo + Postgres)
       └─ BronzeToSilverPipeline.run()
            ├─ marca = watermarks.get("bronze_to_silver")        (Postgres)
            ├─ para cada versão em bronze.versions_between(marca, agora - 1 min):
            │     transformar(versão)  ── função pura ──> ContratacaoLimpa + rejeições
            │     ├─ orgaos.upsert / fornecedores.upsert / contratacoes.upsert
            │     ├─ rejeicoes.add(...)          (idempotente)
            │     └─ a cada 100: commit()
            └─ watermarks.set(agora - 1 min) + commit()   (marca junto com o último lote)
```

### 1. Normalização (`pipelines/normalizacao.py`): funções puras

Cada regra é uma função pequena que recebe o valor "como veio" e devolve o valor limpo
ou levanta `ValueError`:

```python
def para_decimal(valor: object) -> Decimal:
    if isinstance(valor, bool) or valor is None:  # True é int em Python!
        raise ValueError(f"não é um número: {valor!r}")
    if isinstance(valor, Decimal | int):
        resultado = Decimal(valor)
    elif isinstance(valor, float):
        resultado = _parse_decimal(str(valor), valor)  # str(0.1) == "0.1"
    elif isinstance(valor, str):
        # "1.234,56" -> "1234.56"
        resultado = _parse_decimal(_texto_numerico(valor), valor)
    ...
```

Por que `str(float)`? `Decimal(0.1)` expõe o erro binário do float
(`0.1000000000000000055511…`), enquanto `Decimal(str(0.1))` usa a representação mais curta,
`0.1`, que é o que a API mandou.

Datas sem fuso recebem o fuso de Brasília com `replace`, e não com `astimezone`: o
relógio **já é** de Brasília, falta só dizer isso.

### 2. Schemas do bruto (`pipelines/schemas_bronze.py`): 1ª camada de validação

```python
Valor = Annotated[Decimal, BeforeValidator(para_decimal)]


class ItemBronze(_Bruto):  # extra="ignore": o PNCP tem dezenas de campos
    numero_item: int = Field(alias="numeroItem")
    quantidade: Valor
    material_ou_servico: MaterialOuServico = Field(alias="materialOuServico")  # enum
```

O `BeforeValidator` roda a limpeza **antes** do Pydantic validar o tipo. Quando falha, o
erro traz o caminho com os nomes do PNCP (`itens[2].quantidade`), que é o que vai para os
rejeitados.

### 3. Transformação (`pipelines/transformacao.py`): função pura

`transformar(versao) -> Transformacao(limpa | None, rejeicoes)`, em quatro passos:

1. **Cabeçalho da contratação.** Se o Pydantic falha aqui, a **contratação inteira** é
   rejeitada.
2. **Itens, um por um.** Cada item é validado separadamente, então um item ruim é
   rejeitado **sozinho**. O número repetido gera `item_duplicado`: o 1º fica e os demais
   são rejeitados.
3. **Resultado do item.** Resultados cancelados são ignorados. O vencedor é o de menor
   `ordemClassificacaoSrp`; sem ordem, vale o menor `sequencialResultado`. Fornecedor
   inválido rejeita o item com `resultado_invalido`.
4. **Entidades do domínio (2ª camada).** `Orgao`, `Contratacao` e `ItemContratacao`
   aplicam as regras de negócio. `InvalidValueError` vira `campo_invalido` e
   `BusinessRuleError` vira `regra_negocio`.

```python
@staticmethod
def _valor_estimado(item: ItemBronze) -> Dinheiro | None:
    # sigiloso: o PNCP manda 0, mas o valor é desconhecido
    if item.orcamento_sigiloso or item.valor_unitario_estimado is None:
        return None
    return Dinheiro(item.valor_unitario_estimado)
```

Depois de montada, a contratação é conferida: se a soma dos itens diverge do total em
mais de 1%, ela é marcada `inconsistente`. É gravada mesmo assim; a divergência vira
métrica.

### 4. Pipeline (`pipelines/bronze_to_silver.py`)

```python
depois_de = None if completo else self._silver.watermarks.get(PIPELINE)
ate = self._clock() - self._atraso  # agora - 1 min
try:
    for numero, versao in enumerate(
        self._bronze.versions_between(depois_de, ate), start=1
    ):
        self._processar(versao, report)
        if numero % self._tamanho_lote == 0:
            self._silver.commit()  # progresso salvo; a marca só no final
    self._silver.watermarks.set(PIPELINE, ate)
    self._silver.commit()
except Exception:
    self._silver.rollback()  # desfaz o lote atual e deixa o erro subir
    raise
```

- **Por que ler só até "agora − 1 min"?** A ingestão carimba `vigente_desde` um instante
  *antes* de gravar. Uma versão com horário 10:00:00 pode ficar visível às 10:00:01.
  Se o pipeline lesse até "agora" e gravasse a marca 10:00:00,5, essa versão ficaria
  para trás para sempre.
- **Por que a marca é o `ate`, e não o maior `vigente_desde` lido?** Com commit por lote,
  duas versões com o mesmo horário podem cair em lotes diferentes, e a próxima
  execução (`> marca`) pularia a segunda.

### 5. Bronze: `vigente_desde` (`adapters/mongo/bronze.py`)

O campo muda só quando um conteúdo **vira o atual**: é uma versão nova ou uma volta
A → B → A. Uma simples recoleta do mesmo conteúdo (`_touch`) não mexe nele. Os
documentos antigos, gravados na Etapa 02, recebem o campo por um *backfill* idempotente
em `ensure_indexes`:

```python
# update com pipeline ([...]): permite copiar um campo para outro
self._contratacoes.update_many(
    {"vigente_desde": {"$exists": False}},
    [{"$set": {"vigente_desde": "$primeira_coleta"}}],
)
```

### 6. Silver: rejeições e marca (`adapters/postgres/silver.py`)

```python
pg_insert(RegistroRejeitadoModel).values(...).on_conflict_do_nothing(
    constraint="uq_registros_rejeitados_versao_item"
)
```

O UNIQUE é `(numero_controle_pncp, bronze_hash, numero_item) NULLS NOT DISTINCT`. Sem o
`NULLS NOT DISTINCT` (Postgres 15+), duas rejeições da **contratação inteira**
(`numero_item` NULL) não conflitariam, porque para o SQL `NULL = NULL` não é verdadeiro,
e cada reprocessamento duplicaria a linha.

## Decisões e alternativas (por que assim e não de outro jeito)

Resumo; o detalhe está no [ADR 0004](../adr/0004-qualidade-e-incremental-silver.md).

| Decisão | Alternativa descartada | Por quê |
|---|---|---|
| Rejeitar contratação **ou** item | Rejeitar tudo por 1 item ruim | Perderia dados bons |
| Pydantic (formato) + domínio (regra) | Só o domínio | Sem caminho do campo nas mensagens |
| Sigiloso = `NULL` | `0` com flag | Armadilha: médias e sobrepreço envenenados |
| Marca por `vigente_desde` | `ultima_coleta` / `primeira_coleta` | A 1ª muda a cada coleta; a 2ª perde A → B → A |
| Marca no Postgres, no mesmo commit | Marca no Mongo | Dados e marca poderiam divergir |
| Marca = `ate` (corte) | Maior horário lido | Empates entre lotes seriam pulados |
| 1º colocado como vencedor | N resultados por item | Não é necessário até a Etapa 09 |
| Job sob demanda | Evento / loop | Orquestração fica para depois |
| Transformação separada em `transformacao.py` | Tudo em `bronze_to_silver.py` (como no plano) | Função pura testável sem nada de I/O; o pipeline só orquestra |

## Conceitos novos (explicação didática de cada conceito/biblioteca usada)

- **Dimensões de qualidade de dados**, e onde cada uma aparece aqui:
  - *completude*: campos obrigatórios presentes (Pydantic, `Field required`);
  - *validade*: formato e domínio (CNPJ com dígito verificador, UF, enums, datas);
  - *unicidade*: número de item repetido gera `item_duplicado`, e o upsert pela chave
    natural impede duplicata;
  - *consistência*: total da contratação contra a soma dos itens (`inconsistentes`).
- **Processamento incremental / marca d'água (*watermark*):** em vez de reprocessar
  tudo, guarda-se "até onde já fui" e cada execução lê só o intervalo novo. O custo é
  proporcional ao que mudou, e não ao tamanho da base.
- **Idempotência como rede de segurança:** como gravar 2x dá o mesmo resultado (upsert,
  `ON CONFLICT DO NOTHING`), dá para ser "pessimista": na dúvida, reprocessa. Isso vale
  para o crash no meio, para o `--completo` e para a sobreposição.
- **Unidade de trabalho (*Unit of Work*):** um objeto que agrupa os repositórios sobre a
  **mesma transação** e expõe `commit`/`rollback`. O pipeline decide *quando* confirmar
  sem saber que por trás há uma `Session` do SQLAlchemy.
- **`BeforeValidator` (Pydantic v2):** função que roda antes da validação do tipo. É o
  lugar certo para "limpar e depois validar".
- **`NULLS NOT DISTINCT`:** faz o UNIQUE tratar NULLs como iguais.
- **JSONB:** JSON binário do Postgres, consultável por SQL:
  `detalhes -> 0 ->> 'campo'` lê o campo do 1º problema.
- **Unicode NFKD:** decompõe `"ã"` em `"a"` + `"~"`. Removendo os caracteres
  "combinantes", comparamos `"Não se aplica"` e `"nao se aplica"` como iguais.
- **Genéricos PEP 695** (`class _KeyedRepo[K, T]:`): a sintaxe do Python 3.12 para
  classes genéricas, usada no fake de repositório.

## Testes (o que cada teste verifica e por que ele importa)

**Unitários:** 99 novos, 312 no total, sem I/O.

| Arquivo | O que prova |
|---|---|
| `test_normalizacao.py` (42) | Cada regra com bordas: `"1.234,56"`, `"1234.56"`, float `0.1`, `""`, `"abc"`, `"NaN"`, `Infinity`, `True`, `None`; data sem fuso vira Brasília; offset e `Z` mantidos; `30/02` e `10/03/2025` recusados; espaços; marcadores de categoria com e sem acento |
| `test_schemas_bronze.py` (4) | Campos novos do PNCP ignorados; limpeza aplicada; erro aponta o campo em camelCase |
| `test_transformacao.py` (30) | Fixture **real** vira entidades exatas (valor, fuso, fornecedor). Rejeição da contratação: campo ausente com caminho, data inválida, modalidade desconhecida, UF, CNPJ, total negativo. Rejeição só do item: quantidade 0, número inválido, duplicado. Resultados: cancelado ignorado, 1º colocado SRP, fornecedor inválido. Sigiloso vira `None`; esfera "N"; consistência |
| `test_bronze_to_silver.py` (16) | Registro inválido não interrompe o lote; motivo certo; 2ª execução lê 0; só o novo é processado; versões recentes demais esperam; `--completo` sem duplicar; falha inesperada faz rollback **e não avança a marca**; commits por lote; `main` fecha conexões mesmo com erro |
| `test_pncp_client.py` (+4) | **Bug da Etapa 02:** itens, resultados e arquivos percorrem as páginas |
| `test_entities.py` (+2), `test_postgres_mappers.py` (+1) | Valor desconhecido: total `None`; `NULL` ida e volta |

**Integração:** 16 novos, 61 no total, com Mongo e Postgres reais.

| Arquivo | O que prova |
|---|---|
| `test_pipeline_silver.py` (9) | **Contagens batem** (5 na bronze → 4 contratações, 11 itens, 1 órgão, 1 fornecedor, 2 rejeições com motivos); JSONB consultável; valor exato e fuso no banco; sigiloso = NULL; esfera "N"; reexecução idempotente; retificação atualiza e remove item; marca e rejeição idempotentes |
| `test_mongo_bronze.py` (+6) | `vigente_desde` na versão nova, não no toque, sim no A → B → A; filtro por intervalo aberto/fechado; backfill |
| `test_migrations.py` (+1) | Downgrade da 0002 **se recusa** a inventar 0 para item sigiloso |

Por que o fake da silver tem `pending` e `committed`? Para testar de verdade que "a
marca não avança numa falha", o fake precisa simular transação: o que não foi
confirmado some no `rollback`.

## Como rodar e ver funcionando (comandos exatos)

```bash
make up                  # stack no ar
make migrate             # aplica 0002 e 0003
make ingest-once         # (opcional) traz dados novos do PNCP para a bronze
make pipeline            # bronze -> silver, só o que é novo
make pipeline-completo   # reprocessa toda a bronze (após corrigir uma regra)
make logs s=pipeline-silver   # ou veja a saída do make: registro_rejeitado / pipeline_concluido
```

Conferir no banco:

```bash
docker compose exec postgres psql -U radar -d radar
```

```sql
select count(*) from silver.contratacao;
select motivo, count(*) from silver.registros_rejeitados group by 1;
select numero_controle_pncp, numero_item, motivo, detalhes
  from silver.registros_rejeitados order by rejeitado_em desc limit 10;
select * from silver.pipeline_watermark;
-- itens sigilosos (valor desconhecido)
select count(*) from silver.item_contratacao where valor_unitario_estimado is null;
-- consistência: total x soma dos itens
select c.numero_controle_pncp, c.valor_total_estimado,
       sum(i.quantidade * i.valor_unitario_estimado) as soma_itens
  from silver.contratacao c join silver.item_contratacao i on i.contratacao_id = c.id
 group by 1, 2
having abs(c.valor_total_estimado - sum(i.quantidade * i.valor_unitario_estimado))
       > 0.01 * c.valor_total_estimado;
```

**Execução real** (2026-09-24):

- A 1ª execução leu 94 versões, gravou 93 e rejeitou 1, a do consórcio com
  `esferaId "N"`. Isso levou à correção e à migração 0003.
- As 14 inconsistentes tinham **exatamente 10 itens** cada: era o bug de paginação da
  Etapa 02.
- Depois da correção, o `pipeline-completo` leu 110 versões, gravou 110 e não rejeitou
  nenhuma.
- As execuções incrementais seguintes leram só as poucas versões novas, em cerca de
  0,05 s.

## Erros comuns e como depurar

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `relation "silver.pipeline_watermark" does not exist` | Migrações não aplicadas | `make migrate` |
| `CheckViolation ... ck_orgao_esfera_valida` (ou outro CHECK) | Enum do domínio aceita um código que o banco não aceita | Criar uma migração ajustando o CHECK. O pipeline para de propósito: CHECK violado é bug |
| Muitas rejeições `campo_invalido` do mesmo campo | O PNCP mudou o formato ou criou um código novo | Ver `detalhes` na tabela, ajustar a regra/enum (teste primeiro) e rodar `make pipeline-completo` |
| O pipeline "não vê" uma contratação recém-ingerida | Ela está no atraso de segurança (1 min) | Rodar de novo daqui a 1 min |
| Contratação corrigida na regra, mas ainda rejeitada | A marca já passou da versão | `make pipeline-completo` |
| `inconsistentes` alto | Itens faltando na bronze, ou divergência real da fonte | Conferir a quantidade de itens na bronze contra `/itens/quantidade` do PNCP |

## Perguntas de revisão

1. Por que a marca d'água é o instante de corte (`agora − 1 min`), e não o maior
   `vigente_desde` que o pipeline leu? Descreva o cenário que quebraria.
2. Se o processo morrer depois de 2 commits parciais e antes do final, o que acontece
   na próxima execução? Por que isso não duplica nada?
3. Uma contratação com o item 2 com quantidade 0 é gravada? Com quais itens? O que
   aparece em `registros_rejeitados`?
4. Por que um orçamento sigiloso vira `NULL`, e não `0`? Que consulta da Etapa 04 daria
   errado com `0`?
5. Qual é a diferença entre um dado rejeitado (vai para `registros_rejeitados`) e uma
   violação de CHECK no banco (derruba a execução)? Por que tratar diferente?
