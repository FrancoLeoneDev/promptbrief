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

# "error"/"bug" también aparecen en sustantivos compuestos de vocabulario técnico
# normal ("error handler", "error boundary", "bug tracker"...) donde no reportan
# ninguna falla. Si les sigue una de estas palabras, no cuentan como señal de debug.
_DEBUG_COMPOUND_NOUNS = ("handler", "boundary", "message", "handling", "page", "log")
_DEBUG_AMBIGUOUS_SIGNALS = frozenset({"error", "bug"})
_DEBUG_COMPOUND_GUARD = r"(?!\s+(?:" + "|".join(_DEBUG_COMPOUND_NOUNS) + r")\b)"


def _signal_pattern(task_type: TaskType, signal: str) -> str:
    is_ambiguous = task_type is TaskType.DEBUG and signal in _DEBUG_AMBIGUOUS_SIGNALS
    guard = _DEBUG_COMPOUND_GUARD if is_ambiguous else ""
    return re.escape(signal) + guard


def _matcher(task_type: TaskType, signals: tuple[str, ...]) -> re.Pattern[str]:
    # \b en los bordes: "post" no debe matchear dentro de "postgres", ni "add" dentro
    # de "padding". El (?!-) final excluye compuestos con guion: sin él, "bug"
    # matchea dentro de "bug-free" y "post" dentro de "post-mortem", porque el guion
    # es un carácter no-palabra y \b solo mira la transición palabra/no-palabra.
    alternatives = "|".join(_signal_pattern(task_type, s) for s in signals)
    return re.compile(r"\b(?:" + alternatives + r")\b(?!-)")


_MATCHERS: dict[TaskType, re.Pattern[str]] = {
    task: _matcher(task, signals) for task, signals in _SIGNALS.items()
}


def classify(text: str) -> TaskType:
    """Detecta el tipo de tarea. Ante la duda devuelve CODE_CHANGE."""
    normalized = strip_accents(text.lower())
    for task_type in _PRIORITY:
        if _MATCHERS[task_type].search(normalized):
            return task_type
    return TaskType.CODE_CHANGE
