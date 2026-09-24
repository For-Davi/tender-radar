# Plano de etapas — Radar de Licitações

Cada etapa segue o fluxo do `CLAUDE.md`: plano → aprovação → código + testes →
`make check` verde → documento de aprendizado → resumo → parar.

Formato de cada etapa:
- **Objetivo**: o que existe ao final que não existia antes.
- **Construir**: itens concretos.
- **Conceitos que você vai aprender**.
- **Testes obrigatórios**: o mínimo; o Claude Code pode (e deve) adicionar mais.
- **Pronto quando**: critérios verificáveis.

Este é o plano **enxuto**: cobre todos os requisitos da vaga com o menor número de peças.
Ficaram de fora (candidatos a "próximos passos" no README): agente com ferramentas,
Prefect, MLflow, MinIO, busca híbrida, Playwright E2E, Terraform.

---

# FASE 1 — FUNDAÇÃO

## Etapa 00 — Esqueleto, Docker e CI

**Objetivo:** repositório organizado, API mínima respondendo `/health`, stack de
infraestrutura subindo com um comando e todo push validado automaticamente.

**Construir**
- Estrutura de pastas do `CLAUDE.md` (pastas vazias com `.gitkeep` onde necessário).
- `.gitignore` (Python, Node, `.env`, dados, `*Zone.Identifier`), `.editorconfig`.
- `backend/pyproject.toml` com uv: fastapi, uvicorn, pydantic-settings, structlog;
  dev: pytest, pytest-cov, ruff, mypy, pre-commit.
- Configuração de ruff (lint + format), mypy strict, pytest (marcadores `unit`/`integration`,
  cobertura mínima 80%).
- `src/radar/config.py` com `Settings` (pydantic-settings) lendo variáveis de ambiente.
- `src/radar/api/main.py` com app FastAPI e rota `GET /health` → `{"status": "ok"}`.
- Logging estruturado configurado.
- `backend/Dockerfile` multi-stage (builder com uv → runtime slim, usuário não-root),
  a partir de `docs/referencia/Dockerfile`.
- `docker-compose.yml` com postgres (pgvector/pgvector:pg16), mongo, rabbitmq (com
  management) e api, com healthcheck e volumes nomeados. Base: `docs/referencia/docker-compose.yml`,
  ajustando `./services` para `./backend` e removendo o que saiu do plano (minio, mlflow).
- `infra/postgres/init.sql` habilitando a extensão `vector`.
- `.env.example` documentado, `.dockerignore`, `.pre-commit-config.yaml`.
- `Makefile`: `up`, `down`, `logs`, `ps`, `test`, `test-integration`, `lint`, `fmt`, `check`.
- `.github/workflows/ci.yml`: jobs `lint`, `test-unit` (com cobertura), `test-integration`
  (testcontainers no runner), `docker-build`; cache do uv.
- `README.md` inicial (problema de negócio, como rodar, badge do CI).
- `docs/adr/0001-estrutura-e-ferramentas.md` (primeiro ADR, explicando o formato).

**Conceitos:** uv, lint vs formatação vs tipos, configuração por ambiente (12-factor),
imagem vs container, multi-stage build, rede do Compose, healthcheck, pipeline de CI, ADRs.

**Testes obrigatórios**
- `unit`: `/health` retorna 200 e o corpo esperado; `Settings` lê variáveis, aplica padrões
  e falha com erro claro se uma variável estiver inválida.
- `integration`: teste de fumaça que conecta em cada serviço (Postgres `SELECT 1` e extensão
  `vector` existe; Mongo responde `ping`; RabbitMQ aceita conexão).
- Um PR de teste que quebra propositalmente um teste deixa o CI vermelho; corrigido, verde.

**Pronto quando:** `make check` passa; `make up` deixa todos os serviços `healthy`;
`docker compose exec api whoami` não é root; CI verde na branch principal.

---

# FASE 2 — DADOS

## Etapa 01 — Domínio e modelo relacional

**Objetivo:** entidades de negócio e o banco transacional normalizado, com migrações.

**Construir**
- `domain/`: entidades (Orgao, Contratacao, ItemContratacao, Fornecedor) e value objects
  (`Cnpj` com dígito verificador, `Dinheiro` com Decimal).
- Regras de negócio puras (ex.: status válidos, item não pode ter valor negativo).
- `adapters/postgres/`: modelos SQLAlchemy 2.0, sessão e repositórios implementando `ports/` (Protocols).
- Alembic com a primeira migração (PKs, FKs, índices, `UNIQUE` para idempotência —
  ex.: número de controle PNCP).
- Diagrama ER em Mermaid em `docs/modelo-relacional.md`.
- ADR: por que separar entidade de domínio do modelo ORM.

**Conceitos:** orientação a objetos, normalização (1FN–3FN), integridade referencial,
índices, padrão Repository, ports & adapters, migrações versionadas.

**Testes obrigatórios**
- `unit`: CNPJ (válidos, inválidos, com/sem máscara), regras das entidades, `Dinheiro` sem erro
  de ponto flutuante.
- `integration`: migração sobe e desce; repositório salva e busca; violação de `UNIQUE`/FK gera o
  erro de domínio esperado; `upsert` não duplica.

**Pronto quando:** `alembic upgrade head` funciona no container e todos os testes passam.

---

## Etapa 02 — Ingestão do PNCP (bronze + eventos)

**Objetivo:** processo que consome a API do PNCP de forma resiliente, guarda o dado bruto
e avisa o sistema.

**Construir**
- `docs/pncp-api.md` com os endpoints usados.
- `ports/contratacoes_source.py` e `adapters/pncp/client.py` com httpx: paginação, timeout,
  retry com backoff (tenacity) para 429/5xx e parsing para Pydantic.
- Respostas reais gravadas em `tests/fixtures/pncp/` (script manual, nunca no CI).
- `adapters/mongo/`: repositório bronze (JSON original + data de coleta, fonte, hash).
- PDFs dos editais salvos num volume Docker (`storage/editais/`), atrás de um port `DocumentStorage`.
- `adapters/rabbitmq/`: publicador com exchange, fila `edital.novo`, dead-letter queue,
  mensagens persistentes e evento versionado (Pydantic).
- `services/ingestao.py` (fonte → bronze → PDF → evento) e `workers/ingestao.py`
  (intervalo configurável e janela de datas); serviço `worker-ingestao` no Compose.
- Idempotência: reprocessar a mesma janela não duplica nada nem republica eventos.
- ADR: por que RabbitMQ (e não Kafka) e por que Mongo na camada bronze.

**Conceitos:** cliente HTTP, retry e backoff, fixtures gravadas, arquitetura medallion,
exchange/fila/routing key, ack, DLQ, idempotência, entrega "at-least-once".

**Testes obrigatórios**
- `unit` (`respx`, sem rede): parsing de resposta gravada; paginação para na última página;
  retry em 500/429 e desiste após N tentativas; sem retry em 400/404; campo inesperado gera
  erro de validação legível.
- `unit` com fakes em memória: fluxo completo; rodar 2x = mesmo estado; falha num PDF não
  derruba o lote.
- `integration` (Mongo, RabbitMQ reais): documento gravado e mensagem na fila com o schema correto.

**Pronto quando:** `make up` com o worker rodando popula o Mongo e a UI do RabbitMQ mostra
mensagens na fila.

---

## Etapa 03 — Pipeline bronze → silver com qualidade de dados

**Objetivo:** transformar o bruto em dados limpos no Postgres, sabendo o que foi rejeitado.

**Construir**
- `pipelines/bronze_to_silver.py`: lê bronze, normaliza (datas, valores, CNPJs, textos),
  valida com Pydantic e grava via repositórios da Etapa 01.
- Tabela `silver.registros_rejeitados` com motivo da rejeição.
- Processamento incremental (marca d'água pela data de coleta).
- Relatório de execução (lidos, gravados, rejeitados, duração) nos logs; `make pipeline`.

**Conceitos:** qualidade de dados (completude, validade, unicidade, consistência),
processamento incremental.

**Testes obrigatórios**
- Cada regra de limpeza com bordas ("1.234,56", data inválida, CNPJ com máscara, nulos).
- Registro inválido vai para rejeitados com o motivo certo e não interrompe o lote.
- Execução incremental processa só o que é novo.
- `integration`: bronze no Mongo → silver no Postgres, contagens batem.

**Pronto quando:** o pipeline sobre os dados da Etapa 02 popula o Postgres com números coerentes.

---

## Etapa 04 — Camada analítica com dbt (gold)

**Objetivo:** modelo dimensional pronto para análise, com SQL avançado e testes de dados.

**Construir**
- Projeto dbt em `dbt/` (dbt-postgres): `staging/` → `marts/`.
- Star schema: `fato_contratacao_item`, `dim_orgao`, `dim_fornecedor`, `dim_tempo`, `dim_categoria`.
- Marts com funções de janela:
  - variação de preço por categoria mês a mês (`LAG`);
  - ranking de fornecedores por órgão (`RANK`);
  - média móvel de 3 meses de valor contratado;
  - percentil do preço do item na categoria (`PERCENT_RANK`) — base do alerta de sobrepreço.
- Serviço `dbt` no Compose (profile `jobs`) e `make dbt`.

**Conceitos:** modelagem dimensional (fato, dimensão, granularidade), joins, agregações,
CTEs, funções de janela, testes de dados.

**Testes obrigatórios**
- Genéricos: `unique`, `not_null`, `relationships`, `accepted_values`.
- Singulares em SQL (soma dos itens = total da fato; nenhum preço negativo).
- Unit tests do dbt para pelo menos 2 marts com janela, com entrada e saída escritas à mão.

**Pronto quando:** `dbt build` roda sem falhas e o documento de aprendizado explica cada
função de janela com exemplo de entrada e saída.

---

# FASE 3 — APLICAÇÃO

## Etapa 05 — API REST

**Objetivo:** expor os dados para o frontend com uma API bem desenhada.

**Construir**
- Routers: `GET /contratacoes` (filtros: UF, órgão, categoria, período, faixa de valor;
  paginação; ordenação), `GET /contratacoes/{id}`, `GET /orgaos`, `GET /metricas/...` (marts).
- Schemas de resposta separados do domínio; erros padronizados (problem+json); CORS.
- Dependências injetadas via `Depends`.

**Conceitos:** design REST, paginação, validação de entrada, códigos HTTP, OpenAPI,
injeção de dependência.

**Testes obrigatórios**
- Cada endpoint: sucesso, filtros combinados, paginação (primeira/última/vazia), 404, 422.
- Com repositório falso (unit) e banco real (integration).
- Schema OpenAPI gerado sem erro (contrato).

**Pronto quando:** `/docs` mostra todos os endpoints documentados e os testes passam.

---

## Etapa 06 — Frontend: dashboard

**Objetivo:** interface para explorar as contratações.

**Construir**
- Next.js (App Router) + TypeScript strict, Tailwind, ESLint, Prettier.
- Cliente de API tipado com tipos gerados do OpenAPI (`openapi-typescript`).
- Páginas: dashboard (KPIs + gráficos com Recharts), lista com filtros e paginação, detalhe.
- Estados de carregamento, vazio e erro em todas as telas.
- Dockerfile do frontend, serviço no Compose e job de frontend no CI.

**Conceitos:** componentes, server vs client components, tipos via OpenAPI,
TanStack Query, acessibilidade básica.

**Testes obrigatórios** (Vitest + Testing Library + MSW)
- Filtros alteram a requisição à API; paginação funciona.
- Estados de loading, vazio e erro renderizados.
- Moeda e data em pt-BR.

**Pronto quando:** `make up` e `http://localhost:3000` mostra dados reais; testes verdes.

---

# FASE 4 — IA E ML

## Etapa 07 — Extração com LLM + avaliação

**Objetivo:** ler o PDF do edital, extrair campos estruturados e medir o quanto acerta.

**Construir**
- `ports/llm.py` (Protocol) com implementações Anthropic e `FakeLLM` (determinístico).
- Extração de texto do PDF (pdfplumber) preservando o número da página.
- Schema `EditalExtraido`: objeto, modalidade, valor estimado, prazos, exigências de
  habilitação, critério de julgamento — cada campo com a página de origem.
- Prompt versionado em arquivo (`llm/prompts/extracao_v1.md`).
- Saída validada; se inválida, uma nova tentativa com o erro, depois DLQ.
- `workers/extracao.py` consumindo `edital.novo` com ack manual, grava no Postgres.
- Log de tokens por chamada e limite de tamanho do documento.
- Golden set: ~10 editais anotados à mão em `data/golden_set/`; `llm/avaliacao.py`
  compara extraído × esperado por campo; relatório em Markdown; `make eval-extracao`.
- Endpoint `GET /contratacoes/{id}/extracao` (status: extraído, processando ou falhou).
- Frontend: seção "Dados extraídos do edital" no detalhe da contratação, com a página de
  origem de cada campo.

**Conceitos:** saída estruturada, engenharia e versionamento de prompt, consumidor com
ack/nack, abstração de provedor, avaliação de LLM, métricas por tipo de campo.

**Testes obrigatórios** (sempre com `FakeLLM`)
- Texto do PDF de fixture extraído com as páginas certas.
- Resposta válida vira `EditalExtraido`; inválida → nova tentativa → sucesso; inválida 2x → DLQ.
- `ack` só após gravar no banco (falha no banco → `nack`).
- Métricas de avaliação com casos conhecidos (acerto, parcial, erro, campo ausente, tolerância de valor).
- `integration`: mensagem publicada é consumida e o resultado aparece no Postgres.
- Endpoint `/extracao`: 200 com campos, estado "processando", 404 para contratação inexistente.
- Frontend (Vitest + MSW): seção renderiza os estados extraído, processando e falhou, e mostra
  a página de origem de cada campo.

**Pronto quando:** um edital real passa pelo fluxo com LLM real (execução manual), os campos
extraídos aparecem no detalhe da contratação e existe um relatório de avaliação sobre o golden set.

---

## Etapa 08 — RAG com pgvector

**Objetivo:** responder perguntas sobre os editais citando a página de origem.

**Construir**
- Chunking com sobreposição, preservando página.
- Embeddings (sentence-transformers local) em pgvector com índice HNSW.
- `POST /perguntar` com filtro opcional por edital: recupera, monta contexto e responde
  com citações (edital + página); "não encontrei" quando não há evidência.
- Avaliação do retrieval: recall@k sobre perguntas do golden set.
- Página de chat simples no frontend com citações.

**Conceitos:** embeddings, similaridade de cosseno, índices vetoriais, chunking,
grounding e citações, alucinação.

**Testes obrigatórios**
- Chunking: tamanho, sobreposição, sem perda de texto, página preservada.
- `integration`: documentos inseridos, busca retorna o chunk esperado no top-k.
- Endpoint com `FakeLLM`: citações válidas; sem contexto relevante → "não encontrei".
- recall@k correto em caso sintético.
- Frontend: citações renderizadas e estado de erro.

**Pronto quando:** recall@5 medido e registrado; perguntas reais respondidas com citação.

---

## Etapa 09 — Modelo de sobrepreço

**Objetivo:** estimar o valor esperado de um item e sinalizar valores fora do padrão,
com avaliação honesta.

**Construir**
- Dataset a partir dos marts; features (categoria, UF, modalidade, quantidade, unidade, mês).
- Baseline: mediana da categoria. Modelo: scikit-learn (gradient boosting sobre log do valor unitário).
- Validação temporal (treina no passado, testa no futuro).
- Métricas: MAE, MAPE, comparação com baseline, erro por categoria; relatório em `docs/`.
- Regra de alerta: valor real acima do intervalo de predição (quantis) → possível sobrepreço.
- Job em lote gravando alertas, `GET /contratacoes/{id}/avaliacao-preco` e página de alertas no frontend.

**Conceitos:** baseline, data leakage, validação temporal, métricas de regressão,
regressão quantílica.

**Testes obrigatórios**
- Features determinísticas e sem informação do futuro (teste explícito de leakage).
- Split temporal: nenhuma data de teste anterior à maior data de treino.
- Em dados sintéticos com padrão conhecido, o modelo supera o baseline.
- Categoria nunca vista não quebra a inferência.
- Endpoint e página de alertas no formato esperado.

**Pronto quando:** o relatório mostra modelo vs baseline com números e os alertas aparecem na interface.

---

# FASE 5 — ENTREGA

## Etapa 10 — Deploy na nuvem e documentação final

**Objetivo:** projeto no ar, com link público e documentação de portfólio.

**Construir**
- Deploy em VM Linux de nuvem pública (Oracle free tier, GCP ou AWS) com Docker Compose,
  HTTPS via Caddy, firewall fechando tudo exceto 80/443.
- Workflow de CD: build e push das imagens para GHCR; deploy via SSH ao criar tag.
- Backup do Postgres agendado (cron).
- README final: problema, demo (GIF), diagrama de arquitetura, tabela
  "requisito da vaga → onde está no código", ADRs, resultados das avaliações (extração,
  RAG, ML), como a IA foi usada no desenvolvimento, próximos passos.

**Conceitos:** deploy, proxy reverso e TLS, segurança básica de servidor, CD, backups.

**Testes obrigatórios**
- Smoke test pós-deploy no CD (health da API e do frontend pela URL pública).
- Restauração do backup testada uma vez e documentada.

**Pronto quando:** link público funcionando e README pronto para enviar à recrutadora.
