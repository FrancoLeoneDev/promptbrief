from __future__ import annotations

from collections.abc import Sequence

from promptbrief.core.models import Selection, Slot, TaskType
from promptbrief.core.text import terms

CHARS_PER_TOKEN = 4
# Cada slot cuesta además su envoltorio: <convention source="CLAUDE.md:12">…</convention>
XML_OVERHEAD_TOKENS = 12


def estimate_tokens(text: str) -> int:
    """Estimación por caracteres. Suficiente para presupuestar, sin tokenizador."""
    return len(text) // CHARS_PER_TOKEN


def slot_cost(slot: Slot) -> int:
    """Lo que cuesta inyectar un slot, envoltorio XML incluido."""
    return estimate_tokens(slot.content) + XML_OVERHEAD_TOKENS


def _relevance(slot: Slot, query_terms: set[str]) -> int:
    if not query_terms:
        return 0
    return len(terms(slot.content) & query_terms)


def select_within_budget(
    slots: Sequence[Slot],
    task_type: TaskType,
    query: str,
    budget: int,
) -> Selection:
    """Filtra, ordena por relevancia y corta en el presupuesto.

    Nunca trunca el contenido de un slot: entra entero o no entra. Los motivos de
    exclusión se devuelven por separado porque solo uno de ellos es un problema.
    """
    applicable: list[Slot] = []
    not_applicable: list[Slot] = []
    skipped_for_review: list[Slot] = []

    for slot in slots:
        if slot.needs_review:
            skipped_for_review.append(slot)
        elif slot.applies_to and task_type not in slot.applies_to:
            not_applicable.append(slot)
        else:
            applicable.append(slot)

    query_terms = terms(query)
    applicable.sort(key=lambda slot: _relevance(slot, query_terms), reverse=True)

    selected: list[Slot] = []
    over_budget: list[Slot] = []
    spent = 0
    for slot in applicable:
        cost = slot_cost(slot)
        if spent + cost <= budget:
            selected.append(slot)
            spent += cost
        else:
            over_budget.append(slot)

    return Selection(
        selected=tuple(selected),
        over_budget=tuple(over_budget),
        not_applicable=tuple(not_applicable),
        skipped_for_review=tuple(skipped_for_review),
    )
