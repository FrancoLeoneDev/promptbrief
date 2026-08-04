from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from promptbrief.core.errors import PromptBriefError
from promptbrief.server.errors import to_http_exception
from promptbrief.server.security import SecurityConfig, install_security


def create_app(config: SecurityConfig, allowed_roots: Sequence[Path]) -> FastAPI:
    """Arma la app local: allowlist en el estado, seguridad montada y /api/health.

    `allowed_roots` vive en `app.state` y no en un global porque el test la cambia por
    request y el día que haya dos apps en el mismo proceso un global las mezclaría.
    """
    app = FastAPI(title="PromptBrief", version="0.1.0")
    app.state.allowed_roots = allowed_roots

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(PromptBriefError)
    async def promptbrief_error(request: Request, error: PromptBriefError) -> JSONResponse:
        """Traduce la jerarquía de errores de input a su 4xx.

        Lo que `to_http_exception` rechaza —`StoredProfileCorrupt`, un YAML podrido en
        el disco del servidor— sale de acá como `TypeError` y termina en un 500, que es
        el destino correcto: el cliente no lo causó y no puede arreglarlo reenviando.
        """
        http_error = to_http_exception(error)
        return JSONResponse({"detail": http_error.detail}, status_code=http_error.status_code)

    install_security(app, config)
    return app
