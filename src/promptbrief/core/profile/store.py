from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path

import yaml

from promptbrief.core.errors import InvalidProfileName, ProfileCorrupt, ProfileNotFound
from promptbrief.core.models import Profile
from promptbrief.core.profile.serialize import profile_from_dict, profile_to_dict

# fullmatch, no match: con `$` el motor acepta un \n final y dejaría pasar "perfil\n".
_SAFE_NAME = re.compile(r"[A-Za-z0-9._-]{1,64}")
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def profiles_dir() -> Path:
    """~/.config/promptbrief/projects, o PROMPTBRIEF_HOME/projects si está definido."""
    override = os.environ.get("PROMPTBRIEF_HOME")
    base = Path(override) if override else Path.home() / ".config" / "promptbrief"
    return base / "projects"


def validate_profile_name(name: str) -> None:
    """Levanta InvalidProfileName si el nombre no sirve como nombre de archivo seguro."""
    if not _SAFE_NAME.fullmatch(name) or name.upper() in _WINDOWS_RESERVED:
        raise InvalidProfileName(
            f"Nombre de perfil inválido: {name!r}. "
            "Se permiten letras, números, punto, guion y guion bajo (hasta 64)."
        )


def _profile_path(name: str, directory: Path) -> Path:
    """Ruta del perfil, validando que el nombre no escape del directorio.

    Sin esto, un nombre con `..` escapa; y en Windows un nombre absoluto como
    `C:\\evil` hace que `directory / name` descarte `directory` por completo.
    """
    validate_profile_name(name)
    path = (directory / f"{name}.yml").resolve()
    if not path.is_relative_to(directory.resolve()):
        raise InvalidProfileName(f"Nombre de perfil inválido: {name!r}")
    return path


def save_profile(profile: Profile, directory: Path | None = None) -> Path:
    """Persiste el perfil como YAML legible. Devuelve la ruta escrita.

    La escritura pasa por un temporal en el mismo directorio y `os.replace()`, que es
    atómico en NTFS y en POSIX. Los endpoints de FastAPI definidos con `def` corren en
    un threadpool, así que la concurrencia es real: `write_text` a secas trunca y
    después escribe, y dos escrituras simultáneas dejarían un YAML a medio escribir que
    ProfileCorrupt jamás perdonaría.
    """
    target = directory or profiles_dir()
    path = _profile_path(profile.name, target)
    target.mkdir(parents=True, exist_ok=True)
    payload = profile_to_dict(profile)
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(text, encoding="utf-8")
        _retry_replace(tmp_path, path)
    finally:
        # Si `write_text` o `os.replace` fallan definitivamente, el temporal no puede
        # quedar huérfano: `list_profiles` globea solo `*.yml` y nunca lo vería, así
        # que sería basura invisible que crece con cada intento fallido. Una vez que
        # `os.replace` tuvo éxito, `tmp_path` ya no existe y esto es un no-op.
        tmp_path.unlink(missing_ok=True)
    return path


# `os.replace` es atómico incluso bajo esta carrera: nunca deja un lector viendo un
# archivo truncado. El reintento de abajo no arregla eso — arregla que, en Windows,
# la propia llamada al rename puede fallar con "acceso denegado" mientras otro hilo
# tiene el destino abierto para lectura (dura microsegundos). Acotado a Windows: en
# POSIX un PermissionError es un EACCES real (permisos, no una carrera de
# compartición), y reintentarlo solo demora un error genuino.
_MAX_REPLACE_ATTEMPTS = 80
_REPLACE_RETRY_WINDOW = 1.0  # segundos: muy por debajo del tarpit de 2s de un
# threadpool de FastAPI bloqueado por un antivirus.


def _retry_replace(source: Path, destination: Path) -> None:
    if os.name != "nt":
        os.replace(source, destination)
        return

    deadline = time.monotonic() + _REPLACE_RETRY_WINDOW
    delay = 0.001
    attempts = 0
    while True:
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            attempts += 1
            if attempts >= _MAX_REPLACE_ATTEMPTS or time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.02)


def load_profile(name: str, directory: Path | None = None) -> Profile:
    """Carga un perfil del disco.

    El YAML se edita a mano por diseño, así que cualquier deformidad se traduce a
    ProfileCorrupt en vez de dejar escapar un KeyError o un ValueError crudo.
    """
    path = _profile_path(name, directory or profiles_dir())
    if not path.is_file():
        raise ProfileNotFound(f"No existe el perfil '{name}' en {path.parent}")

    try:
        data = yaml.safe_load(_read_profile_text(path))
    except yaml.YAMLError as error:
        raise ProfileCorrupt(f"El perfil '{name}' no es YAML válido: {error}") from error

    return profile_from_dict(data, label=f"el perfil '{name}'")


_MAX_READ_ATTEMPTS = 8
_READ_RETRY_WINDOW = 0.02  # segundos: deliberadamente corta, ver docstring.


def _read_profile_text(path: Path) -> str:
    """Lee el YAML, con un reintento breve ante un `PermissionError` transitorio en Windows.

    Es la otra cara de `_retry_replace`: mientras `os.replace()` resuelve el rename,
    una lectura que llega justo en el medio puede toparse con la misma carrera de
    compartición y fallar con "acceso denegado", una ventana de microsegundos.

    La ventana acá es deliberadamente mucho más corta que la de `_retry_replace`: un
    reintento generoso del lado del lector diluiría la garantía que el test de
    concurrencia viene a proteger. Si `save_profile` dejara de ser atómico (por
    ejemplo, volviera a `write_text` puro), un lector con reintentos largos podría
    terminar esperando a que la escritura no atómica termine y ver siempre una versión
    completa — vieja o nueva —, escondiendo la regresión en vez de detectarla.
    """
    if os.name != "nt":
        return path.read_text(encoding="utf-8")

    deadline = time.monotonic() + _READ_RETRY_WINDOW
    attempts = 0
    while True:
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            attempts += 1
            if attempts >= _MAX_READ_ATTEMPTS or time.monotonic() >= deadline:
                raise
            time.sleep(0.001)


def delete_profile(name: str, directory: Path | None = None) -> None:
    """Borra el perfil. Levanta ProfileNotFound si no estaba.

    Vive acá y no en el llamador porque borrar necesita la misma resolución de nombre
    que guardar y leer: reconstruir la ruta afuera duplicaría `_profile_path` y sería
    la copia que se olvida de validar el nombre.

    Intenta borrar y traduce el fallo en vez de preguntar si existe: entre el chequeo
    y el `unlink` el archivo puede desaparecer, y ahí el chequeo no protege nada.
    """
    path = _profile_path(name, directory or profiles_dir())
    try:
        path.unlink()
    except FileNotFoundError as error:
        raise ProfileNotFound(f"No existe el perfil '{name}' en {path.parent}") from error


def list_profiles(directory: Path | None = None) -> list[str]:
    """Nombres de los perfiles guardados, ordenados alfabéticamente."""
    target = directory or profiles_dir()
    if not target.is_dir():
        return []
    return sorted(path.stem for path in target.glob("*.yml"))
