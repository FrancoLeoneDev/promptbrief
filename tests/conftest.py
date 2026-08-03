from promptbrief.core.models import Provenance, Slot, SlotKind, TaskType

# Instancia a nivel de módulo, no una llamada en el default del parámetro:
# ruff marca B008 (function call in argument defaults) y el CI corre sobre tests/.
# Provenance es frozen, así que compartir la instancia no tiene riesgo.
_DEFAULT_SOURCE = Provenance(file="CLAUDE.md", line=1)


def make_slot(
    id_: str,
    content: str,
    *,
    kind: SlotKind = SlotKind.CONVENTION,
    applies: tuple[TaskType, ...] = (TaskType.CODE_CHANGE,),
    source: Provenance | None = _DEFAULT_SOURCE,
    needs_review: bool = False,
    redacted: bool = False,
) -> Slot:
    """Slot de prueba con defaults razonables. Compartido por toda la suite."""
    return Slot(
        id=id_,
        kind=kind,
        content=content,
        applies_to=applies,
        source=source,
        needs_review=needs_review,
        redacted=redacted,
    )
