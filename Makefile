# Comandos do projeto. Rode `make` (ou `make help`) para ver a lista.

BACKEND := backend
UV := cd $(BACKEND) && uv run

.DEFAULT_GOAL := help
.PHONY: help up down down-volumes logs ps migrate migration ingest-once pncp-fixtures test test-integration lint fmt check pre-commit-install pre-commit actionlint

help: ## Lista os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-18s %s\n", $$1, $$2}'

# ---------- Docker ----------
.env: ## Cria o .env a partir do .env.example (só se ainda não existir)
	cp .env.example .env

up: .env ## Sobe a stack e espera todos os serviços ficarem healthy
	docker compose up -d --build --wait

down: ## Derruba a stack (mantém os dados nos volumes)
	docker compose down

down-volumes: ## Derruba a stack e APAGA os volumes (bancos zerados)
	docker compose down -v

logs: ## Logs de um serviço: make logs s=api
	docker compose logs -f $(s)

ps: ## Estado dos serviços
	docker compose ps

# ---------- Banco de dados ----------
migrate: ## Aplica as migrações pendentes (no container)
	docker compose run --rm --build migrate

migration: .env ## Gera uma migração a partir dos modelos: make migration m="descricao"
	@test -n "$(m)" || (echo "uso: make migration m=\"descricao da mudanca\"" && exit 1)
	cd $(BACKEND) && set -a && . ../.env && set +a && uv run alembic revision --autogenerate 		--rev-id $$(printf "%04d" $$(( $$(ls alembic/versions/*.py | wc -l) + 1 ))) -m "$(m)"

# ---------- Ingestão ----------
ingest-once: ## Roda uma ingestão agora (no container) e termina
	docker compose run --rm --build worker-ingestao python -m radar.workers.ingestao --once

pncp-fixtures: ## Regrava as fixtures do PNCP a partir da API real (manual, nunca no CI)
	$(UV) python scripts/gravar_fixtures_pncp.py

# ---------- Qualidade ----------
test: ## Testes unitários (rápidos, sem Docker)
	$(UV) pytest -m unit

test-integration: ## Testes de integração (sobem containers com testcontainers)
	$(UV) pytest -m integration

lint: ## ruff (lint + formato) e mypy
	$(UV) ruff check .
	$(UV) ruff format --check .
	$(UV) mypy src tests

fmt: ## Formata o código e aplica correções automáticas do ruff
	$(UV) ruff format .
	$(UV) ruff check --fix .

check: lint ## Critério de "pronto": lint + tipos + testes unitários com cobertura >= 80%
	$(UV) pytest -m unit --cov --cov-report=term-missing

pre-commit-install: ## Instala os hooks do git (rodam a cada commit)
	$(UV) pre-commit install

pre-commit: ## Roda os hooks do pre-commit em todos os arquivos
	$(UV) pre-commit run --all-files

actionlint: ## Valida os workflows do GitHub Actions (via Docker)
	docker run --rm -v "$$PWD:/repo" -w /repo rhysd/actionlint:latest
