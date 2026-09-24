# Comandos do projeto. Rode `make` (ou `make help`) para ver a lista.

BACKEND := backend
UV := cd $(BACKEND) && uv run

.DEFAULT_GOAL := help
.PHONY: help up down down-volumes logs ps test test-integration lint fmt check

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
