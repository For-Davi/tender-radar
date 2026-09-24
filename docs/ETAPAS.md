# Plano de etapas — Radar de Licitações

Cada etapa segue o fluxo do `CLAUDE.md`: plano → aprovação → código + testes →
`make check` verde → documento de aprendizado → resumo → parar.

Formato de cada etapa:
- **Objetivo**: o que existe ao final que não existia antes.
- **Construir**: itens concretos.
- **Conceitos que você vai aprender**.
- **Testes obrigatórios**: o mínimo; o Claude Code pode (e deve) adicionar mais.
- **Pronto quando**: critérios verificáveis.

---

# FASE 1 — FUNDAÇÃO

## Etapa 00 — Esqueleto do projeto e ferramentas

**Objetivo:** repositório organizado, ferramentas de qualidade configuradas e uma API
mínima respondendo `/health`, com o primeiro teste passando.

**Construir**
- Estrutura de pastas do `CLAUDE.md` (pastas vazias com `.gitkeep` onde necessário).
- `git init`, `.gitignore` (Python, Node, `.env`, dados), `.editorconfig`.
- `backend/pyproject.toml` com uv: fastapi, uvicorn, pydantic-settings, structlog;
  dev: pytest, pytest-cov, ruff, mypy, pre-commit.
- Configuração de ruff (lint + format), mypy strict, pytest (marcadores `unit`/`integration`,
  cobertura mínima 80%).
- `src/radar/config.py` com `Settings` (pydantic-settings) lendo variáveis de ambiente.
- `src/radar/api/main.py` com app FastAPI e rota `GET /health` → `{"status": "ok"}`.
- Logging estruturado configurado.
- `.pre-commit-config.yaml` (ruff, mypy, checagem de arquivos grandes e segredos).
- `Makefile` com `test`, `lint`, `check`, `fmt`.
- `README.md` inicial com o problema de negócio e como rodar.

**Conceitos:** gerenciamento de dependências com uv, lint vs formatação vs checagem de
tipos, configuração por ambiente (12-factor), estrutura de testes com pytest.

**Testes obrigatórios**
- `/health` retorna 200 e o corpo esperado.
- `Settings` lê variáveis de ambiente e aplica valores padrão; falha com erro claro se
  uma variável obrigatória estiver inválida.

**Pronto quando:** `make check` passa; `uv run uvicorn radar.api.main:app` sobe e
`curl localhost:8000/health` responde.

---

## Etapa 01 — Docker e infraestrutura

**Objetivo:** subir toda a infraestrutura e a API com um único comando.

**Construir**
- `backend/Dockerfile` multi-stage (builder com uv → runtime slim, usuário não-root).
  Use `docs/referencia/Dockerfile` como ponto de partida, se existir.
- `docker-compose.yml` com postgres (pgvector/pgvector:pg16), mongo, rabbitmq (com
  management), minio e api, todos com healthcheck e volumes nomeados.
  Use `docs/referencia/docker-compose.yml` como base, ajustando `./services` para `./backend`.
  Serviços de etapas futuras (workers, dbt, frontend, mlflow) entram só nas suas etapas.
- `infra/postgres/init.sql` habilitando a extensão `vector`.
- `.env.example` completo e documentado.
- `Makefile`: `up`, `down`, `logs`, `ps`, `test-integration`.
- `.dockerignore`.

**Conceitos:** imagem vs container, camadas e cache, multi-stage build, rede interna do
Compose (nome do serviço = hostname), volumes, healthcheck e `depends_on`.

**Testes obrigatórios** (`integration`)
- Teste de fumaça que conecta em cada serviço (Postgres executa `SELECT 1` e a extensão
  `vector` existe; Mongo responde `ping`; RabbitMQ aceita conexão; MinIO lista buckets).
- Script `infra/scripts/smoke.sh`: sobe a stack, espera os healthchecks, chama `/health`
  da API no container e retorna código de saída ≠ 0 se algo falhar.

**Pronto quando:** `make up` deixa todos os serviços `healthy` (`docker compose ps`),
o smoke test passa e a imagem roda como usuário não-root (verificar com `docker compose exec api whoami`).

---

## Etapa 02 — Integração contínua

**Objetivo:** todo push/PR é validado automaticamente.

**Construir**
- `.github/workflows/ci.yml` com jobs: `lint` (ruff, mypy), `test-unit` (com cobertura),
  `test-integration` (usando testcontainers no runner), `docker-build`.
- Cache de dependências do uv.
- Template de PR (`.github/pull_request_template.md`) com checklist.
- Badge do CI no README.
- `docs/adr/0001-estrutura-e-ferramentas.md` (primeiro ADR, explicando o formato).

**Conceitos:** pipeline de CI, jobs paralelos e dependentes, cache, por que CI evita
"na minha máquina funciona", ADRs.

**Testes obrigatórios**
- Um PR de teste que quebra propositalmente um teste deve deixar o CI vermelho;
  depois de corrigido, verde. Registrar isso no documento de aprendizado.
- Validar o YAML localmente com `actionlint` (ou equivalente).

**Pronto quando:** CI verde na branch principal e bloqueando PR com teste quebrado.

---

# FASE 2 — DADOS

## Etapa 03 — Domínio e modelo relacional

**Objetivo:** entidades de negócio e o banco transacional normalizado, com migrações.

**Construir**
- `domain/`: entidades (Orgao, Contratacao, ItemContratacao, Fornecedor, Documento) e
  value objects (ex.: `Cnpj` com validação de dígito verificador, `Dinheiro` com Decimal).
- Regras de negócio puras (ex.: status válidos da contratação, item não pode ter valor negativo).
- `adapters/postgres/`: modelos SQLAlchemy 2.0, sessão, e repositórios implementando
  `ports/` (Protocols).
- Alembic com a primeira migração (chaves primárias, estrangeiras, índices, `UNIQUE` para
  idempotência — ex.: número de controle PNCP).
- Diagrama ER em Mermaid em `docs/modelo-relacional.md`.
- ADR: por que separar entidade de domínio do modelo ORM.

**Conceitos:** normalização (1FN–3FN), chaves e integridade referencial, índices,
padrão Repository, ports & adapters (arquitetura hexagonal), migrações versionadas.

**Testes obrigatórios**
- `unit`: validação de CNPJ (válidos, inválidos, com/sem máscara), regras das entidades,
  `Dinheiro` sem erro de ponto flutuante.
- `integration` (Postgres via testcontainers): migração sobe e desce (`upgrade`/`downgrade`)
  sem erro; repositório salva e busca; violação de `UNIQUE` e de FK geram o erro de domínio
  esperado; `upsert` não duplica registros.

**Pronto quando:** `alembic upgrade head` funciona no container e todos os testes passam.

---

## Etapa 04 — Cliente da API do PNCP

**Objetivo:** consumir a API pública do PNCP de forma resiliente e testável.

**Construir**
- Estudar a documentação da API de consulta do PNCP e registrar os endpoints usados em
  `docs/pncp-api.md`.
- `ports/contratacoes_source.py` (Protocol) e `adapters/pncp/client.py` com httpx:
  paginação, timeout, retry com backoff exponencial (tenacity) para 429/5xx,
  respeito a limite de requisições, e parsing para schemas Pydantic.
- Gravar 3 ou 4 respostas reais em `tests/fixtures/pncp/` (script de gravação separado,
  executado manualmente, nunca no CI).

**Conceitos:** cliente HTTP, idempotência de leitura, retry e backoff, por que depender de
uma interface e não da implementação, fixtures gravadas.

**Testes obrigatórios** (com `respx`, sem rede)
- Parsing correto de uma resposta real gravada.
- Paginação percorre todas as páginas e para na última.
- Retry em 500/429 e sucesso na tentativa seguinte; desiste após N tentativas com erro claro.
- Não faz retry em 400/404.
- Campo inesperado/ausente na resposta gera erro de validação legível (não quebra silenciosamente).

**Pronto quando:** testes passam e um script `make pncp-sample` busca de verdade um dia de
dados e imprime um resumo.

---

## Etapa 05 — Worker de ingestão (bronze + eventos)

**Objetivo:** processo que busca contratações, guarda o dado bruto e avisa o sistema.

**Construir**
- `adapters/mongo/`: repositório bronze (JSON original + metadados: data de coleta, fonte, hash).
- `adapters/minio/`: armazenamento dos PDFs dos editais (bucket criado na inicialização).
- `adapters/rabbitmq/`: publicador com exchange, fila `edital.novo`, fila de dead-letter,
  mensagens persistentes e schema de evento versionado (Pydantic).
- `services/ingestao.py`: caso de uso que orquestra fonte → bronze → PDF → evento.
- `workers/ingestao.py`: executável com intervalo configurável e janela de datas.
- Idempotência: reprocessar a mesma janela não duplica nada nem republica eventos.
- Serviço `worker-ingestao` no Compose.
- ADR: por que RabbitMQ (e não Kafka) e por que Mongo na camada bronze.

**Conceitos:** arquitetura medallion (bronze/silver/gold), mensageria, exchange/fila/routing
key, ack, dead-letter queue, idempotência, entrega "at-least-once".

**Testes obrigatórios**
- `unit` com fakes em memória (fonte, bronze, storage, publicador): fluxo completo,
  idempotência (rodar 2x = mesmo estado), falha no download do PDF não derruba o lote inteiro.
- `integration` (Mongo, MinIO, RabbitMQ reais): documento gravado, PDF no bucket, mensagem
  na fila com o schema correto.

**Pronto quando:** `make up` com o worker rodando popula Mongo e MinIO e a UI do RabbitMQ
mostra mensagens na fila.

---

## Etapa 06 — Pipeline bronze → silver com qualidade de dados

**Objetivo:** transformar o bruto em dados limpos no Postgres, sabendo exatamente o que foi rejeitado.

**Construir**
- `pipelines/bronze_to_silver.py`: lê bronze, normaliza (datas, valores, CNPJs, textos),
  valida com pandera e grava via repositórios da Etapa 03.
- Tabela `silver.registros_rejeitados` com motivo da rejeição.
- Processamento incremental (marca d'água pela data de coleta).
- Relatório de execução (lidos, gravados, rejeitados, duração) nos logs.

**Conceitos:** qualidade de dados (completude, validade, unicidade, consistência),
processamento incremental, validação por schema de DataFrame.

**Testes obrigatórios**
- Cada regra de limpeza com casos de borda (valor "1.234,56", data inválida, CNPJ com máscara,
  campos nulos).
- Registro inválido vai para rejeitados com o motivo certo e não interrompe o lote.
- Execução incremental processa só o que é novo.
- `integration`: bronze no Mongo → silver no Postgres, contagens batem.

**Pronto quando:** rodar o pipeline sobre os dados da Etapa 05 popula o Postgres e o
relatório mostra números coerentes.

---

## Etapa 07 — Camada analítica com dbt (gold)

**Objetivo:** modelo dimensional pronto para análise, com SQL avançado e testes de dados.

**Construir**
- Projeto dbt em `dbt/` (dbt-postgres), com `staging/` → `intermediate/` → `marts/`.
- Star schema: `fato_contratacao_item`, `dim_orgao`, `dim_fornecedor`, `dim_tempo`, `dim_categoria`.
- Marts analíticos usando funções de janela:
  - variação de preço por categoria mês a mês (`LAG`);
  - ranking de fornecedores por órgão (`RANK`/`DENSE_RANK`);
  - média móvel de 3 meses de valor contratado;
  - percentil do preço do item dentro da categoria (`PERCENT_RANK`) — base do alerta de sobrepreço.
- Documentação dos modelos (`dbt docs`).
- Serviço `dbt` no Compose (profile `jobs`) e `make dbt`.

**Conceitos:** modelagem dimensional (fato, dimensão, granularidade), CTEs, funções de
janela, testes de dados, linhagem.

**Testes obrigatórios**
- Testes genéricos: `unique`, `not_null`, `relationships`, `accepted_values`.
- Testes singulares em SQL (ex.: soma dos itens = total da fato; nenhum preço negativo).
- Unit tests do dbt (dbt ≥ 1.8) para pelo menos 2 marts com janela, com entrada e saída
  esperadas escritas à mão — provam que o `LAG`/`RANK` calcula o que você acha que calcula.

**Pronto quando:** `dbt build` roda sem falhas e o documento de aprendizado explica cada
função de janela com um exemplo de entrada e saída.

---

# FASE 3 — APLICAÇÃO

## Etapa 08 — API REST

**Objetivo:** expor os dados para o frontend com uma API bem desenhada.

**Construir**
- Routers: `GET /contratacoes` (filtros: UF, órgão, categoria, período, faixa de valor;
  paginação; ordenação), `GET /contratacoes/{id}`, `GET /orgaos`, `GET /metricas/...`
  (lendo os marts).
- Schemas de resposta separados dos modelos de domínio.
- Tratamento de erros padronizado (RFC 7807 / problem+json).
- CORS configurado para o frontend.
- Dependências injetadas via `Depends` (sessão, repositórios).

**Conceitos:** design de API REST, paginação, validação de entrada, códigos HTTP,
OpenAPI, injeção de dependência no FastAPI.

**Testes obrigatórios**
- Cada endpoint: sucesso, filtros combinados, paginação (primeira/última página, página vazia),
  404, 422 para parâmetros inválidos.
- Teste com repositório falso (unit) e com banco real (integration).
- Teste que garante que o schema OpenAPI é gerado sem erro (contrato).

**Pronto quando:** `/docs` mostra todos os endpoints documentados e os testes passam.

---

## Etapa 09 — Frontend: dashboard

**Objetivo:** interface para explorar as contratações.

**Construir**
- Next.js (App Router) + TypeScript strict em `frontend/`, Tailwind, ESLint, Prettier.
- Cliente de API tipado, com tipos gerados do OpenAPI (`openapi-typescript`).
- Páginas: dashboard (cards de KPIs + gráficos com Recharts), lista com filtros e paginação,
  detalhe da contratação.
- Estados de carregamento, vazio e erro em todas as telas.
- Dockerfile do frontend e serviço no Compose.
- Job de frontend no CI (lint, typecheck, testes).

**Conceitos:** componentes, server vs client components, tipos compartilhados via OpenAPI,
gerenciamento de estado de requisição (TanStack Query), acessibilidade básica.

**Testes obrigatórios** (Vitest + Testing Library + MSW)
- Filtros alteram a requisição feita à API.
- Paginação funciona.
- Estados de loading, vazio e erro são renderizados.
- Formatação de moeda e data em pt-BR.

**Pronto quando:** `make up` e `http://localhost:3000` mostra dados reais; testes verdes.

---

# FASE 4 — IA

## Etapa 10 — Worker de extração com LLM

**Objetivo:** ler o PDF do edital e extrair campos estruturados automaticamente.

**Construir**
- `ports/llm.py` (Protocol) com implementações: Anthropic, Ollama (local, gratuito) e
  `FakeLLM` (determinístico, para testes). Provedor escolhido por variável de ambiente.
- Extração de texto do PDF (pdfplumber ou docling), preservando número da página.
- Schema Pydantic `EditalExtraido`: objeto, modalidade, valor estimado, prazos,
  exigências de habilitação, critério de julgamento, cada campo com a página de origem.
- Prompt versionado em arquivo (`llm/prompts/extracao_v1.md`).
- Saída estruturada validada; se inválida, uma nova tentativa com a mensagem de erro, depois DLQ.
- `workers/extracao.py` consumindo `edital.novo` com ack manual, grava no Postgres.
- Controle de custo: log de tokens por chamada e limite de tamanho do documento.

**Conceitos:** saída estruturada de LLM, engenharia de prompt, versionamento de prompt,
consumidor de fila com ack/nack, DLQ, abstração de provedor.

**Testes obrigatórios** (sempre com `FakeLLM`)
- Texto do PDF de fixture é extraído com as páginas certas.
- Resposta válida do LLM vira `EditalExtraido` correto.
- Resposta inválida → nova tentativa → sucesso; inválida duas vezes → DLQ.
- Mensagem só recebe `ack` após gravar no banco (simular falha no banco e verificar `nack`).
- `integration`: mensagem publicada na fila é consumida e o resultado aparece no Postgres.

**Pronto quando:** um edital real passa pelo fluxo completo com um LLM real (execução manual)
e o resultado é mostrado no resumo da etapa.

---

## Etapa 11 — Avaliação da extração (golden set)

**Objetivo:** medir, com números, o quanto a extração acerta.

**Construir**
- `data/golden_set/`: 20 a 30 editais com os campos anotados à mão (o dono do projeto anota;
  o Claude Code cria o formato e uma ferramenta simples para facilitar a anotação).
- `llm/avaliacao.py`: compara extraído × esperado por campo, com métricas adequadas a cada
  tipo (exato para datas e valores com tolerância; similaridade para textos; precisão/recall
  para listas como exigências).
- Relatório em Markdown com acurácia por campo, erros mais comuns e comparação entre versões
  de prompt.
- `make eval-extracao`.

**Conceitos:** avaliação de LLM, golden set, métricas por tipo de campo, regressão de
qualidade ao mudar prompt ou modelo.

**Testes obrigatórios**
- Cada função de métrica com casos conhecidos (acerto total, parcial, erro, campo ausente).
- Tolerância de valores e normalização de datas.
- Relatório é gerado corretamente a partir de resultados sintéticos.

**Pronto quando:** existe um relatório real comparando pelo menos duas versões de prompt.

---

## Etapa 12 — RAG com pgvector

**Objetivo:** responder perguntas sobre os editais citando a página de origem.

**Construir**
- Chunking com sobreposição, preservando página e seção.
- Embeddings (modelo configurável; opção local com sentence-transformers) salvos em pgvector
  com índice HNSW.
- Busca híbrida: vetorial + textual (full-text do Postgres), com fusão de resultados (RRF).
- Endpoint `POST /perguntar` com filtro opcional por edital: recupera, monta o contexto e
  responde com citações (edital + página). Responde "não encontrei" quando não há evidência.
- Avaliação do retrieval: recall@k e MRR sobre perguntas do golden set.

**Conceitos:** embeddings, similaridade de cosseno, índices vetoriais, chunking, busca
híbrida, grounding e citações, alucinação.

**Testes obrigatórios**
- Chunking: tamanho, sobreposição, nenhuma perda de texto, página preservada.
- Fusão RRF com rankings conhecidos.
- `integration`: documentos inseridos, busca retorna o chunk esperado no top-k.
- Endpoint com `FakeLLM`: resposta contém citações válidas; sem contexto relevante → "não encontrei".
- Métrica recall@k calculada corretamente em caso sintético.

**Pronto quando:** recall@5 medido e registrado; perguntas reais respondidas com citação.

---

## Etapa 13 — Agente com ferramentas

**Objetivo:** assistente que decide sozinho quando consultar números (SQL) ou documentos (RAG).

**Construir**
- Ferramentas: `consultar_dados` (SQL somente leitura, só no schema dos marts),
  `buscar_editais` (RAG da Etapa 12), `detalhar_contratacao`.
- Guardrails do SQL: parser (sqlglot) aceita só `SELECT`, só tabelas permitidas, aplica
  `LIMIT` e timeout; usuário do Postgres com permissão somente leitura.
- Loop do agente com limite de passos e registro de cada chamada de ferramenta (trace).
- Endpoint `POST /agente` com streaming (SSE).

**Conceitos:** tool use / function calling, loop de agente, guardrails, princípio do menor
privilégio, rastreabilidade.

**Testes obrigatórios**
- Guardrail rejeita `DROP`, `UPDATE`, `INSERT`, múltiplos statements, tabelas fora da lista,
  e comentários tentando escapar da regra.
- Usuário do banco realmente não consegue escrever (integration).
- Com `FakeLLM` roteirizado: agente chama a ferramenta certa, usa o resultado e para;
  respeita o limite de passos; erro de ferramenta é devolvido ao modelo sem derrubar a requisição.

**Pronto quando:** perguntas como "qual órgão do CE mais contratou TI em 2025 e quais
exigências aparecem nos editais dele?" funcionam usando as duas ferramentas.

---

# FASE 5 — ML

## Etapa 14 — Modelo de sobrepreço

**Objetivo:** estimar o valor esperado de um item e sinalizar valores fora do padrão, com avaliação honesta.

**Construir**
- Dataset a partir dos marts; features (categoria, UF, órgão, modalidade, quantidade,
  unidade, mês, texto do item via TF-IDF ou embeddings).
- Baseline: mediana da categoria. Modelo: LightGBM (regressão sobre log do valor unitário).
- Validação temporal (treina no passado, testa no futuro) — nunca split aleatório.
- Métricas: MAE, MAPE, comparação com baseline; análise de erro por categoria.
- Regra de alerta: valor real acima do intervalo de predição (quantis) → possível sobrepreço.
- MLflow (serviço no Compose) registrando parâmetros, métricas e modelo.
- Endpoint `GET /contratacoes/{id}/avaliacao-preco` e job em lote gravando os alertas.
- Notebook ou relatório de análise em `docs/`.

**Conceitos:** baseline, vazamento de dados (data leakage), validação temporal, métricas de
regressão, regressão quantílica, rastreamento de experimentos.

**Testes obrigatórios**
- Pipeline de features é determinística e não usa informação do futuro (teste explícito de leakage).
- Split temporal: nenhuma data de teste anterior à maior data de treino.
- Em dados sintéticos com padrão conhecido, o modelo supera o baseline.
- Inferência com categoria nunca vista não quebra.
- Endpoint retorna o formato esperado.

**Pronto quando:** relatório mostra o modelo vs baseline com números e o experimento está no MLflow.

---

# FASE 6 — PRODUTO E ENTREGA

## Etapa 15 — Frontend: chat, alertas e testes E2E

**Objetivo:** expor as features de IA e ML na interface.

**Construir**
- Página de chat com o agente (streaming, citações clicáveis que abrem o edital na página).
- Página de alertas de sobrepreço com filtros e explicação do alerta.
- Detalhe do edital com os campos extraídos pelo LLM.
- Playwright rodando contra a stack do Compose (com `FakeLLM` ativado por variável).
- Job E2E no CI.

**Conceitos:** streaming no frontend (SSE), testes ponta a ponta, ambiente de teste determinístico.

**Testes obrigatórios**
- Componentes: renderização incremental do streaming, citações, estados de erro.
- E2E: fluxo "filtrar → abrir contratação → ver extração"; "perguntar ao agente → ver citação";
  "ver alerta de sobrepreço".

**Pronto quando:** E2E verde no CI.

---

## Etapa 16 — Orquestração e observabilidade

**Objetivo:** o pipeline roda sozinho e é possível saber o que está acontecendo.

**Construir**
- Prefect orquestrando: ingestão → bronze→silver → dbt build → job de alertas de ML,
  com retries e agendamento.
- Logs estruturados com `correlation_id` atravessando API, fila e workers.
- Endpoint `/metrics` (Prometheus) com contadores úteis (itens ingeridos, rejeitados,
  mensagens na DLQ, latência do LLM, tokens usados).
- Runbook em `docs/operacao.md` (o que fazer quando a DLQ enche, como reprocessar).

**Conceitos:** orquestração vs agendamento simples, observabilidade (logs, métricas),
correlação de requisições, operação de sistemas.

**Testes obrigatórios**
- Flow do Prefect executa as tarefas na ordem certa e para se uma etapa crítica falha.
- `correlation_id` gerado na API chega ao log do worker (integration).
- Métricas incrementam nos cenários esperados.

**Pronto quando:** o flow roda agendado e o runbook descreve como reprocessar uma DLQ.

---

## Etapa 17 — Deploy na nuvem e documentação final

**Objetivo:** projeto no ar, com link público e documentação de portfólio.

**Construir**
- Deploy em VM Linux de nuvem pública (Oracle free tier, GCP ou AWS) com Docker Compose,
  HTTPS via Caddy, firewall fechando tudo exceto 80/443.
- (Opcional) Terraform para criar a VM.
- Workflow de CD: build e push das imagens para GHCR; deploy via SSH ao criar tag.
- Backup do Postgres agendado.
- README final: problema do cliente, demo (GIF ou vídeo), diagrama de arquitetura,
  tabela "requisito → onde está no código", decisões (links para ADRs), resultados das
  avaliações (extração, RAG, ML), como a IA foi usada no desenvolvimento, próximos passos.

**Conceitos:** deploy, proxy reverso e TLS, segurança básica de servidor, CD, backups.

**Testes obrigatórios**
- Smoke test pós-deploy no workflow de CD (health da API e do frontend pela URL pública).
- Restauração do backup testada uma vez e documentada.

**Pronto quando:** link público funcionando e README pronto para enviar à recrutadora.
