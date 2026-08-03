from __future__ import annotations

import hashlib
from pathlib import Path

from promptbrief.core.models import Profile

SOURCE_PRIORITY: tuple[str, ...] = ("CLAUDE.md", "AGENTS.md", "README.md", "package.json")
MAX_SOURCE_BYTES = 1_000_000


def discover_sources(root: Path) -> list[Path]:
    """Fuentes conocidas presentes en `root`, en orden de prioridad.

    Los symlinks se ignoran a propósito: un CLAUDE.md que apunta a ~/.ssh/id_rsa
    se leería y se destilaría igual.
    """
    return [
        root / name
        for name in SOURCE_PRIORITY
        if (root / name).is_file() and not (root / name).is_symlink()
    ]


def read_source(path: Path) -> str | None:
    """Lee una fuente acotada. Devuelve None si excede el límite o no decodifica.

    Lee en una sola operación con tope en vez de consultar el tamaño y después leer:
    entre las dos llamadas el archivo puede cambiar, y el chequeo no protegería nada.
    Devolver None en lugar de propagar la excepción también es deliberado: un archivo
    ilegible no puede abortar el scan de todo el proyecto.
    """
    with path.open("rb") as handle:
        data = handle.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        return None
    try:
        # utf-8-sig descarta el BOM que dejan Notepad y otras herramientas de Windows.
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stale_sources(profile: Profile, root: Path) -> list[str]:
    """Fuentes cuyo contenido cambió (o que desaparecieron) desde la destilación."""
    changed: list[str] = []
    for source in profile.sources:
        path = root / source.path
        if not path.is_file() or hash_file(path) != source.sha256:
            changed.append(source.path)
    return changed
