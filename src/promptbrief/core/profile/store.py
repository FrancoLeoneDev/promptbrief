from __future__ import annotations

import os
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import yaml

from promptbrief.core.errors import InvalidProfileName, ProfileCorrupt, ProfileNotFound
from promptbrief.core.models import Profile
from promptbrief.core.profile.serialize import profile_from_dict, profile_to_dict

_T = TypeVar("_T")

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
    tmp_path.write_text(text, encoding="utf-8")
    _retry_on_permission_error(lambda: os.replace(tmp_path, path))
    return path


def _retry_on_permission_error(action: Callable[[], _T]) -> _T:
    """Reintenta `action` ante un `PermissionError` transitorio en Windows.

    `os.replace()` es atómico, pero en Windows un hilo que tiene el destino abierto
    para lectura puede hacer que el rename (o, simétricamente, la próxima apertura del
    lector) devuelva momentáneamente "acceso denegado" mientras el sistema de archivos
    resuelve la carrera — dura microsegundos, no es corrupción. Reintentar con backoff
    corto absorbe esa carrera de compartición sin tocar la atomicidad real de
    `os.replace`, que sigue garantizando que ningún lector ve un archivo truncado.
    """
    deadline = time.monotonic() + 2.0
    delay = 0.001
    while True:
        try:
            return action()
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.05)


def load_profile(name: str, directory: Path | None = None) -> Profile:
    """Carga un perfil del disco.

    El YAML se edita a mano por diseño, así que cualquier deformidad se traduce a
    ProfileCorrupt en vez de dejar escapar un KeyError o un ValueError crudo.
    """
    path = _profile_path(name, directory or profiles_dir())
    if not path.is_file():
        raise ProfileNotFound(f"No existe el perfil '{name}' en {path.parent}")

    try:
        text = _retry_on_permission_error(lambda: path.read_text(encoding="utf-8"))
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ProfileCorrupt(f"El perfil '{name}' no es YAML válido: {error}") from error

    if not isinstance(data, dict):
        raise ProfileCorrupt(f"El perfil '{name}' no tiene un mapeo en la raíz.")

    return profile_from_dict(data, label=f"el perfil '{name}'")


def list_profiles(directory: Path | None = None) -> list[str]:
    """Nombres de los perfiles guardados, ordenados alfabéticamente."""
    target = directory or profiles_dir()
    if not target.is_dir():
        return []
    return sorted(path.stem for path in target.glob("*.yml"))
