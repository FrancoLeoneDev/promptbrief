from __future__ import annotations

import re

from promptbrief.core.models import TaskType
from promptbrief.core.text import strip_accents

_SIGNALS: dict[TaskType, tuple[str, ...]] = {
    TaskType.DEBUG: (
        "error", "errores", "falla", "fallando", "rompe", "roto", "bug", "bugs",
        "excepcion", "crash", "crashea", "failing", "fails", "broken", "traceback",
        "no anda", "no funciona", "stack trace",
    ),
    TaskType.WRITING: (
        "post", "posteo", "linkedin", "readme", "documentar", "documentacion",
        "redactar", "escribir", "escribi", "draft", "article", "blog", "changelog",
    ),
    TaskType.CODE_CHANGE: (
        "agregar", "agrega", "crear", "crea", "implementar", "modificar", "refactor",
        "add", "create", "implement", "build", "update", "rename", "migrate",
    ),
}

# El orden importa: debug gana sobre code_change cuando aparecen señales de ambos,
# porque "arreglar el error al agregar un producto" es un debug, no un feature.
_PRIORITY = (TaskType.DEBUG, TaskType.WRITING, TaskType.CODE_CHANGE)


def _matcher(signals: tuple[str, ...]) -> re.Pattern[str]:
    # \b en los bordes: "post" no debe matchear dentro de "postgres",
    # ni "add" dentro de "padding".
    return re.compile(r"\b(?:" + "|".join(re.escape(s) for s in signals) + r")\b")


_MATCHERS: dict[TaskType, re.Pattern[str]] = {
    task: _matcher(signals) for task, signals in _SIGNALS.items()
}


def classify(text: str) -> TaskType:
    """Detecta el tipo de tarea. Ante la duda devuelve CODE_CHANGE."""
    normalized = strip_accents(text.lower())
    for task_type in _PRIORITY:
        if _MATCHERS[task_type].search(normalized):
            return task_type
    return TaskType.CODE_CHANGE
