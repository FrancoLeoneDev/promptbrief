from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Family(StrEnum):
    """Familia de la regla, según el §6 del spec."""

    TEXT = "text"
    COMPLETENESS = "completeness"
    CONTEXT = "context"


class TaskType(StrEnum):
    CODE_CHANGE = "code_change"
    DEBUG = "debug"
    WRITING = "writing"


class SlotKind(StrEnum):
    """Qué clase de dato es un slot. Decide su tag y su sección al renderizar."""

    STACK = "stack"
    CONVENTION = "convention"
    CONSTRAINT = "constraint"
    GLOSSARY = "glossary"
    ARCHITECTURE = "architecture"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class Provenance:
    file: str
    line: int

    def label(self) -> str:
        """Etiqueta legible para mensajes de usuario: 'CLAUDE.md:12'."""
        return f"{self.file}:{self.line}"


@dataclass(frozen=True)
class Slot:
    """Un dato del proyecto, listo para inyectar (o descartar).

    `applies_to` vacío significa "aplica a todos los tipos de tarea", no "a ninguno"
    — la misma convención que usa `Rule.applies_to`.
    """

    id: str
    kind: SlotKind
    content: str
    applies_to: tuple[TaskType, ...]
    source: Provenance | None
    needs_review: bool = False
    redacted: bool = False

    def label(self) -> str:
        """Cómo nombrar este slot ante el usuario: la procedencia si la hay, si no el id."""
        return self.source.label() if self.source else self.id


@dataclass(frozen=True)
class SourceFile:
    path: str
    sha256: str


@dataclass(frozen=True)
class Profile:
    name: str
    root: str
    slots: tuple[Slot, ...]
    sources: tuple[SourceFile, ...]
    budget_tokens: int = 1500


@dataclass(frozen=True)
class BriefRequest:
    text: str
    task_type: TaskType
    profile: Profile | None = None
    success_criteria: str | None = None
    output_format: str | None = None
    file_scope: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    repro_steps: str | None = None
    expected_vs_actual: str | None = None


@dataclass(frozen=True)
class Selection:
    """Resultado de recortar el perfil al presupuesto.

    Los motivos de exclusión se reportan por separado a propósito: solo `over_budget`
    es un problema. `not_applicable` es el filtrado normal por tipo de tarea y
    `skipped_for_review` es lo que la destilación no pudo clasificar.
    """

    selected: tuple[Slot, ...] = ()
    over_budget: tuple[Slot, ...] = ()
    not_applicable: tuple[Slot, ...] = ()
    skipped_for_review: tuple[Slot, ...] = ()

    def all_slots(self) -> tuple[Slot, ...]:
        return (*self.selected, *self.over_budget, *self.not_applicable, *self.skipped_for_review)


@dataclass(frozen=True)
class CheckContext:
    request: BriefRequest
    selection: Selection = Selection()
    stale_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    rule_id: str
    family: Family
    severity: Severity
    message: str
    suggestion: str
    slot_name: str | None = None


@dataclass(frozen=True)
class Brief:
    text: str
    findings: tuple[Finding, ...] = ()
    dropped_slots: tuple[str, ...] = ()
    selection: Selection = Selection()
