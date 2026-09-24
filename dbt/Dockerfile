# Imagem do dbt (camada gold). Separada da do backend: só precisa do dbt e do SQL.

FROM python:3.12-slim
# mesma versão fixa do uv usada no backend
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 dbtuser
WORKDIR /dbt

# dependências primeiro (camada de cache), depois o projeto
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY --chown=dbtuser:dbtuser . .
# o dbt escreve target/ e logs/ dentro do projeto: o usuário precisa ser dono da pasta
RUN chown dbtuser:dbtuser /dbt
USER dbtuser

ENTRYPOINT ["dbt"]
CMD ["build"]
