from __future__ import annotations

from pathlib import Path

from promptbrief.core.budget import select_within_budget
from promptbrief.core.errors import EmptyRequestError
from promptbrief.core.models import Brief, BriefRequest, CheckContext, Finding, Profile
from promptbrief.core.profile.sources import stale_sources
from promptbrief.core.profile.store import load_profile
from promptbrief.core.render import render_brief
from promptbrief.core.rules import ALL_RULES, run_rules


def resolve_profile(name: str) -> Profile:
    """Carga un perfil por nombre. Compartida por la CLI y el servidor del Plan 2.

    Levanta ProfileNotFound, InvalidProfileName o ProfileCorrupt — todas bajo
    PromptBriefError, así que un consumidor HTTP las mapea a 4xx de una.
    """
    return load_profile(name)


def _context(request: BriefRequest, root: Path | None) -> CheckContext:
    if not request.text.strip():
        raise EmptyRequestError("La descripción de la tarea está vacía.")

    profile = request.profile
    if profile is None:
        return CheckContext(request=request)

    selection = select_within_budget(
        profile.slots, request.task_type, request.text, profile.budget_tokens
    )
    target = root or Path(profile.root)
    stale = stale_sources(profile, target) if profile.sources and target.is_dir() else []
    return CheckContext(request=request, selection=selection, stale_sources=tuple(stale))


def lint(request: BriefRequest, root: Path | None = None) -> tuple[Finding, ...]:
    """Hallazgos sin renderizar el brief."""
    return run_rules(_context(request, root), ALL_RULES)


def build_brief(request: BriefRequest, root: Path | None = None) -> Brief:
    """Selecciona contexto, corre las reglas y renderiza. Punto de entrada del core."""
    ctx = _context(request, root)
    return Brief(
        text=render_brief(request, ctx.selection.selected),
        findings=run_rules(ctx, ALL_RULES),
        dropped_slots=tuple(slot.id for slot in ctx.selection.over_budget),
        selection=ctx.selection,
    )
