# ADR 0003 — RabbitMQ para eventos, MongoDB na bronze e outbox simplificado

- **Status:** aceito
- **Data:** 2026-09-24
- **Etapa:** 02

## Contexto

A ingestão precisa: (1) guardar o dado bruto do PNCP, um JSON grande, aninhado e que ganha
campos novos com frequência; (2) avisar outro processo (a extração com LLM, Etapa 07) de
que existe um edital novo para ler, sem que um processo dependa do outro estar no ar.

## Decisão

1. **MongoDB na camada bronze.** Uma coleção de versões por contratação, versionada por
   hash (SHA-256 do JSON canônico). Uma versão nova só é gravada quando o conteúdo muda.
2. **RabbitMQ para eventos.** Exchange `radar.eventos` (topic), fila durável `edital.novo`
   com dead-letter (`radar.dlx` → `edital.novo.dlq`), mensagens persistentes, *publisher
   confirms* e evento versionado (`EditalNovoV1`).
3. **Outbox simplificado.** O documento é registrado no Mongo como "evento pendente" antes
   da publicação e só é marcado como publicado após a confirmação do broker. Pendentes são
   republicados no início de cada execução. Entrega **at-least-once**: o consumidor
   deduplica pelo `event_id` (UUID v5, determinístico por documento).

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Bronze no próprio Postgres (coluna `jsonb`) | Funcionaria e teria uma peça a menos. Mas separar o bruto do transacional deixa claro o papel de cada camada, não mistura carga de ingestão com consultas da API e cobre o requisito de NoSQL da vaga. Mongo guarda o JSON aninhado sem schema prévio |
| Bronze em arquivos (JSON/Parquet num bucket) | É o padrão em *data lakes* grandes, mas exigiria MinIO/S3 (fora do plano enxuto) e dificultaria consultas pontuais ("me mostra o bruto desta contratação") |
| Sobrescrever o bruto a cada coleta | Perderia o histórico: retificações de edital sumiriam |
| **Kafka** | Feito para milhões de eventos/s, retenção longa e replay. Aqui são centenas de eventos por dia, um produtor e um tipo de consumidor. Kafka exigiria cluster (ou KRaft), partições e offsets. RabbitMQ entrega fila de trabalho, ack, DLQ e UI de gestão com um container |
| Redis (listas/streams) | Leve, mas sem durabilidade e DLQ tão maduras quanto as do RabbitMQ para fila de trabalho |
| Publicar direto, sem outbox | Se o worker cair entre gravar o PDF e publicar, o evento se perde para sempre (o documento já "existe", então não seria baixado de novo) |
| Outbox "de verdade" (tabela + processo *relay* separado) | Mais robusto em sistemas grandes; aqui, o próprio worker varrendo os pendentes cobre o mesmo risco com bem menos peças |
| Publicar só no fim da execução | **Tentado e descartado** na execução real: com o PNCP lento, a execução levava dezenas de minutos, e os editais já baixados esperavam o fim para serem avisados |

## Consequências

- **Positivas:** ingestão idempotente (rodar 2x = mesmo estado); nenhum evento se perde
  se o broker ou o worker caírem; histórico completo do bruto; a extração (Etapa 07) pode
  ficar fora do ar sem perder trabalho (as mensagens esperam na fila).
- **Negativas:** o consumidor **precisa** ser idempotente (pode receber o mesmo evento 2x);
  mais uma peça de infraestrutura (Mongo) para operar.
- **A observar:** a API de detalhes do PNCP pode ser lenta (~33 s por chamada medidos).
  Se o volume crescer, paralelizar as chamadas com concorrência limitada (hoje são
  sequenciais, por simplicidade).
