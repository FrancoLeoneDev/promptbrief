from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from promptbrief.core.build import build_brief, lint, resolve_profile
from promptbrief.core.classify import classify
from promptbrief.core.errors import (
    ProfileCorrupt,
    ProfileNotFound,
    PromptBriefError,
    RootNotFound,
    StoredProfileCorrupt,
)
from promptbrief.core.models import BriefRequest, Profile
from promptbrief.core.profile.diff import diff_profiles
from promptbrief.core.profile.distill import distill_project
from promptbrief.core.profile.scan import scan_project
from promptbrief.core.profile.store import (
    delete_profile,
    list_profiles,
    save_profile,
    validate_profile_name,
)
from promptbrief.server.errors import to_http_exception
from promptbrief.server.paths import checked_root
from promptbrief.server.schemas import (
    BriefOut,
    BriefRequestBody,
    DiffOut,
    LintOut,
    ProfileIn,
    ProfileOut,
    ProfileSummary,
    ScanBody,
)
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

    @app.post("/api/profiles/{name}/sync")
    def sync(name: str) -> DiffOut:
        """Compara el perfil guardado contra una destilación fresca del proyecto.

        **No escribe nada:** es un preview. Para aplicar los cambios el front vuelve a
        llamar a `POST /api/profiles/scan` con `force=true`. Separar mirar de aplicar
        es lo que permite mostrar el diff y que el usuario decida, en vez de pisarle
        las ediciones manuales del YAML por el solo hecho de haber abierto la pantalla.

        El `root` del perfil pasa por la allowlist aunque venga del disco del servidor:
        un YAML editado a mano —o guardado cuando la allowlist era otra— puede apuntar
        a cualquier lado, y destilarlo devolvería por HTTP el contenido de ese
        directorio.
        """
        profile = _stored_profile(name)
        root = checked_root(profile.root, app.state.allowed_roots)
        if not root.is_dir():
            raise RootNotFound(f"No existe el directorio {root}")
        return DiffOut.of(diff_profiles(profile, distill_project(root, name=profile.name)))

    @app.get("/api/profiles/{name}")
    def get_one(name: str) -> ProfileOut:
        """El perfil completo, en el mismo shape que acepta `POST /api/profiles`."""
        return ProfileOut.of(_stored_profile(name))

    @app.delete("/api/profiles/{name}", status_code=204)
    def remove(name: str) -> Response:
        """Borra el perfil. No toca el proyecto en disco, solo el YAML destilado."""
        delete_profile(name)
        return Response(status_code=204)

    def prepared(body: BriefRequestBody) -> tuple[BriefRequest, Path | None]:
        """El pedido del core y la raíz ya autorizada, cuando el pedido trae perfil.

        La raíz sale por separado para pasársela **explícita** a `build_brief` y a
        `lint`: si no se la pasan, el core sigue el `root` del perfil por su cuenta y
        `stale_sources` hashea lo que haya ahí. Eso convierte cualquiera de los dos
        endpoints en un oráculo de existencia de archivos y en un hasheador sin tope de
        tamaño, sobre cualquier ruta del disco.

        Un perfil en el body gana sobre `profile_name` —es la pantalla de edición
        mandando cambios sin guardar—, y los dos pasan por la misma guarda: uno que
        llegó por HTTP no es más confiable que uno que salió del disco.
        """
        profile: Profile | None = None
        if body.profile is not None:
            profile = body.profile.to_profile()
        elif body.profile_name:
            profile = _stored_profile(body.profile_name)

        root = None if profile is None else checked_root(profile.root, app.state.allowed_roots)
        task_type = body.task_type or classify(body.text)
        return body.to_request(task_type=task_type, profile=profile), root

    @app.post("/api/brief")
    def brief(body: BriefRequestBody) -> BriefOut:
        """Arma el brief y devuelve, además del texto, la selección y los hallazgos."""
        request, root = prepared(body)
        return BriefOut.of(build_brief(request, root), request.task_type)

    @app.post("/api/lint")
    def lint_only(body: BriefRequestBody) -> LintOut:
        """Los mismos hallazgos que `/api/brief`, sin renderizar el brief.

        Es lo que consume el interrogatorio del front: cada hallazgo trae el
        `slot_name` del campo que le falta, así el formulario se arma sin hardcodear
        ninguna regla.
        """
        request, root = prepared(body)
        return LintOut.of(lint(request, root), request.task_type)

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
