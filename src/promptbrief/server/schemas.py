from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from promptbrief.core.models import (
    Brief,
    BriefRequest,
    Family,
    Finding,
    Profile,
    Provenance,
    Selection,
    Severity,
    Slot,
    SlotKind,
    SourceFile,
    TaskType,
)
from promptbrief.core.profile.diff import ProfileDiff
from promptbrief.core.profile.serialize import profile_from_dict

# Los `of()` traducen del dominio al borde en un solo sentido. El inverso solo existe
# para lo que el cliente manda (ProfileIn, BriefRequestBody): un modelo de salida que
# también supiera reconstruirse invita a usarlo como formato de persistencia, y ahí ya
# son dos esquemas que hay que migrar juntos.


class ScanBody(BaseModel):
    """Pedido de destilar un directorio y guardarlo como perfil."""

    root: str
    name: str | None = None
    force: bool = False


class ProvenanceOut(BaseModel):
    file: str
    line: int

    @classmethod
    def of(cls, provenance: Provenance) -> ProvenanceOut:
        return cls(file=provenance.file, line=provenance.line)


class SlotOut(BaseModel):
    id: str
    kind: SlotKind
    content: str
    applies_to: list[TaskType]
    source: ProvenanceOut | None
    needs_review: bool
    redacted: bool

    @classmethod
    def of(cls, slot: Slot) -> SlotOut:
        return cls(
            id=slot.id,
            kind=slot.kind,
            content=slot.content,
            applies_to=list(slot.applies_to),
            source=None if slot.source is None else ProvenanceOut.of(slot.source),
            needs_review=slot.needs_review,
            redacted=slot.redacted,
        )


class ProfileIn(BaseModel):
    """Un perfil que llega en un body JSON.

    Los slots y las fuentes quedan como mapeos crudos a propósito: `profile_from_dict`
    ya valida cada campo y levanta `ProfileCorrupt`, que el app traduce a un 4xx.
    Redeclarar acá esa validación sería una segunda fuente de verdad que se desincroniza
    con el core en cuanto uno de los dos cambie.
    """

    name: str
    root: str
    budget_tokens: int = 1500
    sources: list[dict[str, Any]] = Field(default_factory=list)
    slots: list[dict[str, Any]] = Field(default_factory=list)

    def to_profile(self) -> Profile:
        """Levanta `ProfileCorrupt` si el contenido no tiene la forma esperada."""
        return profile_from_dict(self.model_dump(), label="el perfil recibido")


class SourceOut(BaseModel):
    path: str
    sha256: str

    @classmethod
    def of(cls, source: SourceFile) -> SourceOut:
        return cls(path=source.path, sha256=source.sha256)


class ProfileOut(BaseModel):
    """El perfil completo tal como sale por HTTP.

    Espeja campo por campo lo que acepta `ProfileIn`: la pantalla de edición trae el
    perfil por GET, lo modifica y lo manda de vuelta sin traducir nada en el medio.
    Sigue siendo de un solo sentido —no sabe reconstruir un `Profile`—, así que el
    inverso pasa igual por `profile_from_dict`, que es donde vive la validación.
    """

    name: str
    root: str
    budget_tokens: int
    sources: list[SourceOut] = Field(default_factory=list)
    slots: list[SlotOut] = Field(default_factory=list)

    @classmethod
    def of(cls, profile: Profile) -> ProfileOut:
        return cls(
            name=profile.name,
            root=profile.root,
            budget_tokens=profile.budget_tokens,
            sources=[SourceOut.of(source) for source in profile.sources],
            slots=[SlotOut.of(slot) for slot in profile.slots],
        )


class ProfileSummary(BaseModel):
    """Lo mínimo para dibujar la lista de perfiles.

    Los contadores viajan resueltos porque son lo único que la pantalla de lista
    muestra además del nombre: devolver solo nombres la obligaría a pedir cada perfil
    por separado para llenar una tabla.
    """

    name: str
    slot_count: int
    source_count: int

    @classmethod
    def of(cls, profile: Profile) -> ProfileSummary:
        return cls(
            name=profile.name,
            slot_count=len(profile.slots),
            source_count=len(profile.sources),
        )


class SelectionOut(BaseModel):
    """El recorte del perfil al presupuesto, con los motivos separados.

    Los cuatro grupos viajan por separado porque solo `over_budget` es un problema que
    el usuario puede querer resolver subiendo el presupuesto; los otros dos son
    filtrado normal y no deberían pintarse como pérdida.
    """

    selected: list[SlotOut] = Field(default_factory=list)
    over_budget: list[SlotOut] = Field(default_factory=list)
    not_applicable: list[SlotOut] = Field(default_factory=list)
    skipped_for_review: list[SlotOut] = Field(default_factory=list)

    @classmethod
    def of(cls, selection: Selection) -> SelectionOut:
        return cls(
            selected=[SlotOut.of(slot) for slot in selection.selected],
            over_budget=[SlotOut.of(slot) for slot in selection.over_budget],
            not_applicable=[SlotOut.of(slot) for slot in selection.not_applicable],
            skipped_for_review=[SlotOut.of(slot) for slot in selection.skipped_for_review],
        )


class SlotChange(BaseModel):
    """Los dos lados de una edición, para que la UI muestre el antes y el después."""

    before: SlotOut
    after: SlotOut


class DiffOut(BaseModel):
    added: list[SlotOut] = Field(default_factory=list)
    removed: list[SlotOut] = Field(default_factory=list)
    modified: list[SlotChange] = Field(default_factory=list)
    unchanged: list[SlotOut] = Field(default_factory=list)

    @classmethod
    def of(cls, diff: ProfileDiff) -> DiffOut:
        return cls(
            added=[SlotOut.of(slot) for slot in diff.added],
            removed=[SlotOut.of(slot) for slot in diff.removed],
            modified=[
                SlotChange(before=SlotOut.of(before), after=SlotOut.of(after))
                for before, after in diff.modified
            ],
            unchanged=[SlotOut.of(slot) for slot in diff.unchanged],
        )


class FindingOut(BaseModel):
    """Un hallazgo del lint.

    `slot_name` es el que hace útil al hallazgo del lado del front: nombra el campo que
    falta, así el cliente puede resaltar ese input en vez de mostrar un texto suelto.
    """

    rule_id: str
    family: Family
    severity: Severity
    message: str
    suggestion: str
    slot_name: str | None = None

    @classmethod
    def of(cls, finding: Finding) -> FindingOut:
        return cls(
            rule_id=finding.rule_id,
            family=finding.family,
            severity=finding.severity,
            message=finding.message,
            suggestion=finding.suggestion,
            slot_name=finding.slot_name,
        )


class BriefRequestBody(BaseModel):
    """El pedido de brief tal como llega del front.

    `task_type` se tipa con el `StrEnum` del core y no con `str`: con `str`, un
    `"borrar_todo"` pasa la validación de Pydantic y recién revienta adentro con un
    `ValueError` crudo, o sea un 500 por algo que es claramente culpa del pedido. Un
    enum es un tipo de valor, no dominio filtrándose por el borde, así que usarlo acá
    no crea una tercera fuente de verdad — evita una.

    `None` significa "clasificalo vos": el core sabe inferirlo del texto.
    """

    text: str
    task_type: TaskType | None = None
    profile_name: str | None = None
    profile: ProfileIn | None = None
    success_criteria: str | None = None
    output_format: str | None = None
    file_scope: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    repro_steps: str | None = None
    expected_vs_actual: str | None = None

    def to_request(self, *, task_type: TaskType, profile: Profile | None) -> BriefRequest:
        """El `BriefRequest` del core, con el tipo y el perfil ya resueltos.

        Los dos llegan por parámetro y no se leen de `self` porque resolverlos es una
        decisión del endpoint —clasificar el texto, cargar el perfil del disco— y no
        del esquema, que solo transporta lo que mandó el cliente.
        """
        return BriefRequest(
            text=self.text,
            task_type=task_type,
            profile=profile,
            success_criteria=self.success_criteria,
            output_format=self.output_format,
            file_scope=tuple(self.file_scope),
            constraints=tuple(self.constraints),
            examples=tuple(self.examples),
            repro_steps=self.repro_steps,
            expected_vs_actual=self.expected_vs_actual,
        )


class BriefOut(BaseModel):
    """El brief renderizado.

    Incluye el `task_type` **resuelto** aunque el pedido lo haya mandado vacío: sin
    esto el front tendría que reimplementar la clasificación para saber qué tipo de
    tarea terminó armando, y dos clasificadores en dos lenguajes se separan solos.
    """

    text: str
    task_type: TaskType
    findings: list[FindingOut] = Field(default_factory=list)
    dropped_slots: list[str] = Field(default_factory=list)
    selection: SelectionOut = Field(default_factory=SelectionOut)

    @classmethod
    def of(cls, brief: Brief, task_type: TaskType) -> BriefOut:
        return cls(
            text=brief.text,
            task_type=task_type,
            findings=[FindingOut.of(finding) for finding in brief.findings],
            dropped_slots=list(brief.dropped_slots),
            selection=SelectionOut.of(brief.selection),
        )
