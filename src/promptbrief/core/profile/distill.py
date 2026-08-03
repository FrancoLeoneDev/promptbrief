from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

from promptbrief.core.models import Profile, Provenance, Slot, SlotKind, SourceFile, TaskType
from promptbrief.core.profile.sources import discover_sources, hash_file, read_source
from promptbrief.core.text import redact_secrets, strip_accents

_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*]\s+(.+)$")
_FENCE = re.compile(r"^\s*```")

_DEV_TASKS: tuple[TaskType, ...] = (TaskType.CODE_CHANGE, TaskType.DEBUG)

# Techo por archivo. Sin esto, un markdown de un millón de bullets cortos produce
# un perfil que hay que recorrer entero en cada build_brief — justo el context rot
# que la herramienta existe para evitar.
MAX_SLOTS_PER_SOURCE = 500

# Token del heading (sin tildes, en minúscula) -> (kind, a qué tareas aplica).
_HEADING_KINDS: dict[str, tuple[SlotKind, tuple[TaskType, ...]]] = {
    "convencion": (SlotKind.CONVENTION, _DEV_TASKS),
    "convention": (SlotKind.CONVENTION, _DEV_TASKS),
    "prohibi": (SlotKind.CONSTRAINT, _DEV_TASKS),
    "forbidden": (SlotKind.CONSTRAINT, _DEV_TASKS),
    "restriccion": (SlotKind.CONSTRAINT, _DEV_TASKS),
    "constraint": (SlotKind.CONSTRAINT, _DEV_TASKS),
    "glosario": (SlotKind.GLOSSARY, _DEV_TASKS),
    "glossary": (SlotKind.GLOSSARY, _DEV_TASKS),
    "stack": (SlotKind.STACK, ()),
    "arquitectura": (SlotKind.ARCHITECTURE, _DEV_TASKS),
    "architecture": (SlotKind.ARCHITECTURE, _DEV_TASKS),
}

# Reformulación de negativo a positivo (F3), en el idioma de la fuente.
# Traducir sería inventar: el brief conserva el idioma del repo (ver D2 del spec).
_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"^no\s+(?:modificar|tocar|cambiar)\s+(?P<target>.+)$", re.I),
        "Mantener {target} sin cambios.",
    ),
    (re.compile(r"^no\s+agregar\s+(?P<target>.+)$", re.I), "Resolver sin agregar {target}."),
    (re.compile(r"^no\s+usar\s+(?P<target>.+)$", re.I), "Resolver sin usar {target}."),
    (
        re.compile(r"^(?:do not|don't|never)\s+(?:modify|touch|change)\s+(?P<target>.+)$", re.I),
        "Keep {target} unchanged.",
    ),
    (
        re.compile(r"^(?:do not|don't|never)\s+add\s+(?P<target>.+)$", re.I),
        "Solve it without adding {target}.",
    ),
    (
        re.compile(r"^(?:do not|don't|never)\s+use\s+(?P<target>.+)$", re.I),
        "Solve it without using {target}.",
    ),
)


def _classify_heading(heading: str) -> tuple[SlotKind, tuple[TaskType, ...]] | None:
    """Clasifica un heading por el token que aparece PRIMERO en el texto.

    Recorrer el diccionario y quedarse con el primer token que matchea haría que
    "Convenciones y restricciones" cayera en CONVENTION solo porque esa clave está
    antes en el dict, aunque el heading hable de restricciones.
    """
    key = strip_accents(heading.strip().lower())
    matches = [
        (key.index(token), value) for token, value in _HEADING_KINDS.items() if token in key
    ]
    if not matches:
        return None
    return min(matches, key=lambda match: match[0])[1]


def _to_positive(text: str) -> str:
    """Reescribe una prohibición como instrucción positiva. Devuelve el original si no aplica."""
    stripped = text.strip()
    for pattern, template in _REWRITES:
        match = pattern.match(stripped)
        if match:
            return template.format(target=match.group("target").rstrip("."))
    return stripped


def _slot_id(source_path: str, kind: SlotKind, content: str) -> str:
    """ID estable: no depende de la posición del bullet en el archivo.

    Un contador posicional haría que agregar un bullet arriba renumere todo lo de
    abajo, y cada re-scan reportaría el perfil entero como cambiado.
    """
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    return f"{Path(source_path).stem.lower()}-{kind.value}-{digest}"


def distill_markdown(text: str, path: str) -> list[Slot]:
    """Extrae slots de un markdown.

    El heading da el `kind` por defecto, pero un bullet que se reescribe como
    prohibición se promueve a CONSTRAINT sin importar bajo qué heading esté.
    Lo que no se puede clasificar se marca `needs_review`, y eso implica que no
    se inyecta.
    """
    lines = text.splitlines()

    # Un fence sin cerrar dejaría `in_code_fence` en True hasta EOF: el resto del
    # documento se descartaría en silencio, sin señal para el usuario, que solo
    # vería un perfil más chico. Por eso contamos los fences ANTES de parsear. Un
    # conteo impar significa que algo quedó sin cerrar, y ahí apagamos el tracking
    # de fences entero (nada se pierde) pero marcamos TODOS los slots del archivo
    # `needs_review=True`: perder contenido en silencio es el peor resultado
    # posible, e inyectar el contenido de un posible bloque de código como si
    # fuera un hecho del proyecto es el segundo peor. `needs_review=True` evita
    # los dos — esos slots no se inyectan, pero sí cuentan en `pbrief scan`, así
    # que el usuario ve que algo quedó sin clasificar y va a mirar el archivo.
    unclosed_fence = sum(1 for line in lines if _FENCE.match(line)) % 2 == 1

    slots: list[Slot] = []
    heading_kind = SlotKind.UNCLASSIFIED
    heading_applies: tuple[TaskType, ...] = ()
    in_code_fence = False

    for lineno, line in enumerate(lines, start=1):
        if not unclosed_fence:
            if _FENCE.match(line):
                in_code_fence = not in_code_fence
                continue
            if in_code_fence:
                continue

        heading = _HEADING.match(line)
        if heading:
            resolved = _classify_heading(heading.group(1))
            heading_kind, heading_applies = resolved or (SlotKind.UNCLASSIFIED, ())
            continue

        bullet = _BULLET.match(line)
        if not bullet:
            continue
        if len(slots) >= MAX_SLOTS_PER_SOURCE:
            break

        content = bullet.group(1).strip()
        # Una regla horizontal tipo "* * *" matchea _BULLET (`[-*]\s+` no exige que
        # lo que sigue sea texto) y no aporta ningún hecho del proyecto. "---" no
        # se ve afectado: sin espacio después del primer "-", ni siquiera matchea
        # _BULLET.
        if not content.strip("-*. "):
            continue

        kind, applies = heading_kind, heading_applies

        positive = _to_positive(content)
        if positive != content:
            content, kind, applies = positive, SlotKind.CONSTRAINT, _DEV_TASKS

        content, redacted = redact_secrets(content)
        slots.append(
            Slot(
                id=_slot_id(path, kind, content),
                kind=kind,
                content=content,
                applies_to=applies,
                source=Provenance(file=path, line=lineno),
                needs_review=kind is SlotKind.UNCLASSIFIED,
                redacted=redacted,
            )
        )

    if unclosed_fence:
        slots = [replace(slot, needs_review=True) for slot in slots]
    return slots


def distill_package_json(text: str, path: str) -> list[Slot]:
    """Extrae un slot de stack a partir de las dependencias.

    Devuelve una lista vacía en silencio ante JSON roto, no-objeto o sin
    dependencias: ninguno de esos casos justifica abortar el scan del proyecto.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []

    dependencies = data.get("dependencies")
    if not isinstance(dependencies, dict) or not dependencies:
        return []

    listed = ", ".join(f"{name} {version}" for name, version in sorted(dependencies.items()))
    # Una dependencia privada puede traer un token en la URL: git+https://ghp_xxx@…
    content, redacted = redact_secrets(listed)
    return [
        Slot(
            id=_slot_id(path, SlotKind.STACK, content),
            kind=SlotKind.STACK,
            content=content,
            applies_to=(),
            source=Provenance(file=path, line=1),
            redacted=redacted,
        )
    ]


def distill_project(root: Path, name: str | None = None) -> Profile:
    """Destila todas las fuentes conocidas de `root` en un perfil.

    Una fuente ilegible se registra igual, aunque no aporte slots: si no quedara
    registrada, `stale_sources` nunca avisaría cuando cambie.
    """
    slots: list[Slot] = []
    sources: list[SourceFile] = []
    seen_ids: set[str] = set()

    for path in discover_sources(root):
        sources.append(SourceFile(path=path.name, sha256=hash_file(path)))

        text = read_source(path)
        if text is None:
            continue

        produced = (
            distill_package_json(text, path.name)
            if path.name == "package.json"
            else distill_markdown(text, path.name)
        )
        for slot in produced:
            if slot.id not in seen_ids:
                seen_ids.add(slot.id)
                slots.append(slot)

    return Profile(
        name=name or root.name,
        root=str(root),
        slots=tuple(slots),
        sources=tuple(sources),
    )
