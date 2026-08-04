from __future__ import annotations

from collections.abc import Sequence
from textwrap import dedent
from xml.sax.saxutils import escape, quoteattr

from promptbrief.core.models import BriefRequest, Slot, SlotKind

_INDENT = "  "
# quoteattr cambia a comilla simple si el valor tiene una comilla doble. Forzar el
# escapado mantiene el atributo siempre con comillas dobles, como el §7 del spec.
_ATTR_ESCAPES = {'"': "&quot;"}


def _indent(text: str, level: int = 1) -> str:
    pad = _INDENT * level
    return "\n".join(f"{pad}{line}" if line.strip() else line for line in text.splitlines())


def _slot_element(slot: Slot) -> str:
    attr = ""
    if slot.source:
        attr = f" source={quoteattr(slot.source.label(), _ATTR_ESCAPES)}"
    tag = slot.kind.value
    return f"{_INDENT}<{tag}{attr}>{escape(slot.content)}</{tag}>"


def _project_context(slots: Sequence[Slot], paths: Sequence[str]) -> str:
    clean_paths = [path.strip() for path in paths if path.strip()]
    if not slots and not clean_paths:
        return ""
    lines = ["<project_context>"]
    lines.extend(_slot_element(slot) for slot in slots)
    if clean_paths:
        lines.append(f"{_INDENT}<relevant_paths>")
        lines.extend(f"{_INDENT * 2}{escape(path)}" for path in clean_paths)
        lines.append(f"{_INDENT}</relevant_paths>")
    lines.append("</project_context>")
    return "\n".join(lines)


def _section(tag: str, body: str) -> str:
    if not body.strip():
        return ""
    return f"<{tag}>\n{_indent(escape(body.strip()))}\n</{tag}>"


def _examples(examples: Sequence[str]) -> str:
    # dedent antes del strip: sobre un bloque de código indentado, strip a secas se
    # come la sangría de la primera línea nada más y distorsiona la relativa —
    # "def f():" queda a 4 espacios y "return 1" a 12.
    clean = [dedent(text).strip() for text in examples if text.strip()]
    if not clean:
        return ""
    blocks = [
        f"{_INDENT}<example>\n{_indent(escape(text), 2)}\n{_INDENT}</example>" for text in clean
    ]
    return "<examples>\n" + "\n".join(blocks) + "\n</examples>"


def render_brief(request: BriefRequest, selected: Sequence[Slot]) -> str:
    """Emite el brief. Contexto largo arriba, consulta abajo (F1 del spec).

    Las secciones vacías no se emiten. Nunca se emite <role>. Los slots de tipo
    CONSTRAINT van a <constraints>, no a <project_context>.
    """
    context_slots = [slot for slot in selected if slot.kind is not SlotKind.CONSTRAINT]
    inherited = [slot.content for slot in selected if slot.kind is SlotKind.CONSTRAINT]
    constraint_items = [
        item.strip() for item in [*inherited, *request.constraints] if item.strip()
    ]

    sections = [
        _project_context(context_slots, request.file_scope),
        _section("constraints", "\n".join(constraint_items)),
        _examples(request.examples),
        _section("reproduction", request.repro_steps or ""),
        _section("expected_vs_actual", request.expected_vs_actual or ""),
        _section("task", request.text),
        _section("success_criteria", request.success_criteria or ""),
        _section("output_format", request.output_format or ""),
    ]
    return "\n\n".join(section for section in sections if section)
