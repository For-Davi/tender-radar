"""Exporta o schema OpenAPI da API para um arquivo JSON (contrato com o frontend).

Uso:  make openapi   (grava frontend/openapi.json e regenera os tipos TypeScript)

O schema sai direto da app FastAPI (`create_app().openapi()`): não precisa subir a
API nem ter banco no ar, porque criar o engine não abre conexão. O CI roda este
script e falha se o arquivo versionado estiver diferente, ou seja, se alguém mudou a
API sem atualizar os tipos do frontend.
"""

import json
import sys
from pathlib import Path

from radar.api.main import create_app
from radar.config import Settings

DESTINO_PADRAO = Path(__file__).parents[2] / "frontend" / "openapi.json"


def exportar(destino: Path) -> None:
    # log em WARNING: o "app_criada" não interessa aqui
    schema = create_app(Settings(log_level="WARNING")).openapi()
    # indent + newline final: diff legível e estável entre execuções
    destino.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    exportar(Path(sys.argv[1]) if len(sys.argv) > 1 else DESTINO_PADRAO)
