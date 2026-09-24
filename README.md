# Radar de Licitações

[![CI](https://github.com/For-Davi/tender-radar/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/For-Davi/tender-radar/actions/workflows/ci.yml)

Plataforma que coleta as contratações públicas do **PNCP** (Portal Nacional de Contratações
Públicas), organiza os dados, lê os editais com LLM, responde perguntas sobre eles com
citação da página e aponta itens com possível **sobrepreço**.

## O problema

O PNCP publica milhares de contratações por dia, mas os dados chegam crus e os detalhes
importantes estão escondidos em PDFs longos. Dois públicos sofrem com isso:

- **Fornecedores** querem achar licitações do seu ramo e entender rápido o que o edital exige.
- **Analistas de controle** (auditores, jornalistas) querem acompanhar os gastos e achar
  preços fora do padrão.

## Arquitetura (visão alvo)

```
PNCP (API) → worker de ingestão → MongoDB (bronze) → pipeline → PostgreSQL (silver)
                    │                                                  │
                    └─> RabbitMQ "edital.novo" → worker de extração    └─> dbt (gold)
                                                  (LLM → Postgres)            │
                                       FastAPI (REST, RAG, ML) ◄──────────────┘
                                                  │
                                       Next.js (dashboard, chat, alertas)
```

O plano completo, etapa por etapa, está em [docs/ETAPAS.md](docs/ETAPAS.md) e o andamento em
[docs/PROGRESSO.md](docs/PROGRESSO.md).

## Stack

| Área | Tecnologias |
|---|---|
| Backend | Python 3.12, uv, FastAPI, Pydantic, SQLAlchemy, Alembic, structlog |
| Dados | PostgreSQL 16 + pgvector, MongoDB, RabbitMQ, dbt |
| IA / ML | LLM (Anthropic), RAG com pgvector, scikit-learn |
| Frontend | Next.js, TypeScript |
| Qualidade | pytest, testcontainers, ruff, mypy (strict), pre-commit |
| Entrega | Docker, Docker Compose, GitHub Actions |

## Como rodar

Pré-requisitos: Linux (ou WSL2), Docker com Compose v2, `make` e [uv](https://docs.astral.sh/uv/).

```bash
make up          # cria o .env, sobe Postgres, Mongo, RabbitMQ e a API, espera ficarem healthy
curl localhost:8000/health        # {"status":"ok"}
make down        # derruba a stack (os dados continuam nos volumes)
```

| Serviço | Endereço local |
|---|---|
| API (docs interativas) | http://localhost:8000/docs |
| RabbitMQ (UI de gestão) | http://localhost:15672 (usuário e senha do `.env`) |
| PostgreSQL | `localhost:5432` |
| MongoDB | `localhost:27017` |

Para rodar a API fora do Docker, com recarga automática:

```bash
cd backend && uv run uvicorn radar.api.main:app --reload
```

## Desenvolvimento

```bash
make help              # lista todos os comandos
make test              # testes unitários (rápidos, sem Docker)
make test-integration  # testes com containers reais (precisa de Docker)
make lint              # ruff + mypy
make fmt               # formata o código
make check             # critério de "pronto": lint + tipos + testes + cobertura >= 80%
make pre-commit-install  # instala os hooks que rodam a cada commit
```

## Documentação

- [Decisões de arquitetura (ADRs)](docs/adr/)
- [Documentos de aprendizado por etapa](docs/aprendizado/)
