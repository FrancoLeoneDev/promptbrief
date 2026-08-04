from __future__ import annotations

from pathlib import Path

from promptbrief.core.errors import NoKnownSources, ProfileAlreadyExists, RootNotFound
from promptbrief.core.models import Profile
from promptbrief.core.profile.distill import distill_project
from promptbrief.core.profile.store import (
    list_profiles,
    save_profile,
    validate_profile_name,
)


def scan_project(
    root: Path,
    name: str | None = None,
    force: bool = False,
) -> tuple[Profile, Path]:
    """Destila un directorio y guarda el perfil. Devuelve (perfil, ruta escrita).

    La política vive acá y no en la CLI porque el servidor la necesita igual: en la
    capa de presentación se duplicaría con reglas apenas distintas.

    El nombre se valida antes de destilar: leer y hashear todos los .md del repo para
    después rechazar por el nombre de la carpeta es trabajo tirado, y en el servidor
    es I/O completo antes de un 400.
    """
    if not root.is_dir():
        raise RootNotFound(f"No existe el directorio {root}")

    validate_profile_name(name if name is not None else root.name)

    profile = distill_project(root, name=name)
    if not profile.sources:
        raise NoKnownSources(
            f"No encontré CLAUDE.md, AGENTS.md, README.md ni package.json en {root}"
        )
    if profile.name in list_profiles() and not force:
        raise ProfileAlreadyExists(f"Ya existe el perfil '{profile.name}'.")

    return profile, save_profile(profile)
