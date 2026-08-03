from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from promptbrief.core.errors import InvalidProfileName, ProfileCorrupt, ProfileNotFound
from promptbrief.core.models import Profile, Provenance, Slot, SlotKind, SourceFile, TaskType

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


def _profile_path(name: str, directory: Path) -> Path:
    """Ruta del perfil, validando que el nombre no escape del directorio.

    Sin esto, un nombre con `..` escapa; y en Windows un nombre absoluto como
    `C:\\evil` hace que `directory / name` descarte `directory` por completo.
    """
    if not _SAFE_NAME.fullmatch(name) or name.upper() in _WINDOWS_RESERVED:
        raise InvalidProfileName(
            f"Nombre de perfil inválido: {name!r}. "
            "Se permiten letras, números, punto, guion y guion bajo (hasta 64)."
        )
    path = (directory / f"{name}.yml").resolve()
    if not path.is_relative_to(directory.resolve()):
        raise InvalidProfileName(f"Nombre de perfil inválido: {name!r}")
    return path


def _slot_to_dict(slot: Slot) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": slot.id,
        "kind": slot.kind.value,
        "content": slot.content,
        "applies_to": [task.value for task in slot.applies_to],
        "needs_review": slot.needs_review,
        "redacted": slot.redacted,
    }
    if slot.source is not None:
        data["source"] = {"file": slot.source.file, "line": slot.source.line}
    return data


def _slot_from_dict(data: dict[str, Any]) -> Slot:
    source = data.get("source")
    return Slot(
        id=data["id"],
        kind=SlotKind(data.get("kind", SlotKind.UNCLASSIFIED.value)),
        content=data["content"],
        applies_to=tuple(TaskType(task) for task in data.get("applies_to", [])),
        source=Provenance(file=source["file"], line=source["line"]) if source else None,
        needs_review=data.get("needs_review", False),
        redacted=data.get("redacted", False),
    )


def save_profile(profile: Profile, directory: Path | None = None) -> Path:
    """Persiste el perfil como YAML legible. Devuelve la ruta escrita."""
    target = directory or profiles_dir()
    path = _profile_path(profile.name, target)
    target.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": profile.name,
        "root": profile.root,
        "budget_tokens": profile.budget_tokens,
        "sources": [{"path": s.path, "sha256": s.sha256} for s in profile.sources],
        "slots": [_slot_to_dict(slot) for slot in profile.slots],
    }
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return path


def load_profile(name: str, directory: Path | None = None) -> Profile:
    """Carga un perfil del disco.

    El YAML se edita a mano por diseño, así que cualquier deformidad se traduce a
    ProfileCorrupt en vez de dejar escapar un KeyError o un ValueError crudo.
    """
    path = _profile_path(name, directory or profiles_dir())
    if not path.is_file():
        raise ProfileNotFound(f"No existe el perfil '{name}' en {path.parent}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ProfileCorrupt(f"El perfil '{name}' no es YAML válido: {error}") from error

    if not isinstance(data, dict):
        raise ProfileCorrupt(f"El perfil '{name}' no tiene un mapeo en la raíz.")

    raw_slots = data.get("slots", [])
    raw_sources = data.get("sources", [])
    if not isinstance(raw_slots, list) or not isinstance(raw_sources, list):
        raise ProfileCorrupt(f"En el perfil '{name}', 'slots' y 'sources' deben ser listas.")

    # Cada elemento tiene que ser un mapeo antes de indexarlo: sin esto, un slot que
    # es solo un string ("- solo_una_cadena") pasa el chequeo de lista de arriba y
    # después _slot_from_dict revienta con un AttributeError sin capturar.
    for index, item in enumerate(raw_slots):
        if not isinstance(item, dict):
            raise ProfileCorrupt(
                f"En el perfil '{name}', el slot en la posición {index} no es un mapeo."
            )
    for index, item in enumerate(raw_sources):
        if not isinstance(item, dict):
            raise ProfileCorrupt(
                f"En el perfil '{name}', el source en la posición {index} no es un mapeo."
            )

    budget_tokens = data.get("budget_tokens", 1500)
    # `Profile` es un dataclass sin validación en runtime: sin este chequeo, un
    # budget_tokens deforme entra tal cual y recién explota lejos de acá, el día que
    # alguien haga aritmética con el campo.
    if (
        not isinstance(budget_tokens, int)
        or isinstance(budget_tokens, bool)
        or budget_tokens <= 0
    ):
        raise ProfileCorrupt(
            f"En el perfil '{name}', 'budget_tokens' debe ser un entero positivo, "
            f"no {budget_tokens!r}."
        )

    # AttributeError deliberadamente no está en este tuple: los guards de arriba ya
    # garantizan que todo elemento de slots/sources es un dict antes de llegar acá, así
    # que ningún YAML malformado puede producir un AttributeError dentro del try. Si uno
    # aparece, es un typo de programador (p. ej. data.content en vez de data["content"])
    # y tiene que reventar como 500, no disfrazarse de error de input del usuario.
    try:
        return Profile(
            name=data["name"],
            root=data["root"],
            slots=tuple(_slot_from_dict(slot) for slot in raw_slots),
            sources=tuple(SourceFile(path=s["path"], sha256=s["sha256"]) for s in raw_sources),
            budget_tokens=budget_tokens,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ProfileCorrupt(f"El perfil '{name}' tiene un campo inválido: {error}") from error


def list_profiles(directory: Path | None = None) -> list[str]:
    """Nombres de los perfiles guardados, ordenados alfabéticamente."""
    target = directory or profiles_dir()
    if not target.is_dir():
        return []
    return sorted(path.stem for path in target.glob("*.yml"))
