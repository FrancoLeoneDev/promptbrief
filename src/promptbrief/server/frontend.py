from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from promptbrief.server.security import API_PREFIX, TOKEN_HEADER, SecurityConfig

TOKEN_QUERY_PARAM = "token"
INDEX = "index.html"
_SERVED_METHODS = frozenset({"GET", "HEAD"})

# El build vive en el repo y no adentro del paquete: `npm run build` lo escribe en
# `web/dist/` y nadie lo copia. Instalado como wheel esta ruta no existe, y ahí `/`
# contesta la página de "falta compilar" en vez de un 500 — el mismo camino que cuando
# alguien clona el repo y todavía no corrió el build.
DEFAULT_WEB_DIST = (
    Path(__file__).resolve().parents[3] / "web" / "dist" / "promptbrief-web" / "browser"
)

_PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PromptBrief</title>
<style>
  body {{
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: #14161c; color: #e7e9ef; padding: 2rem;
    font: 15px/1.6 ui-sans-serif, system-ui, "Segoe UI", sans-serif;
  }}
  main {{ max-width: 34rem; }}
  h1 {{ font-size: 1.1rem; letter-spacing: .01em; margin: 0 0 .75rem; }}
  p {{ color: #9aa3b4; margin: 0 0 1rem; }}
  code {{
    display: block; padding: .75rem 1rem; border-radius: .4rem;
    background: #1d2029; border: 1px solid #2a2f3b; color: #cbd2e0;
    font: 13px/1.7 ui-monospace, "Cascadia Mono", Consolas, monospace; white-space: pre;
  }}
</style>
</head>
<body><main><h1>{title}</h1><p>{body}</p>{extra}</main></body>
</html>
"""

_MISSING_TOKEN = _PAGE.format(
    title="Falta el token de la sesión",
    body=(
        "Cada arranque de <code style='display:inline;padding:.1rem .3rem'>pbrief serve"
        "</code> genera un token nuevo y lo imprime dentro de una URL. Abrí esa URL: el "
        "front se lo saca de encima apenas carga, así que recargar esta página no alcanza."
    ),
    extra="",
)

_NOT_BUILT = _PAGE.format(
    title="El front todavía no está compilado",
    body="La API ya está andando. Falta generar los estáticos que sirve este servidor:",
    extra="<code>cd web\nnpm install\nnpm run build</code>",
)


def _is_api(path: str) -> bool:
    """True si la ruta le pertenece a la API. `/apium` no le pertenece."""
    return path == API_PREFIX or path.startswith(f"{API_PREFIX}/")


def asset_in(web_dist: Path, url_path: str) -> Path | None:
    """El archivo del build que corresponde a `url_path`, si es que hay uno.

    `index.html` queda afuera a propósito: es el documento, y el documento pide token.
    Sin esta línea, pedirlo por su nombre sería la puerta de al lado, sin guarda.

    Se rechaza cualquier forma que no sea una ruta relativa de URL **antes** de tocar el
    sistema de archivos: una `\\\\host\\share` colada por la URL dispara la resolución
    DNS y el intento de conexión SMB dentro de `resolve()`, o sea una fuga del hash NTLM
    de la máquina hacia el host que eligió el atacante. Es la misma razón por la que
    `checked_root` mira el string antes de resolverlo.
    """
    if not url_path or url_path == INDEX or url_path.startswith("/") or "\\" in url_path:
        return None
    try:
        candidate = (web_dist / url_path).resolve()
    except (OSError, ValueError):
        # Un nombre que el sistema de archivos rechaza —un NUL, por ejemplo— no es un
        # asset: es un 404, no un 500.
        return None
    if not candidate.is_relative_to(web_dist.resolve()) or not candidate.is_file():
        return None
    return candidate


class FrontendFallback:
    """Sirve el front compilado para todo lo que no cuelga de `/api`.

    Es middleware y no una ruta `/{path:path}` porque una ruta atrapa por patrón: se
    quedaría también con cualquier `/api/...` que no exista y con las que se registren
    después, y ahí un error del servidor saldría como la home del front. Como middleware
    el corte es explícito —`/api` sigue de largo hacia el app— y no depende del orden en
    que se hayan declarado las rutas.

    Los assets se sirven **sin** token. No es un olvido: son los bundles del build, no
    tienen autoridad sobre nada, y el navegador no puede colgarle un query param a los
    `<script>` que el propio documento emite. El token se exige donde sí decide algo: en
    el documento, y en cada llamada a la API por header.
    """

    def __init__(self, app: ASGIApp, config: SecurityConfig, web_dist: Path) -> None:
        self.app = app
        self.config = config
        self.web_dist = web_dist

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in _SERVED_METHODS
            or _is_api(scope.get("path", ""))
        ):
            await self.app(scope, receive, send)
            return

        await self._respond(Request(scope))(scope, receive, send)

    def _respond(self, request: Request) -> Response:
        asset = asset_in(self.web_dist, request.url.path.lstrip("/"))
        if asset is not None:
            return FileResponse(asset)

        if not self._authorized(request):
            return HTMLResponse(_MISSING_TOKEN, status_code=401)

        index = self.web_dist / INDEX
        if not index.is_file():
            # Un 503 y no un 500: el servidor está sano, lo que falta es un paso del
            # build, y la página dice cuál.
            return HTMLResponse(_NOT_BUILT, status_code=503)

        # `no-store` para que el documento no quede cacheado: es lo que arranca la
        # sesión, y una copia servida del disco del navegador se saltea esta guarda.
        return FileResponse(index, headers={"Cache-Control": "no-store"})

    def _authorized(self, request: Request) -> bool:
        """El token del documento, por header o por query param.

        El query param existe únicamente acá: es la única forma de que el navegador
        traiga el token en la primera carga. La API no lo acepta, y por eso el front lo
        primero que hace es borrarlo de la URL con `history.replaceState`.
        """
        return self.config.token_matches(
            request.headers.get(TOKEN_HEADER)
        ) or self.config.token_matches(request.query_params.get(TOKEN_QUERY_PARAM))


def install_frontend(app: FastAPI, config: SecurityConfig, web_dist: Path) -> None:
    """Monta el front sobre `app`. Va **antes** de `install_security`.

    El orden importa: `add_middleware` deja afuera al último que se agrega, así que
    llamar a esta función primero deja la guarda de token, Host y origen por fuera del
    front. El documento tiene que estar tan protegido del rebinding como la API.
    """
    app.add_middleware(FrontendFallback, config=config, web_dist=web_dist)
