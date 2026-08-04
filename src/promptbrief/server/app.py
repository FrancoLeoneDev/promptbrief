from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from promptbrief.core.build import resolve_profile
from promptbrief.core.errors import (
    ProfileCorrupt,
    ProfileNotFound,
    PromptBriefError,
    StoredProfileCorrupt,
)
from promptbrief.core.models import Profile
from promptbrief.core.profile.scan import scan_project
from promptbrief.core.profile.store import (
    delete_profile,
    list_profiles,
    save_profile,
    validate_profile_name,
)
from promptbrief.server.errors import to_http_exception
from promptbrief.server.paths import checked_root
from promptbrief.server.schemas import ProfileIn, ProfileOut, ProfileSummary, ScanBody
from promptbrief.server.security import SecurityConfig, install_security


def _stored_profile(name: str) -> Profile:
    """Carga un perfil del disco, marcando la corrupción como falla del servidor.

    `load_profile` levanta `ProfileCorrupt`, que el mapeo traduce a 400. Para un YAML
    que está en el disco del servidor eso mentiría: el cliente no lo mandó y no lo
    arregla reenviando otra cosa. `StoredProfileCorrupt` es la misma jerarquía marcada
    como "no es culpa del pedido" y termina en el 500 que corresponde.
    """
    try:
        return resolve_profile(name)
    except ProfileCorrupt as error:
        raise StoredProfileCorrupt(str(error)) from error


def create_app(config: SecurityConfig, allowed_roots: Sequence[Path]) -> FastAPI:
    """Arma la app local: allowlist en el estado, seguridad montada y las rutas.

    `allowed_roots` vive en `app.state` y no en un global porque el test la cambia por
    request y el día que haya dos apps en el mismo proceso un global las mezclaría.
    """
    app = FastAPI(title="PromptBrief", version="0.1.0")
    app.state.allowed_roots = allowed_roots

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/profiles")
    def list_all() -> list[ProfileSummary]:
        """Resumen de cada perfil guardado.

        Devuelve los contadores y no solo los nombres para que la pantalla de lista no
        haga una llamada por perfil para dibujar una tabla. El costo es que hay que
        abrir cada YAML: uno podrido hace caer la lista entera con un 500, que es la
        respuesta honesta — es integridad de datos del servidor, no del pedido.
        """
        return [ProfileSummary.of(_stored_profile(name)) for name in list_profiles()]

    @app.post("/api/profiles/scan")
    def scan(body: ScanBody) -> ProfileOut:
        """Destila un directorio permitido y guarda el perfil.

        Es el único camino que crea un perfil: `POST /api/profiles` solo edita uno que
        ya existe.
        """
        root = checked_root(body.root, app.state.allowed_roots)
        profile, _ = scan_project(root, name=body.name, force=body.force)
        return ProfileOut.of(profile)

    @app.post("/api/profiles")
    def save(body: ProfileIn) -> ProfileOut:
        """Guarda las ediciones de un perfil que ya existe.

        Exige que exista a propósito: crear va por `scan`, que pide `force` para pisar.
        Si acá se pudiera crear pisando, la ruta sin confirmación sería la más
        destructiva de las dos, justo al revés de lo que el cliente espera.

        El `root` pasa por la allowlist igual que en `scan` y **antes** de escribir:
        sin eso el cliente guarda un perfil con `root: "C:/"` y lo cobra después por
        `/api/brief`, que sobre ese root lee y hashea lo que haya.
        """
        validate_profile_name(body.name)
        checked_root(body.root, app.state.allowed_roots)
        # `to_profile` valida el contenido entero (slots, sources, budget) antes de
        # que exista cualquier chance de escribirlo.
        profile = body.to_profile()
        if profile.name not in list_profiles():
            raise ProfileNotFound(
                f"No existe el perfil '{profile.name}'. Creálo con un scan del proyecto."
            )
        save_profile(profile)
        return ProfileOut.of(profile)

    @app.get("/api/profiles/{name}")
    def get_one(name: str) -> ProfileOut:
        """El perfil completo, en el mismo shape que acepta `POST /api/profiles`."""
        return ProfileOut.of(_stored_profile(name))

    @app.delete("/api/profiles/{name}", status_code=204)
    def remove(name: str) -> Response:
        """Borra el perfil. No toca el proyecto en disco, solo el YAML destilado."""
        delete_profile(name)
        return Response(status_code=204)

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
