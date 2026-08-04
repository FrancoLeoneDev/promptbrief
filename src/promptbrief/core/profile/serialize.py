from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from promptbrief.core.errors import ProfileCorrupt
from promptbrief.core.models import Profile, Provenance, Slot, SlotKind, SourceFile, TaskType


def _text(value: Any, field: str, label: str) -> str:
    """Exige que `value` sea un string, o levanta ProfileCorrupt nombrando el campo.

    Sin esto, un `{"path": 5}` pasa el chequeo de "es un dict" y se persiste tal cual;
    recién revienta con un TypeError sin capturar la próxima vez que alguien haga
    `root / path`, fuera de cualquier try — un 500 en cada lectura posterior.
    """
    if not isinstance(value, str):
        raise ProfileCorrupt(f"En {label}, '{field}' debe ser texto, no {value!r}.")
    return value


def _integer(value: Any, field: str, label: str) -> int:
    """Exige que `value` sea un int (no un bool), o levanta ProfileCorrupt.

    Misma clase de bug que `_text`: un `{"line": "doce"}` pasaba sin control y recién
    explotaba lejos de acá, el día que alguien hiciera aritmética con `Provenance.line`.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProfileCorrupt(f"En {label}, '{field}' debe ser un entero, no {value!r}.")
    return value


def _safe_relative_path(value: Any, field: str, label: str) -> str:
    """Exige un `sources[].path` relativo, sin `..`, en cualquier convención de separador.

    `Path("C:/base") / "C:/Windows/win.ini"` descarta la base entera en Windows, así
    que un path absoluto guardado en el perfil convierte stale_sources en un lector de
    rutas arbitrarias. Se chequean las dos convenciones de separador (Windows y POSIX)
    porque `PureWindowsPath.is_absolute()` no detecta `/etc/passwd` como absoluto, y a
    la inversa `PurePosixPath` no trata `\\` como separador.

    `is_absolute()` por sí solo no alcanza: en Windows, `\\Windows\\win.ini` tiene raíz
    pero no unidad, así que `PureWindowsPath(...).is_absolute()` da False — es "rooted"
    pero relativo a la unidad actual, y sigue pudiendo escapar la base. `C:foo` tiene
    unidad pero no raíz (relativo a la unidad actual): no escapa la base, pero tampoco
    hay motivo para aceptarlo. Por eso se chequean `.root` y `.drive` además de
    `is_absolute()`.
    """
    text = _text(value, field, label)
    windows_path = PureWindowsPath(text)
    posix_path = PurePosixPath(text)
    if (
        windows_path.is_absolute()
        or posix_path.is_absolute()
        or windows_path.root
        or windows_path.drive
        or ".." in windows_path.parts
        or ".." in posix_path.parts
    ):
        raise ProfileCorrupt(
            f"En {label}, '{field}' no puede ser absoluto ni contener '..': {text!r}."
        )
    return text


def slot_to_dict(slot: Slot) -> dict[str, Any]:
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


def slot_from_dict(data: Any, *, label: str = "el perfil") -> Slot:
    """Reconstruye un Slot desde un dict "crudo".

    Valida que `data` sea un mapeo por sí misma, no solo cuando la llama
    `profile_from_dict`: es pública, y la API HTTP que la va a usar directamente le
    puede pasar cualquier cosa que haya llegado en un body JSON.
    """
    if not isinstance(data, dict):
        raise ProfileCorrupt(
            f"En {label}, el slot no es un mapeo, sino {type(data).__name__}."
        )
    source = data.get("source")
    if source is not None and not isinstance(source, dict):
        raise ProfileCorrupt(f"En {label}, 'source' debe ser un mapeo, no {source!r}.")
    try:
        return Slot(
            id=_text(data["id"], "id", label),
            kind=SlotKind(data.get("kind", SlotKind.UNCLASSIFIED.value)),
            content=_text(data["content"], "content", label),
            applies_to=tuple(TaskType(task) for task in data.get("applies_to", [])),
            source=(
                Provenance(
                    file=_text(source["file"], "source.file", label),
                    line=_integer(source["line"], "source.line", label),
                )
                if source
                else None
            ),
            needs_review=data.get("needs_review", False),
            redacted=data.get("redacted", False),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ProfileCorrupt(f"En {label}, el slot tiene un campo inválido: {error}") from error


def profile_to_dict(profile: Profile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "root": profile.root,
        "budget_tokens": profile.budget_tokens,
        "sources": [{"path": s.path, "sha256": s.sha256} for s in profile.sources],
        "slots": [slot_to_dict(slot) for slot in profile.slots],
    }


def profile_from_dict(data: Any, *, label: str = "el perfil") -> Profile:
    """Reconstruye un Profile desde un dict "crudo" (por ejemplo, un YAML recién leído).

    `label` deja que el llamador (típicamente `load_profile`) conserve el nombre del
    perfil en el mensaje de error, en vez de perderlo detrás de un genérico "el perfil".

    Valida que `data` sea un mapeo por sí misma: es pública, y la API HTTP que la va a
    usar directamente sobre un body JSON le puede pasar una lista, un string o `None`
    (por ejemplo un `[1, 2]` como body) — sin este guard eso revienta con un
    AttributeError crudo en el primer `.get()`, un 500 en vez de un 4xx.
    """
    if not isinstance(data, dict):
        raise ProfileCorrupt(
            f"En {label}, el contenido no es un mapeo, sino {type(data).__name__}."
        )

    raw_slots = data.get("slots", [])
    raw_sources = data.get("sources", [])
    if not isinstance(raw_slots, list) or not isinstance(raw_sources, list):
        raise ProfileCorrupt(f"En {label}, 'slots' y 'sources' deben ser listas.")

    # Cada elemento tiene que ser un mapeo antes de indexarlo: sin esto, un slot que
    # es solo un string ("- solo_una_cadena") pasa el chequeo de lista de arriba y
    # después slot_from_dict revienta con un AttributeError sin capturar.
    for index, item in enumerate(raw_slots):
        if not isinstance(item, dict):
            raise ProfileCorrupt(f"En {label}, el slot en la posición {index} no es un mapeo.")
    for index, item in enumerate(raw_sources):
        if not isinstance(item, dict):
            raise ProfileCorrupt(f"En {label}, el source en la posición {index} no es un mapeo.")

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
            f"En {label}, 'budget_tokens' debe ser un entero positivo, no {budget_tokens!r}."
        )

    # AttributeError deliberadamente no está en este tuple: los guards de arriba ya
    # garantizan que todo elemento de slots/sources es un dict antes de llegar acá, así
    # que ningún YAML malformado puede producir un AttributeError dentro del try. Si uno
    # aparece, es un typo de programador (p. ej. data.content en vez de data["content"])
    # y tiene que reventar como 500, no disfrazarse de error de input del usuario.
    try:
        return Profile(
            name=_text(data["name"], "name", label),
            root=_text(data["root"], "root", label),
            slots=tuple(slot_from_dict(slot, label=label) for slot in raw_slots),
            sources=tuple(
                SourceFile(
                    path=_safe_relative_path(s["path"], "sources[].path", label),
                    sha256=_text(s["sha256"], "sources[].sha256", label),
                )
                for s in raw_sources
            ),
            budget_tokens=budget_tokens,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ProfileCorrupt(f"En {label}, hay un campo inválido: {error}") from error
