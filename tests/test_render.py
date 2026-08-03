from xml.etree import ElementTree

from promptbrief.core.models import BriefRequest, Provenance, SlotKind, TaskType
from promptbrief.core.render import render_brief

from .conftest import make_slot


def full_request(**overrides) -> BriefRequest:
    base = dict(
        text="Add a Python projects section",
        task_type=TaskType.CODE_CHANGE,
        success_criteria="Cards render like the Game Dev ones",
        output_format="Code changes with file paths",
        file_scope=("src/data/portfolio.ts", "src/components/GameDev.tsx"),
        constraints=("Keep next.config.ts unchanged",),
    )
    base.update(overrides)
    return BriefRequest(**base)


def test_sections_appear_in_the_documented_order():
    out = render_brief(full_request(), [make_slot("s", "Next.js 15", kind=SlotKind.STACK)])
    positions = [
        out.index("<project_context>"),
        out.index("<constraints>"),
        out.index("<task>"),
        out.index("<success_criteria>"),
        out.index("<output_format>"),
    ]
    assert positions == sorted(positions)


def test_each_slot_kind_becomes_its_own_tag():
    slots = [
        make_slot("s", "Next.js 15", kind=SlotKind.STACK),
        make_slot("c", "Static export enabled", kind=SlotKind.CONVENTION),
    ]
    out = render_brief(full_request(), slots)
    assert "<stack" in out
    assert "<convention" in out


def test_constraint_slots_land_in_constraints_not_in_project_context():
    slots = [make_slot("c", "Keep next.config.ts unchanged.", kind=SlotKind.CONSTRAINT)]
    out = render_brief(full_request(constraints=()), slots)
    constraints_block = out[out.index("<constraints>") : out.index("</constraints>")]
    assert "Keep next.config.ts unchanged." in constraints_block
    assert "Keep next.config.ts unchanged." not in out[: out.index("<constraints>")]


def test_provenance_is_emitted_as_a_double_quoted_attribute():
    slots = [make_slot("c", "Static export", source=Provenance(file="CLAUDE.md", line=12))]
    assert 'source="CLAUDE.md:12"' in render_brief(full_request(), slots)


def test_a_quote_in_a_filename_cannot_break_out_of_the_attribute():
    slots = [make_slot("c", "Static export", source=Provenance(file='we"ird.md', line=3))]
    out = render_brief(full_request(), slots)
    # El marcado sigue siendo parseable y el atributo round-trippea intacto.
    root = ElementTree.fromstring(f"<root>{out}</root>")
    assert root.find(".//convention").get("source") == 'we"ird.md:3'


def test_the_whole_brief_is_well_formed_xml():
    slots = [make_slot("c", "a < b && c > d", source=Provenance(file="CLAUDE.md", line=1))]
    out = render_brief(full_request(), slots)
    ElementTree.fromstring(f"<root>{out}</root>")


def test_file_scope_lists_paths_and_never_file_contents():
    out = render_brief(full_request(), [])
    assert "<relevant_paths>" in out
    assert "src/data/portfolio.ts" in out


def test_debug_sections_render_above_the_task():
    request = BriefRequest(
        text="the cart is empty after adding an item",
        task_type=TaskType.DEBUG,
        repro_steps="add an item, refresh",
        expected_vs_actual="expected the item, got an empty cart",
    )
    out = render_brief(request, [])
    assert out.index("<reproduction>") < out.index("<task>")
    assert out.index("<expected_vs_actual>") < out.index("<task>")


def test_empty_sections_are_omitted_entirely():
    out = render_brief(BriefRequest(text="do it", task_type=TaskType.CODE_CHANGE), [])
    for tag in ("<constraints>", "<success_criteria>", "<examples>", "<project_context>"):
        assert tag not in out
    assert "<task>" in out


def test_no_role_section_is_ever_emitted():
    out = render_brief(full_request(), [make_slot("s", "Next.js 15", kind=SlotKind.STACK)])
    assert "<role>" not in out


def test_examples_are_wrapped_individually():
    request = BriefRequest(
        text="write a post",
        task_type=TaskType.WRITING,
        examples=("first sample", "second sample"),
    )
    assert render_brief(request, []).count("<example>") == 2


def test_xml_special_characters_in_the_task_are_escaped():
    out = render_brief(BriefRequest(text="fix a < b && c > d", task_type=TaskType.CODE_CHANGE), [])
    assert "&lt;" in out and "&amp;" in out


def test_blank_examples_are_dropped_not_emitted_as_empty_tags():
    request = BriefRequest(
        text="write a post",
        task_type=TaskType.WRITING,
        examples=("first sample", "", "   ", "second sample"),
    )
    out = render_brief(request, [])
    assert out.count("<example>") == 2
    assert "first sample" in out and "second sample" in out


def test_all_blank_examples_omit_the_examples_section_entirely():
    request = BriefRequest(
        text="write a post",
        task_type=TaskType.WRITING,
        examples=("", "   "),
    )
    assert "<examples>" not in render_brief(request, [])


def test_blank_constraint_items_leave_no_empty_line_in_the_section():
    slots = [make_slot("c", "   ", kind=SlotKind.CONSTRAINT)]
    out = render_brief(full_request(constraints=("a", "", "  ", "b")), slots)
    constraints_block = out[out.index("<constraints>") : out.index("</constraints>")]
    assert "\n\n" not in constraints_block
    assert "a" in constraints_block and "b" in constraints_block


def test_blank_file_scope_entries_leave_no_empty_line_in_relevant_paths():
    request = full_request(file_scope=("a.ts", "", "   ", "b.ts"))
    out = render_brief(request, [])
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "<relevant_paths>")
    end = next(i for i, line in enumerate(lines) if line.strip() == "</relevant_paths>")
    inner_lines = lines[start + 1 : end]
    assert all(line.strip() for line in inner_lines)
    assert "a.ts" in out and "b.ts" in out
