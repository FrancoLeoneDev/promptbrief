from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

TOKEN_HEADER = "X-PromptBrief-Token"
# El `text` de un lint corre las reglas sobre el string completo; sin cota el costo
# crece con el tamaño del body. Medido: ~0,5 s por MB.
MAX_BODY_BYTES = 1_000_000
MIN_TOKEN_LENGTH = 32
_SAFE_FETCH_SITES = frozenset({"same-origin", "same-site", "none"})
_API_PREFIX = "/api"
_TOKEN_HEADER_BYTES = TOKEN_HEADER.lower().encode("ascii")


@dataclass(frozen=True)
class SecurityConfig:
    token: str
    port: int

    def __post_init__(self) -> None:
        if len(self.token) < MIN_TOKEN_LENGTH:
            raise ValueError(f"El token necesita al menos {MIN_TOKEN_LENGTH} caracteres.")

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return frozenset({f"127.0.0.1:{self.port}", f"localhost:{self.port}"})

    @property
    def allowed_origins(self) -> frozenset[str]:
        """Los mismos destinos que `allowed_hosts`, escritos como origen.

        Se deriva de `allowed_hosts` en vez de ser solo `origin`: si `localhost:puerto`
        vale como Host, la página servida desde ahí manda `Origin: http://localhost:...`
        y rechazarla convertiría en 403 cada fetch del front abierto por localhost.
        """
        return frozenset(f"http://{host}" for host in self.allowed_hosts)

    @classmethod
    def generate(cls, port: int) -> SecurityConfig:
        return cls(token=secrets.token_urlsafe(32), port=port)


def _raw_header(scope: Scope, name: bytes) -> bytes | None:
    """El valor crudo de un header, sin decodificar.

    Sin decodificar a propósito: el token se compara en bytes, y decodificar primero
    para volver a codificar después solo agrega una oportunidad de romperse con un
    valor no ASCII.
    """
    for key, value in scope["headers"]:
        if key.lower() == name:
            return value
    return None


def _text_header(scope: Scope, name: bytes) -> str | None:
    raw = _raw_header(scope, name)
    # latin-1 es la codificación de los headers HTTP y nunca falla: cualquier byte
    # tiene un carácter. Un Host o un Origin raro termina en un 403, no en un 500.
    return None if raw is None else raw.decode("latin-1")


class SecurityGuard:
    """Token, Host, Sec-Fetch-Site y Origin, en ese orden.

    Middleware ASGI puro y no BaseHTTPMiddleware: no toca el body ni necesita el ciclo
    de request/response de Starlette, y así no se interpone entre `BodyLimit` y el app.

    El token se exige solo bajo `/api`, que es todo lo que hoy monta el servidor. El
    resto de los chequeos corre para cualquier ruta: el día que se sirva el front
    estático desde acá, la protección contra rebinding tiene que cubrirlo también, y un
    documento cargado por el navegador no puede mandar un header custom.
    """

    def __init__(self, app: ASGIApp, config: SecurityConfig) -> None:
        self.app = app
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rejection = self._rejection(scope)
        if rejection is not None:
            status, detail = rejection
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _rejection(self, scope: Scope) -> tuple[int, str] | None:
        if scope.get("path", "").startswith(_API_PREFIX) and not self._token_matches(scope):
            return 401, "Falta el token o no coincide."

        # El Host es lo único anómalo en una request de DNS rebinding: el atacante
        # resuelve su dominio a 127.0.0.1, así que la request es same-origin, no manda
        # Origin y llega con el Host del atacante.
        host = _text_header(scope, b"host")
        if host is None or host.lower() not in self.config.allowed_hosts:
            return 403, "Host no permitido."

        # Sec-Fetch-Site llega donde Origin no: <img>, <script>, navegación, no-cors.
        fetch_site = _text_header(scope, b"sec-fetch-site")
        if fetch_site is not None and fetch_site.lower() not in _SAFE_FETCH_SITES:
            return 403, "Pedido cross-site."

        origin = _text_header(scope, b"origin")
        if origin is not None and origin not in self.config.allowed_origins:
            return 403, "Origen no permitido."

        return None

    def _token_matches(self, scope: Scope) -> bool:
        """Compara el token del header, en bytes y en tiempo constante.

        En bytes y no en str porque `hmac.compare_digest` sobre strings exige ASCII
        puro: un `ñ` en el header le arranca un TypeError, o sea un 500 que cualquiera
        dispara sin conocer el token.

        La query string ni se mira: ahí el token queda escrito en el access log de
        uvicorn y en el historial del navegador.
        """
        provided = _raw_header(scope, _TOKEN_HEADER_BYTES)
        if provided is None:
            return False
        return hmac.compare_digest(provided, self.config.token.encode("utf-8"))


class BodyLimit:
    """Corta el body en `max_bytes` contando lo que llega.

    Mirar `Content-Length` no alcanza: una request con `Transfer-Encoding: chunked` no
    lo trae y pasaría sin cota — medido, 5 MB por un tope de 1 MB. Middleware ASGI puro
    y no BaseHTTPMiddleware, porque hay que envolver `receive` antes de que nadie lea
    el body.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        seen = 0
        too_big = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal seen, too_big
            message = await receive()
            if message["type"] != "http.request":
                return message
            seen += len(message.get("body", b""))
            if seen > self.max_bytes:
                too_big = True
                # Cortar la lectura acá: seguir consumiendo un cuerpo ya rechazado es
                # justo el recurso que el tope viene a proteger.
                return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            # FastAPI atrapa el ClientDisconnect que ve al parsear el body y lo
            # convierte en un 400 "error parsing the body", que miente sobre el motivo.
            # Esa respuesta se descarta y abajo sale el 413 — solo mientras no haya
            # salido nada al cable todavía.
            if too_big and not response_started:
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except ClientDisconnect:
            # Una ruta que no envuelva la lectura del body deja escapar el disconnect
            # que fabricamos arriba. Es nuestro, no un cliente que se fue.
            if not too_big:
                raise

        if too_big and not response_started:
            await JSONResponse(
                {"detail": f"El cuerpo supera los {self.max_bytes} bytes."}, status_code=413
            )(scope, receive, send)


def install_security(app: FastAPI, config: SecurityConfig) -> None:
    """Monta el tope de body y la guarda de acceso sobre `app`.

    El orden importa: la guarda queda por fuera, así un pedido sin token se corta con
    un 401 antes de que el tope se ponga a contar megabytes ajenos.
    """
    app.add_middleware(BodyLimit)
    app.add_middleware(SecurityGuard, config=config)
