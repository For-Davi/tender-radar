# Imagem única para a API e os workers (muda só o command no docker-compose).

# ---------- Stage 1: builder — instala as dependências com uv ----------
FROM python:3.12-slim AS builder
# versão fixa do uv: o build de hoje e o de daqui a 6 meses usam a mesma ferramenta
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv
WORKDIR /app
# COMPILE_BYTECODE: gera os .pyc no build (a app sobe mais rápido)
# LINK_MODE=copy: copia arquivos em vez de hardlink (o cache e o destino ficam em camadas diferentes)
# PYTHON_DOWNLOADS=never: usa o Python da imagem, nunca baixa outro
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

# Só os arquivos de dependência primeiro: enquanto eles não mudarem, o Docker
# reaproveita esta camada do cache e não reinstala nada ao mudar o código.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Agora o código. --no-editable instala o pacote "de verdade" dentro do .venv,
# então o runtime precisa copiar só o .venv (sem a pasta src).
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# ---------- Stage 2: runtime — imagem final enxuta ----------
FROM python:3.12-slim AS runtime

# Usuário sem privilégios: se a app for invadida, o atacante não é root no container.
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
# migrações: usadas pelo serviço "migrate" do docker-compose (alembic upgrade head)
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser alembic ./alembic
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1

# nunca rodar como root (comentário em linha própria: o Docker não aceita comentário no fim da instrução)
USER appuser
EXPOSE 8000
CMD ["uvicorn", "radar.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
