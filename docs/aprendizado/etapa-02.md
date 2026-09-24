# Etapa 02 — Ingestão do PNCP (bronze + eventos)

## O que foi construído (visão geral em 1 parágrafo)

Um **worker** que, a cada hora, consulta a API pública do PNCP (padrão: Ceará, pregão
eletrônico e dispensa, últimos 2 dias), guarda cada contratação **exatamente como veio**
(com itens, resultados e lista de arquivos) no **MongoDB** (camada bronze), baixa o **edital**
para um volume Docker e publica um evento **`edital.novo`** no **RabbitMQ**, para a extração
com LLM (Etapa 07) saber que há trabalho. Tudo é **idempotente**: rodar de novo não duplica
versões, arquivos nem eventos. Tudo é **resiliente**: retry com backoff para falhas
temporárias, falhas isoladas não derrubam o lote, e um *outbox* garante que nenhum evento
se perde se o broker ou o worker caírem.

## Como a lógica funciona (passo a passo, com trechos curtos de código)

```
worker (loop)                                          ┌──────────── MongoDB (bronze)
  └─ IngestaoService.run(janela)                       │   pncp_contratacoes: versões por hash
       ├─ 0. publica pendentes de execuções anteriores │   pncp_documentos: arquivos + outbox
       └─ para cada modalidade × UF:                   │
            PncpClient.list_contratacoes ─ paginação ──┤
              └─ para cada contratação:                │
                   get_itens / get_resultados / get_documentos
                   ├─ bronze.save_if_changed(payload) ─┘
                   └─ para cada edital ainda não baixado:
                        download → LocalDocumentStorage (volume) → register_document (pendente)
                        └─ publish(EditalNovoV1) ──> RabbitMQ ──> mark_published
```

### 1. Ports (`ports/`): o que o serviço precisa, sem saber quem entrega

Quatro contratos: `ContratacoesSource` (PNCP), `BronzeRepository` (Mongo),
`DocumentStorage` (disco) e `EventPublisher` (RabbitMQ). Os tipos trafegados são do
projeto, não do PNCP:

```python
@dataclass(frozen=True, slots=True)
class DocumentoRef:
    sequencial_documento: int
    eh_edital: bool  # o adapter traduz "tipoDocumentoId == 2"; o serviço não conhece esse código
    url: str
    payload: JsonDict  # o JSON bruto, para a bronze
```

Assim o serviço não sabe que o PNCP chama o campo de `tipoDocumentoId`: se isso mudar,
só o adapter muda.

### 2. Cliente do PNCP (`adapters/pncp/client.py`)

**Paginação** que respeita as peculiaridades reais da API (ver [pncp-api.md](../pncp-api.md)):

```python
while True:
    response = self._get(url, params | {"pagina": pagina})
    if response.status_code == httpx.codes.NO_CONTENT:  # 204: acabou (sem corpo!)
        return
    page = self._parse(PaginaPublicacao, self._json(response), url)
    for record in page.data:
        yield self._to_raw_contratacao(record, url)  # gerador: uma de cada vez
    if page.paginas_restantes == 0 or not page.data:
        return
    pagina += 1
```

`yield` transforma a função num **gerador**: o serviço processa a contratação 1 enquanto
a página 2 ainda nem foi pedida, e a memória não cresce com o total.

**Retry com tenacity**, só para o que vale repetir:

```python
retrying = Retrying(
    stop=stop_after_attempt(self._max_attempts),
    wait=self._wait,  # Retry-After do servidor, senão exponencial + jitter
    retry=retry_if_exception(lambda exc: isinstance(exc, _TransientError)),
    sleep=self._sleep,  # injetável: os testes não esperam de verdade
)
```

- `_TransientError` = 429, 500, 502, 503, 504, timeout, erro de conexão.
- 4xx (400, 404, 422) vira `SourceRequestError` **na hora**: repetir um pedido errado só
  repete o erro.
- Esgotadas as tentativas: `SourceUnavailableError("PNCP indisponível após 5 tentativas em <url>: ...")`.

**Ritmo (throttle):** no mínimo 0,2 s entre requisições, com relógio injetável:

```python
wait = self._min_interval - (now - self._last_request_at)
if wait > 0:
    self._sleep(wait)
```

**Validação legível:** o Pydantic valida só o essencial (`extra="ignore"`), e o erro vira texto
com o caminho do campo: `resposta inesperada do PNCP em <url>: orgaoEntidade.cnpj: Input
should be a valid string`.

### 3. Serviço (`services/ingestao.py`)

Cada contratação vira **um documento bronze** com tudo que foi coletado:

```python
payload = {
    "contratacao": raw.payload,
    "itens": [...],
    "resultados": {"1": [...]},
    "arquivos": [...],
}
record = BronzeRecord(
    numero, payload, hash=payload_hash(payload), coletado_em=self._clock()
)
```

`payload_hash` é o SHA-256 do JSON com as chaves ordenadas: a mesma informação sempre dá o
mesmo hash, independentemente da ordem dos campos. Se o hash é igual ao da última versão,
nada é gravado.

**Falhas isoladas:** cada nível tem seu `try/except` só com os erros esperados
(`SourceError`, `StorageError`, `PublishError`), e o erro vira uma linha em
`relatorio.falhas`. Erros inesperados (Mongo fora do ar, bug) **não** são capturados: o
worker cai e o Docker o reinicia (`restart: unless-stopped`).

**Outbox:**

```python
self._bronze.register_document(stored)  # 1. grava como PENDENTE
self._publish(stored, report)  # 2. publica; só marca publicado se o broker confirmar
```

Se o processo cair entre 1 e 2, o documento continua pendente, e a próxima execução
começa publicando os pendentes. Se o broker falhar no meio da execução, o serviço para de
tentar (os demais ficam pendentes) até a próxima.

### 4. Bronze no Mongo (`adapters/mongo/bronze.py`)

```python
self._contratacoes.update_one(
    {"numero_controle_pncp": numero, "hash": record.hash},  # chave única
    {
        "$setOnInsert": {"payload": ..., "primeira_coleta": ...},  # só na criação
        "$set": {"ultima_coleta": record.coletado_em},
    },  # sempre
    upsert=True,
)
```

`$setOnInsert` + `upsert` = "crie se não existir; se existir, só atualize a data". Se o
conteúdo voltar a uma versão antiga (A → B → A), a versão A é "reativada", e não duplicada.

### 5. RabbitMQ (`adapters/rabbitmq/publisher.py`)

```
radar.eventos (topic) ──"edital.novo"──> fila edital.novo ──(nack/rejeição)──> radar.dlx ──> edital.novo.dlq
```

- `channel.confirm_delivery()`: liga os **publisher confirms**, e o `basic_publish` só
  retorna depois que o broker confirma que guardou;
- `delivery_mode=2` + fila `durable`: a mensagem sobrevive a um restart do broker;
- `mandatory=True`: se nenhuma fila receber, é erro (e não descarte silencioso);
- `message_id = event_id`: o UUID v5 do documento, igual em toda republicação, para o
  consumidor deduplicar.

### 6. Worker (`workers/ingestao.py`)

É a **raiz de composição**: o único lugar que cria httpx, `MongoClient`, publisher e
storage e os injeta no serviço. A janela padrão é "os últimos N dias, terminando hoje
**em Brasília**" (`ZoneInfo("America/Sao_Paulo")`: às 22h de Brasília já é "amanhã" em UTC).
Um `SIGTERM` (vindo do `docker stop`) interrompe a espera entre execuções na hora
(`threading.Event.wait`), e a `main` restaura os tratadores de sinal originais ao sair.

## Decisões e alternativas (por que assim e não de outro jeito)

As escolhas de Mongo, RabbitMQ e outbox estão no [ADR 0003](../adr/0003-rabbitmq-mongo-bronze-outbox.md).
As peculiaridades da API estão em [pncp-api.md](../pncp-api.md).

| Decisão | Alternativa | Por quê |
|---|---|---|
| httpx/pika/pymongo **síncronos** | asyncio (httpx async, aio-pika, motor) | Mais simples de ler e de testar. **Custo medido:** com a API de detalhes a ~33 s por chamada, tudo em sequência é lento. Paralelizar com concorrência limitada é o próximo passo natural se o volume crescer |
| Validar **só os campos essenciais** | `extra="forbid"` (plano original: "campo inesperado gera erro") | O PNCP adiciona campos com frequência; `forbid` quebraria a ingestão a cada novidade. "Inesperado" passou a significar campo obrigatório ausente ou com tipo errado |
| Bronze guarda **datas sem fuso e floats como vieram** | Converter já na ingestão | A bronze é a "foto" da fonte. Conversões (fuso de Brasília, `Decimal`) são regras da Etapa 03; se tiverem bug, dá para reprocessar a partir do bruto |
| Detectar o tipo do arquivo pelos **bytes** | Confiar no `Content-Type` | O PNCP responde `application/octet-stream` para tudo |
| Gravar arquivo **temporário + rename** | Escrever direto no destino | O rename é atômico: ninguém lê um PDF pela metade se o processo cair no meio |
| Timeout de **90 s** (era 30 s) | 30 s | **Medido na execução real:** a API de detalhes respondia em ~33 s, e 30 s estourava em todas as chamadas |
| Evento publicado **logo após o download** (era no fim) | Publicar todos no fim da execução | **Achado na execução real:** a execução levava dezenas de minutos, e os editais baixados esperavam o fim. O teste de regressão `test_event_is_published_as_soon_as_document_is_stored` reproduz o problema |
| Fixtures **reais** enxutas, gravadas por script manual | Escrever JSON de exemplo à mão | JSON inventado reflete o que *achamos* que a API manda. O gravado mostrou, por exemplo, o `numeroItem` estranho nos resultados |

## Conceitos novos (explicação didática de cada conceito/biblioteca usada)

- **Arquitetura medallion (bronze → silver → gold)**: camadas de dados com qualidade
  crescente. **Bronze** = bruto, como veio, com histórico (esta etapa). **Silver** = limpo,
  validado e normalizado (Postgres, Etapa 03). **Gold** = modelado para análise (dbt, Etapa 04).
  Se uma regra da silver tiver bug, dá para reprocessar a partir da bronze, sem pedir de
  novo à fonte.
- **Mensageria**: processos se comunicam por mensagens numa fila, e não chamando um ao
  outro. O produtor não precisa saber quem consome nem se o consumidor está no ar.
- **Exchange, fila e routing key (RabbitMQ)**: o produtor publica numa *exchange* com uma
  *routing key* (`edital.novo`); a exchange entrega às *filas* ligadas (*bind*) àquela
  chave. No tipo `topic`, a chave pode ter curingas (`edital.*`).
- **Ack / nack**: o consumidor confirma (*ack*) que processou; se rejeitar sem recolocar na
  fila (*nack*, `requeue=False`), a mensagem vai para a **dead-letter queue (DLQ)**, onde
  fica para inspeção em vez de sumir ou ficar em loop.
- **Publisher confirms**: o *ack* no sentido contrário: o broker confirma ao produtor que
  guardou a mensagem.
- **At-least-once × exactly-once**: garantir que a mensagem chega **pelo menos uma vez** é
  viável (retry + outbox); garantir **exatamente uma vez** entre sistemas diferentes é, na
  prática, impossível. Por isso o consumidor deduplica pelo `event_id`: entrega
  at-least-once + processamento idempotente = efeito exactly-once.
- **Idempotência**: fazer 2x tem o mesmo efeito que fazer 1x. Aqui: hash na bronze,
  `document_exists` antes do download, `$setOnInsert` no registro, `event_id` determinístico.
- **Outbox**: gravar "preciso avisar X" no mesmo lugar do dado, e só apagar o aviso depois
  de avisar. Resolve o problema de gravar num sistema (Mongo) e publicar em outro
  (RabbitMQ) sem uma transação que abranja os dois.
- **Retry com backoff exponencial e jitter**: esperar 1 s, 2 s, 4 s, 8 s... (exponencial),
  com um pouco de aleatoriedade (jitter), para que vários clientes não voltem todos no
  mesmo instante e derrubem o servidor de novo.
- **`Retry-After`**: cabeçalho em que o servidor diz quanto esperar. Se ele disse, é melhor
  obedecer do que chutar.
- **Gerador (`yield`)**: função que devolve itens um de cada vez, sob demanda.
- **UUID v5**: UUID calculado a partir de um texto e de um *namespace* (SHA-1). O mesmo texto
  sempre gera o mesmo UUID, ao contrário do v4 (aleatório).
- **`respx`**: intercepta as chamadas do httpx nos testes, e nenhuma requisição sai para a rede.
- **Path traversal**: ataque em que uma "chave" como `../../etc/passwd` faz o programa
  gravar ou ler fora da pasta permitida. Bloqueado com `resolve()` + `is_relative_to(root)`.

## Testes (o que cada teste verifica e por que ele importa)

**Unitários novos — 92 testes, sem rede e sem infraestrutura**

| Arquivo | Qtde | O que prova |
|---|---|---|
| `test_pncp_client.py` | 26 | Parse de resposta **real** gravada (e os parâmetros enviados); campo extra preservado; campo ausente ou com tipo errado → erro com o caminho do campo; resposta não-JSON; itens, resultados e documentos (edital × outros); 204 = lista vazia; paginação até a última página e parada no 204; retry em 500/502/503/504/429 e timeout; `Retry-After` respeitado; backoff crescente; desiste após N tentativas com erro claro; **não** repete 400/404/422; download com redirect e limite de tamanho; intervalo mínimo entre requisições |
| `test_ingestao_service.py` | 22 | Fluxo completo; resultados só de itens com resultado; todas as modalidades × UFs; **rodar 2x = mesmo estado**; conteúdo alterado → nova versão sem novo evento; falha de download, de detalhes, de listagem ou de storage não derruba o lote; download falho é tentado de novo depois; **outbox**: publicação falha → pendente → publicada na próxima; broker caído → para de tentar; pendentes publicados no início; **evento sai logo após o download** (regressão); só editais baixados; zip mantém a extensão; log de progresso; hash e tipo de arquivo |
| `test_worker_ingestao.py` | 14 | Argumentos (`--once`, backfill implica `--once`, datas inválidas ou invertidas); janela móvel e janela de backfill; `main` roda uma vez e **fecha as conexões mesmo com erro**; tratadores de sinal restaurados |
| `test_events.py` | 11 | Ida e volta em JSON; tipo e versão no corpo; **`event_id` determinístico** por documento; campos inválidos, campo desconhecido e outra `schema_version` rejeitados; imutável |
| `test_local_storage.py` | 9 | Grava e sobrescreve; sem arquivo temporário sobrando; cria a raiz; **bloqueia path traversal** |
| `test_config.py` | +10 | Padrões da ingestão; listas por vírgula; UF, modalidade, janela e tentativas inválidas; URL do Mongo codificada; senhas fora do `repr` |

**Integração novos — 16 testes, containers reais**

| Arquivo | Qtde | O que prova |
|---|---|---|
| `test_mongo_bronze.py` | 9 | Versão nova gravada; mesmo hash não duplica (só atualiza `ultima_coleta`); conteúdo alterado → 2 versões; A → B → A não duplica; índice único existe; pendentes/publicados; registro idempotente; ordem de pendentes |
| `test_rabbitmq_publisher.py` | 5 | Mensagem persistente, com `message_id` e schema corretos; **nack → DLQ**; topologia idempotente; reconecta após perder a conexão; broker inacessível → `PublishError` |
| `test_ingestao_e2e.py` | 2 | PNCP simulado (fixtures reais) + Mongo + RabbitMQ + disco: bruto no Mongo, PDF no disco, evento na fila; rodar 2x publica uma vez só |

**Totais do projeto:** 213 unitários + 45 de integração.

**Execução real (2026-09-24, CE, modalidades 6 e 8, últimos 2 dias):**

```
MongoDB:   11 contratações na bronze, 6 documentos (16 MB no volume)
RabbitMQ:  edital.novo = 6 mensagens | edital.novo.dlq = 0
1ª tentativa: 18 novas tentativas por ReadTimeout (API de detalhes a ~33 s, timeout era 30 s)
Após as correções: 0 timeouts; os 6 pendentes publicados em ~3 s no início da execução
```

## Como rodar e ver funcionando (comandos exatos)

```bash
make up                                   # sobe tudo, inclusive o worker-ingestao
make logs s=worker-ingestao               # acompanha: ingestao_iniciada, contratacao_ingerida...
make ingest-once                          # uma execução avulsa, agora

# backfill de um período (uma execução):
docker compose run --rm worker-ingestao python -m radar.workers.ingestao \
    --data-inicial 2025-03-01 --data-final 2025-03-07
```

Ver os dados:

```bash
# Mongo (bronze)
set -a; . ./.env; set +a
docker compose exec mongo mongosh -u "$MONGO_ROOT_USER" -p "$MONGO_ROOT_PASSWORD" \
    --authenticationDatabase admin radar_bronze \
    --eval 'db.pncp_contratacoes.findOne({}, {"payload.contratacao.objetoCompra": 1, ultima_coleta: 1})'

# RabbitMQ: UI em http://localhost:15672 (usuário/senha do .env) → Queues → edital.novo
docker compose exec rabbitmq rabbitmqctl list_queues name messages

# editais baixados
docker compose exec worker-ingestao ls -R /data/editais | head
```

Rodar local, sem Docker para o worker (com a infra no ar):

```bash
cd backend && set -a && . ../.env && set +a && uv run python -m radar.workers.ingestao --once
```

## Erros comuns e como depurar

| Sintoma | Causa provável | Como resolver |
|---|---|---|
| Muitos `pncp_nova_tentativa` com `ReadTimeout` | A API de detalhes do PNCP está lenta (medido: ~33 s) | O log traz a `url`; meça com `curl -w "%{time_total}"`; se preciso, aumente `PNCP_TIMEOUT_SECONDS` |
| A execução demora muito e `contratacoes` não sobe | Contratações já conhecidas sendo reprocessadas (1 chamada por item com resultado) | Acompanhe `contratacao_ingerida` no log (campo `lidas_ate_agora`); reduza UFs/modalidades ou a janela |
| `PermissionError` ao gravar em `/data/editais` | Volume criado antes de a imagem ter a pasta do `appuser` | `docker compose down` e `docker volume rm radar_editais_data` (apaga os PDFs), depois `make up` |
| Documentos pendentes que nunca saem | RabbitMQ fora do ar ou credencial errada | `ingestao_falha` com "publicação de ..." no log; `docker compose ps rabbitmq`; eles saem sozinhos na próxima execução depois do conserto |
| `SourceSchemaError: resposta inesperada do PNCP` | O PNCP mudou o formato de um campo essencial | A mensagem diz o campo; atualize `adapters/pncp/schemas.py` e regrave as fixtures (`make pncp-fixtures`) |
| `SourceRequestError: HTTP 400` | Parâmetro inválido (ex.: modalidade inexistente, página > 50) | Confira `INGESTAO_MODALIDADES` e o [pncp-api.md](../pncp-api.md) |
| Teste de DLQ falha às vezes | O dead-lettering é **assíncrono**: o `nack` retorna antes de a mensagem chegar na DLQ | Aconteceu nesta etapa. O teste espera a mensagem com prazo (`_get_with_timeout`) em vez de ler na hora; a investigação (script medindo o tempo) confirmou que a topologia estava certa |
| `mypy`: `Module has no attribute "DeliveryMode"` | Os stubs `types-pika` são mais antigos que o pika 1.3 | Aconteceu nesta etapa. Use `pika.spec.PERSISTENT_DELIVERY_MODE` e `ExchangeType("topic")`, que os stubs conhecem |

## Perguntas de revisão

1. Se o worker cair **depois** de baixar o PDF e **antes** de publicar o evento, o que
   acontece na próxima execução? Quais linhas do código garantem isso?
2. Por que o `event_id` é um UUID **v5** (determinístico) e não um v4 (aleatório)? O que o
   consumidor da Etapa 07 vai fazer com ele?
3. O cliente repete a requisição em 503, mas não em 404. Por quê? E por que o backoff
   tem *jitter*?
4. A bronze guarda `"valorTotalEstimado": 215264.88` como veio (float), mesmo o domínio
   exigindo `Decimal`. Por que a conversão fica para a Etapa 03, e não aqui?
5. O teste da DLQ falhou na primeira versão. Por que "esperar com prazo" é uma correção
   legítima, e não um "afrouxar o teste"? Como a investigação provou que o bug não era
   no código?
