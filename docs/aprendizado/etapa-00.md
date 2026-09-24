# Etapa 00 — Esqueleto, Docker e CI

## O que foi construído (visão geral em 1 parágrafo)

A fundação do projeto: um backend Python com uma API FastAPI que responde `GET /health`,
configuração lida de variáveis de ambiente (com validação), logs estruturados, a
infraestrutura (PostgreSQL com pgvector, MongoDB e RabbitMQ) subindo com um único
`make up`, testes unitários e de integração, ferramentas de qualidade (ruff, mypy,
pre-commit) e um pipeline de CI no GitHub Actions que valida cada push e PR. Ainda não
existe regra de negócio: esta etapa só garante que tudo que vier depois tenha onde morar
e seja verificado automaticamente.

## Como a lógica funciona (passo a passo, com trechos curtos de código)

### 1. Configuração: `backend/src/radar/config.py`

`Settings` herda de `BaseSettings` (pydantic-settings). Cada campo é lido da variável de
ambiente com o mesmo nome em maiúsculas; se ela não existir, vale o padrão.

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    log_level: LogLevel = "INFO"  # LogLevel = Literal["DEBUG", "INFO", ...]
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_password: SecretStr = SecretStr("radar")
```

- `Literal[...]`: só aceita aqueles valores. `LOG_LEVEL=banana` gera `ValidationError`.
- `Field(ge=1, le=65535)`: a porta tem que estar nessa faixa; `"abc"` nem vira `int`.
- `SecretStr`: ao imprimir as settings aparece `**********`, e a senha não vaza em log.
- `frozen=True`: ninguém altera a configuração no meio do código.
- `extra="ignore"`: variáveis que não são campos (ex.: `MONGO_ROOT_USER`) são ignoradas.

Um *validator* roda **antes** da validação do `Literal` e aceita `info` em minúsculas:

```python
@field_validator("log_level", mode="before")
@classmethod
def _normalize_log_level(cls, value: object) -> object:
    return value.upper() if isinstance(value, str) else value
```

A URL do banco é uma `@property` montada a partir das partes. O `quote` codifica
caracteres especiais: uma senha `p@ss` sem codificação quebraria a URL, porque `@`
separa o usuário do host.

### 2. Logs: `backend/src/radar/logging_setup.py`

O structlog passa cada evento por uma lista de *processors* (funções em sequência) e,
no fim, por um *renderer*:

```python
processors = [merge_contextvars, add_log_level, TimeStamper(fmt="iso", utc=True)]
if json_output:
    processors += [format_exc_info, JSONRenderer()]  # container
else:
    processors.append(ConsoleRenderer(colors=False))  # terminal
```

Uso no código: `structlog.get_logger().info("app_criada", environment="dev")`.
Em container, a saída é uma linha JSON:
`{"environment": "dev", "event": "app_criada", "level": "info", "timestamp": "..."}`.

O arquivo se chama `logging_setup.py`, e não `logging.py` como estava no plano, para não
confundir com o módulo `logging` da biblioteca padrão, que ele próprio importa.

### 3. API: `backend/src/radar/api/main.py` e `health.py`

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    app = FastAPI(title=settings.app_name, version=version("radar"))
    app.state.settings = settings
    app.include_router(health_router)
    return app


app = create_app()  # o que o uvicorn carrega
```

`create_app` é uma **factory**: quem chama decide a configuração. O teste passa
`Settings(app_name="radar-teste")`; o uvicorn usa o `app` do fim do arquivo, com as
settings do ambiente. A rota fica num `APIRouter` separado, e cada grupo de rotas futuro
(contratações, órgãos...) ganha o seu.

`/health` devolve um modelo Pydantic (`HealthResponse`) com `status: Literal["ok"]`. O
modelo documenta a resposta no OpenAPI (`/docs`) e garante o formato.

### 4. Docker: `backend/Dockerfile`

Build **multi-stage**:

1. **builder**: instala o uv, copia **só** `pyproject.toml` e `uv.lock`, instala as
   dependências; depois copia `src/` e instala o pacote.
2. **runtime**: imagem limpa, cria `appuser`, copia **só** o `.venv` do builder.

Copiar primeiro só os arquivos de dependência aproveita o **cache de camadas**: se você
muda uma linha de código, o Docker reaproveita a camada das dependências (a parte lenta)
e refaz só a do código.

### 5. Compose: `docker-compose.yml`

Quatro serviços (`postgres`, `mongo`, `rabbitmq`, `api`), cada um com **healthcheck**. A
API só sobe depois que os outros três estão `healthy`:

```yaml
depends_on:
  postgres: { condition: service_healthy }
```

Dentro da rede do Compose, o nome do serviço é o hostname. Por isso o Compose sobrescreve
`POSTGRES_HOST: postgres` para a API (no `.env` está `localhost`, que serve para rodar
a API fora do Docker).

`make up` roda `docker compose up -d --build --wait`: o `--wait` só termina quando todos
os serviços estão healthy, ou falha se algum não ficar.

### 6. Testes com marcadores automáticos: `backend/tests/conftest.py`

```python
def pytest_collection_modifyitems(items):
    for item in items:
        folder = item.path.relative_to(_TESTS_DIR).parts[0]
        if folder in ("unit", "integration"):
            item.add_marker(folder)
```

Um teste em `tests/integration/` recebe o marcador `integration` sozinho. `make test`
roda `pytest -m unit` e nunca sobe container por engano.

### 7. CI: `.github/workflows/ci.yml`

Três jobs em paralelo (`lint`, `test-unit`, `test-integration`) e um quarto
(`docker-build`) com `needs:` nos três, que só roda se todos passarem. O
`astral-sh/setup-uv` guarda em cache os pacotes baixados, com chave no `uv.lock`.
`uv sync --locked` falha se o `pyproject.toml` foi alterado sem atualizar o lock.

## Decisões e alternativas (por que assim e não de outro jeito)

As decisões estruturais estão no [ADR 0001](../adr/0001-estrutura-e-ferramentas.md).
Decisões menores desta etapa:

| Decisão | Alternativa | Por quê |
|---|---|---|
| Campos separados para o Postgres + `postgres_dsn` como property | Uma variável `DATABASE_URL` | Cada parte é validada com erro claro, e os nomes batem com os que a imagem do Postgres espera (`POSTGRES_USER`...) |
| Sem `env_file` no `Settings` | Ler `.env` automaticamente | 12-factor: a app só lê o ambiente. Quem carrega o `.env` é o Compose. Assim um `.env` esquecido na máquina não muda o resultado dos testes |
| Healthcheck da API em Python (`urllib`) | `curl` (como no Dockerfile de referência) | Instalar curl exigiria `apt-get` e aumentaria a imagem; o Python já está lá |
| `uv sync --no-editable` no Docker | Instalação editável (padrão) | O pacote é instalado dentro do `.venv`, então o runtime copia só o `.venv` e não precisa de `src/` |
| Versão do uv fixa na imagem (`0.12.18`) | `uv:latest` | `latest` muda sem aviso; um build pode quebrar de um dia para o outro sem mudança no código |
| Portas presas a `127.0.0.1` | `"5432:5432"` | Sem o IP, a porta fica aberta para a rede inteira (ex.: Wi-Fi público) |
| Usuário próprio no RabbitMQ | `guest` padrão | O `guest` só aceita conexões de localhost, e a API conecta vindo de outro container |
| `httpx2` no TestClient | `httpx` | O Starlette atual marca o uso de `httpx` no TestClient como obsoleto |
| gitleaks no pre-commit | `detect-private-key` | O `detect-private-key` só acha chaves privadas; o gitleaks acha também tokens e API keys |

**Correções em relação aos arquivos de referência:**
- No `Dockerfile` de referência, a linha `USER appuser   # nunca rodar como root` quebra o build:
  o Docker **não aceita comentário no fim de uma instrução**, e trataria `#`, `nunca`...
  como parte do nome do usuário. O comentário foi para uma linha própria.
- Os arquivos `*:Zone.Identifier` (metadados que o Windows cria ao copiar para o WSL) estavam
  versionados. Como `:` é inválido em nome de arquivo no Windows, o clone quebraria lá.
  Foram removidos e entraram no `.gitignore`.

## Conceitos novos (explicação didática de cada conceito/biblioteca usada)

- **uv**: gerenciador de pacotes e de versões do Python. `uv add pacote` atualiza o
  `pyproject.toml` (o que você *quer*) e o `uv.lock` (as versões *exatas* resolvidas).
  `uv run comando` roda dentro do ambiente virtual do projeto sem precisar ativá-lo.
  O `.python-version` diz ao uv qual Python usar; ele baixa o 3.12 se não houver.
- **Lint × formatação × checagem de tipos**:
  - *lint* (`ruff check`): procura erros e más práticas (import não usado, `assert` em
    produção, senha escrita no código);
  - *formatação* (`ruff format`): só estilo (espaços, quebras de linha), sem mudar o que o
    código faz;
  - *tipos* (`mypy --strict`): verifica, sem executar, se os tipos batem (ex.: passar `str`
    onde se espera `int`). O `strict` exige anotação em tudo.
- **12-factor / configuração por ambiente**: o mesmo código (a mesma imagem) roda em dev,
  CI e produção; só as variáveis de ambiente mudam. Segredos nunca ficam no código.
- **Log estruturado**: log como dados (chave/valor), não como texto livre. Dá para filtrar
  `level=error AND event=app_criada` numa ferramenta de logs, o que não é possível com
  `print("deu erro aqui")`.
- **Imagem × container**: a imagem é o "molde" (somente leitura, feita pelo `docker build`);
  o container é uma instância rodando a partir dela. Várias instâncias podem sair da mesma imagem.
- **Camadas e cache**: cada instrução do Dockerfile gera uma camada. Se nada do que ela usa
  mudou, o Docker reaproveita a camada do cache.
- **Multi-stage build**: vários `FROM` no mesmo Dockerfile. O primeiro estágio tem as
  ferramentas de build; o último copia só o resultado. A imagem final fica menor (160 MB aqui)
  e com menos superfície de ataque.
- **Volume nomeado** (`pg_data`): guarda os dados fora do container. `make down` apaga os
  containers e mantém os dados; `make down-volumes` apaga tudo.
- **Healthcheck**: comando que o Docker executa periodicamente para saber se o serviço está
  *pronto*, e não só *rodando*. O Postgres, por exemplo, leva alguns segundos entre o processo
  subir e aceitar conexões.
- **testcontainers**: biblioteca que, dentro do teste, sobe um container Docker real,
  informa host e porta e o destrói no final. É o banco de verdade, sem mock.
- **Fixture com `scope="module"`**: o container sobe **uma vez** para todos os testes do
  arquivo, não uma vez por teste (seriam ~15 s cada).
- **pre-commit**: framework que roda verificações (hooks) automaticamente a cada `git commit`.
  Se algum hook falhar, o commit é bloqueado.
- **CI (integração contínua)**: um servidor limpo (o *runner*) baixa o código e roda as
  verificações a cada push ou PR. Acaba com o "na minha máquina funciona", porque a máquina
  do CI não tem nada instalado além do que o projeto declara.
- **ADR**: registro curto de uma decisão de arquitetura. Veja o formato no ADR 0001.
- **TDD (vermelho → verde)**: os testes da configuração, do log e do `/health` foram escritos
  **antes** do código. Primeiro rodaram e falharam (os módulos não existiam), depois o código
  foi escrito até passarem.

## Testes (o que cada teste verifica e por que ele importa)

**Unitários — 21 testes, sem I/O, ~1 s**

| Arquivo | Teste | O que prova |
|---|---|---|
| `test_config.py` | `test_settings_defaults` | Sem variáveis, os padrões valem (a app sobe "do zero") |
| | `test_settings_reads_env_vars` | Variáveis sobrescrevem os padrões e texto vira `int`/`bool` |
| | `test_settings_log_level_is_case_insensitive` | `warning` é aceito como `WARNING` |
| | `test_settings_invalid_log_level_fails_clearly` | Valor inválido gera **um** erro, apontando o campo `log_level` |
| | `test_settings_invalid_port_fails_clearly` (×3) | `abc`, `0` e `70000` são rejeitados com erro em `postgres_port` |
| | `test_settings_invalid_environment_fails` | Só `dev`, `test` e `prod` são aceitos |
| | `test_postgres_dsn_is_built_from_parts` | A URL do banco é montada no formato certo |
| | `test_postgres_dsn_escapes_special_chars_in_password` | `@` e `/` na senha são codificados (`%40`, `%2F`) |
| | `test_password_is_not_exposed_in_repr` | A senha não aparece ao imprimir as settings |
| `test_health.py` | `test_health_returns_200_and_ok` | O contrato do `/health`: 200 + `{"status": "ok"}` |
| | `test_health_is_json` | O `content-type` é `application/json` |
| | `test_unknown_route_returns_404` | Rota inexistente responde 404 |
| | `test_health_rejects_post` | Método errado responde 405 |
| | `test_create_app_uses_injected_settings` | A factory usa as settings recebidas (injeção de dependência) |
| `test_logging.py` | `test_logging_json_output` | Em modo JSON, a saída é JSON válido com `event`, `level`, `timestamp` e campos extras |
| | `test_logging_one_json_object_per_line` | Cada evento é uma linha (formato que as ferramentas de log esperam) |
| | `test_logging_respects_level` | Com nível INFO, `debug` é descartado e `warning` passa |
| | `test_logging_console_output_is_human_readable` | O modo terminal é texto legível, não JSON |
| | `test_logging_includes_exception_traceback_in_json` | `logger.exception` coloca o traceback no JSON |

A fixture `clean_env` apaga as variáveis antes de cada teste de configuração. Sem ela, um
`LOG_LEVEL=DEBUG` no seu terminal faria `test_settings_defaults` falhar na sua máquina e
passar no CI. As fixtures `reset_logging` restauram o structlog depois de cada teste, para
um teste não "vazar" configuração para o seguinte.

**Integração — 4 testes, containers reais, ~15 s**

| Teste | O que prova |
|---|---|
| `test_postgres_select_1_and_vector_extension` | O Postgres responde, **o nosso `init.sql`** habilita o `vector` e a URL gerada por `Settings` conecta de verdade |
| `test_postgres_init_sql_is_idempotent` | Rodar o `init.sql` duas vezes não dá erro (`IF NOT EXISTS`) |
| `test_mongo_ping` | O Mongo aceita conexão e responde `ping` |
| `test_rabbitmq_accepts_connection_and_declares_queue` | O RabbitMQ aceita conexão AMQP e cria uma fila |

**Verificações manuais feitas** (saídas reais):

```
$ make up        → api, mongo, postgres, rabbitmq: Up (healthy)
$ curl localhost:8000/health                  → {"status":"ok"}  HTTP 200
$ docker compose exec api whoami              → appuser
$ psql ... "select extname, extversion ..."   → vector|0.8.6
$ make actionlint                             → sem problemas
$ make pre-commit                             → todos os hooks Passed
```

## Como rodar e ver funcionando (comandos exatos)

```bash
# uma vez: instalar o uv
curl -LsSf https://astral.sh/uv/install.sh | sh

cd ~/tender-radar
make up                                    # sobe tudo e espera ficar healthy
make ps                                    # estado dos serviços
curl localhost:8000/health                 # {"status":"ok"}
open http://localhost:8000/docs            # documentação interativa (Swagger)
docker compose exec api whoami             # appuser
make logs s=api                            # logs JSON da API (Ctrl+C para sair)

make check                                 # lint + tipos + testes + cobertura
make test-integration                      # testes com containers reais
make pre-commit-install                    # hooks rodando a cada commit

make down                                  # derruba (mantém dados)
```

Rodar a API fora do Docker, com recarga automática ao salvar:

```bash
cd backend && uv run uvicorn radar.api.main:app --reload
```

## Erros comuns e como depurar

| Sintoma | Causa provável | Como resolver |
|---|---|---|
| `uv: command not found` | O `~/.local/bin` não está no PATH do terminal atual | Abra um terminal novo ou rode `source ~/.profile` |
| `Expected a Python module at: src/radar/__init__.py` | O pacote não tem `__init__.py` | Aconteceu nesta etapa: o `uv add` precisa do pacote existindo |
| `make up` para com `container ... is unhealthy` | Um serviço não ficou pronto | `make logs s=<serviço>`; `docker inspect --format '{{json .State.Health}}' radar-<serviço>-1` mostra a saída do healthcheck |
| `port is already allocated` | Outro Postgres/Mongo já usa a porta na máquina | Pare o outro serviço ou mude a porta publicada no Compose |
| Extensão `vector` não existe após mudar o `init.sql` | O `init.sql` só roda na **primeira** criação do volume | `make down-volumes && make up` (apaga os dados!) |
| `ValidationError` ao subir a API | Variável de ambiente inválida no `.env` | Leia a mensagem: ela diz o campo e o valor aceito |
| Teste de integração falha com erro de Docker | Docker Desktop desligado ou sem integração com o WSL | Abra o Docker Desktop → Settings → Resources → WSL integration |
| Commit bloqueado pelo pre-commit | Um hook falhou (ex.: ruff ou gitleaks) | Leia a saída; o ruff e o `end-of-file-fixer` corrigem sozinhos, é só rodar `git add` de novo |
| CI falha em `uv sync --locked` | O `pyproject.toml` mudou sem o `uv.lock` | Rode `uv lock` (ou `uv add`) e commite o `uv.lock` |

## Perguntas de revisão

1. Por que o `Dockerfile` copia `pyproject.toml` e `uv.lock` **antes** de copiar o `src/`?
   O que aconteceria com o tempo de build se copiasse tudo de uma vez?
2. Dentro do Compose, a API se conecta ao Postgres em `postgres:5432`; da sua máquina, você
   usa `localhost:5432`. Por que os dois endereços funcionam, e por que `localhost` **não**
   funcionaria dentro do container da API?
3. `make check` não roda os testes de integração. Onde eles são garantidos, então? E por que
   a fixture do container usa `scope="module"`?
4. Qual a diferença entre o `ruff format`, o `ruff check` e o `mypy`? Dê um exemplo de erro
   que só um deles pegaria.
5. Se alguém colocar `LOG_LEVEL=verbose` no `.env`, o que acontece ao subir a API, e por que
   isso é melhor do que a API subir usando o nível padrão?
