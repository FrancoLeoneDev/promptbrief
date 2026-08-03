from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from promptbrief.core.models import TaskType

# Única fuente de verdad sobre qué exige cada tipo de tarea. Las reglas de la
# familia B derivan su applies_to de acá en vez de repetirlo.
REQUIRED_SLOTS: Mapping[TaskType, frozenset[str]] = MappingProxyType(
    {
        TaskType.CODE_CHANGE: frozenset(
            {"success_criteria", "output_format", "file_scope", "constraints"}
        ),
        TaskType.DEBUG: frozenset(
            {
                "success_criteria",
                "output_format",
                "file_scope",
                "repro_steps",
                "expected_vs_actual",
            }
        ),
        TaskType.WRITING: frozenset({"success_criteria", "output_format", "examples"}),
    }
)


def tasks_requiring(slot_name: str) -> tuple[TaskType, ...]:
    """Tipos de tarea que exigen ese slot. Vacío si ninguno lo exige."""
    return tuple(task for task, required in REQUIRED_SLOTS.items() if slot_name in required)
