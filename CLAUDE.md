# CLAUDE.md — Regras de trabalho do projeto Radar de Licitações

Este projeto é um portfólio de estudo. O dono do projeto quer **entender cada linha**,
então o objetivo não é só entregar código: é entregar código + explicação + testes.

## Contexto do projeto

Plataforma que ingere contratações públicas do PNCP (Portal Nacional de Contratações
Públicas), extrai informações dos editais com LLM, permite perguntas via RAG, detecta
possível sobrepreço com ML e exibe tudo num dashboard.

Stack: Python 3.12 (uv, FastAPI, SQLAlchemy, Alembic, httpx, pydantic, scikit-learn, pytest),
PostgreSQL 16 + pgvector, MongoDB, RabbitMQ, dbt,
Next.js + TypeScript (Vitest, Testing Library, MSW), Docker Compose, GitHub Actions.

O plano completo está em `docs/ETAPAS.md`. O andamento está em `docs/PROGRESSO.md`.

## Estrutura de pastas (tudo dentro desta pasta raiz)

```
radar-licitacoes/
├── CLAUDE.md
├── README.md
├── Makefile                 # comandos únicos: make up, make test, make check...
├── docker-compose.yml
├── .env.example             # nunca commitar .env
├── .github/workflows/       # CI
├── backend/                 # tudo que é Python
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic/
│   ├── src/radar/
│   │   ├── config.py        # settings via pydantic-settings
│   │   ├── domain/          # entidades e regras de negócio (sem I/O)
│   │   ├── ports/           # interfaces (Protocols) que o domínio precisa
│   │   ├── adapters/        # implementações: postgres, mongo, rabbitmq, storage, pncp, llm
│   │   ├── services/        # casos de uso que orquestram domínio + ports
│   │   ├── api/             # FastAPI (routers, schemas, dependências)
│   │   ├── workers/         # processos consumidores/agendados
│   │   ├── pipelines/       # bronze -> silver
│   │   ├── llm/             # extração, RAG, avaliação
│   │   └── ml/              # features, treino, avaliação, inferência
│   └── tests/
│       ├── unit/            # rápidos, sem I/O real
│       ├── integration/     # com containers reais (testcontainers)
│       ├── fixtures/        # JSONs e PDFs de exemplo
│       └── conftest.py
├── dbt/                     # camada analítica (staging -> marts)
├── frontend/                # Next.js + TypeScript
├── infra/                   # init.sql, scripts, terraform (opcional)
├── data/golden_set/         # editais anotados à mão para avaliar o LLM
└── docs/
    ├── ETAPAS.md
    ├── PROGRESSO.md
    ├── aprendizado/         # uma explicação por etapa (etapa-00.md, etapa-01.md...)
    ├── adr/                 # decisões de arquitetura
    └── referencia/          # arquivos de referência fornecidos pelo dono
```

## Fluxo obrigatório de cada etapa

1. **Uma etapa por vez.** Trabalhe apenas na etapa pedida. Nunca adiante trabalho de
   etapas futuras, nem "aproveite para" refatorar coisas fora do escopo.
2. **Plano antes de código.** Antes de escrever qualquer arquivo, apresente:
   - lista de arquivos que serão criados/alterados;
   - decisões técnicas e o porquê (com alternativas consideradas);
   - lista dos testes que serão escritos e o que cada um prova.
   Depois **pare e espere a aprovação**.
3. **Branch por etapa:** `git checkout -b etapa-XX-nome-curto`.
4. **Implemente em passos pequenos**, escrevendo os testes junto com o código
   (de preferência o teste primeiro). Após cada passo relevante, rode os testes.
5. **Validação final:** rode `make check` (lint + tipos + testes + cobertura).
   A etapa só termina com tudo verde. Mostre a saída dos comandos.
6. **Documento de aprendizado:** crie `docs/aprendizado/etapa-XX.md` seguindo o modelo abaixo.
7. **Marque a etapa como concluída** em `docs/PROGRESSO.md` (troque `[ ]` por `[x]`) ao finalizá-la
   e, se houve decisão arquitetural, crie um ADR em `docs/adr/`.
8. **Commits** pequenos com Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
9. **Resumo no chat:** o que foi feito, como rodar, como os testes provam que funciona,
   e 3 perguntas de revisão para o dono testar o próprio entendimento.
   Depois **pare** e espere o pedido da próxima etapa.

## Modelo do documento de aprendizado (`docs/aprendizado/etapa-XX.md`)

```
# Etapa XX — Nome
## O que foi construído (visão geral em 1 parágrafo)
## Como a lógica funciona (passo a passo, com trechos curtos de código)
## Decisões e alternativas (por que assim e não de outro jeito)
## Conceitos novos (explicação didática de cada conceito/biblioteca usada)
## Testes (o que cada teste verifica e por que ele importa)
## Como rodar e ver funcionando (comandos exatos)
## Erros comuns e como depurar
## Perguntas de revisão
```

## Regras de qualidade de código

- Tipagem completa (mypy em modo strict no `src/`). Sem `Any` sem justificativa.
- Identificadores em inglês; termos de domínio sem tradução natural podem ficar em
  português (ex.: `edital`, `orgao`). Comentários, docstrings e docs em português.
- Funções pequenas, responsabilidade única. Domínio não importa nada de `adapters`.
- Dependências entram por injeção (construtor/`Depends`), nunca instanciadas "no meio" do código.
- Configuração só via variáveis de ambiente (`config.py`). Nenhum segredo no código.
- Logs estruturados (structlog), nunca `print` em código de produção.
- Erros tratados explicitamente; nada de `except Exception: pass`.

## Regras de testes

- Toda etapa entrega testes. Cobertura mínima do backend: **80%** (o CI falha abaixo disso).
- Marcadores do pytest: `unit` (padrão, sem I/O), `integration` (containers via testcontainers).
- **Testes nunca chamam APIs externas reais nem LLMs pagos.** Use `respx` para HTTP,
  um `FakeLLM` determinístico e fixtures gravadas em `tests/fixtures/`.
- Cada bug encontrado ganha primeiro um teste que o reproduz, depois a correção.
- **Proibido** fazer um teste passar apagando-o, pulando-o (`skip`), afrouxando o `assert`
  ou mockando o próprio código sob teste. Se um teste falha, corrija a causa raiz e explique.
- Teste casos de erro e bordas, não só o caminho feliz.
- Frontend: Vitest + Testing Library + MSW para componentes.

## Comandos (Makefile)

- `make up` / `make down` — sobe/derruba a stack Docker
- `make test` — testes unitários
- `make test-integration` — testes de integração
- `make lint` — ruff + ruff format --check + mypy (+ eslint/tsc no frontend)
- `make check` — tudo acima + cobertura (é o critério de "pronto")
- `make logs s=<serviço>` — logs de um serviço
