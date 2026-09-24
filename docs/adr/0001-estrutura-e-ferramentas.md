# ADR 0001 — Estrutura do repositório e ferramentas de base

- **Status:** aceito
- **Data:** 2026-09-24
- **Etapa:** 00

## Sobre os ADRs

Um ADR (*Architecture Decision Record*) registra **uma** decisão importante: o contexto,
o que foi decidido, as alternativas e as consequências. Serve para que, daqui a meses,
alguém (inclusive você) entenda *por que* o projeto é assim, e não só *como* ele é.
ADRs não são editados depois de aceitos: se a decisão mudar, cria-se um ADR novo que
substitui o antigo. Os arquivos são numerados em ordem (`0001-...`, `0002-...`).

Formato usado: **Contexto → Decisão → Alternativas consideradas → Consequências**.

## Contexto

O projeto vai ter backend Python, frontend TypeScript, dbt, vários serviços de
infraestrutura e testes com containers reais. É um projeto de estudo e portfólio: precisa
ser fácil de rodar por quem clonar e ter qualidade verificável automaticamente.

## Decisão

1. **Monorepo** com uma pasta por "mundo": `backend/`, `frontend/`, `dbt/`, `infra/`, `docs/`.
2. **Backend com layout `src/`** (`backend/src/radar`) e arquitetura em camadas
   (`domain`, `ports`, `adapters`, `services`, `api`, `workers`...), como descrito no `CLAUDE.md`.
3. **uv** para dependências e versão do Python, com `uv.lock` versionado.
4. **ruff** para lint e formatação; **mypy strict** para tipos; **pytest** com marcadores
   `unit`/`integration` atribuídos automaticamente pela pasta; cobertura mínima de 80%
   medida só nos testes unitários.
5. **testcontainers** para testes de integração com serviços reais e descartáveis.
6. **Makefile** como interface única de comandos (`make up`, `make check`...), usada
   tanto localmente quanto como referência para o CI.
7. **GitHub Actions** com jobs separados (lint, unit, integration) e build Docker só
   depois que todos passam. `dev` é a branch principal.
8. **Imagem Docker única** para API e workers, multi-stage, rodando como usuário não-root.

## Alternativas consideradas

| Decisão | Alternativa | Por que não |
|---|---|---|
| Monorepo | Um repositório por parte | Para um projeto de uma pessoa, sincronizar vários repositórios só gera atrito; o avaliador vê tudo num lugar |
| uv | pip + venv / Poetry | pip não tem lockfile nativo; Poetry é mais lento e não gerencia a versão do Python |
| Layout `src/` | Pacote na raiz do backend | No layout "flat", o teste pode importar a pasta local e esconder erro de empacotamento |
| ruff | flake8 + black + isort | Três ferramentas e três configurações para o que o ruff faz sozinho, mais rápido |
| testcontainers | Testar contra a stack do `make up` | Dependeria de estado externo (dados de execuções anteriores) e de alguém ter subido a stack |
| Cobertura só dos unitários | Somar unitários + integração | O `make check` ficaria lento e dependente do Docker; a integração é validada em job próprio no CI |
| Um job de CI | Vários jobs | Um job só é mais simples, mas esconde qual verificação falhou e não roda em paralelo |

## Consequências

- **Positivas:** `make up` e `make check` bastam para rodar e validar tudo; o CI repete as
  mesmas verificações; testes de integração são reprodutíveis em qualquer máquina com Docker.
- **Negativas:** testes de integração exigem Docker e levam alguns segundos para subir os
  containers; o mypy strict exige anotar tudo, o que dá mais trabalho no começo.
- **A observar:** se o frontend crescer muito, pode valer um gerenciador de monorepo
  (ex.: workspaces); por enquanto, cada pasta tem suas próprias ferramentas.
