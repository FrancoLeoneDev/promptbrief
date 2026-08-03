import pytest

from promptbrief.core.build import build_brief, lint
from promptbrief.core.errors import EmptyRequestError
from promptbrief.core.models import BriefRequest, Profile, Severity, SlotKind, SourceFile, TaskType
from promptbrief.core.profile.sources import hash_file

from .conftest import make_slot


def code_request(profile: Profile | None = None, **overrides) -> BriefRequest:
    base = dict(
        text="add a python section",
        task_type=TaskType.CODE_CHANGE,
        profile=profile,
        success_criteria="it renders",
        output_format="code",
        file_scope=("src/x.ts",),
        constraints=("keep config unchanged",),
    )
    base.update(overrides)
    return BriefRequest(**base)


def profile_with(*slots, **kwargs) -> Profile:
    return Profile(name="demo", root="/tmp", sources=(), slots=slots, **kwargs)


def test_applicable_slots_reach_the_brief_and_others_do_not():
    profile = profile_with(
        make_slot("keep", "Static export is enabled."),
        make_slot("skip", "Tone should be casual.", applies=(TaskType.WRITING,)),
    )
    brief = build_brief(code_request(profile))
    assert "Static export is enabled." in brief.text
    assert "Tone should be casual." not in brief.text


def test_filtering_by_task_type_is_not_reported_as_a_budget_problem():
    profile = profile_with(
        make_slot("keep", "Static export is enabled."),
        make_slot("skip", "Tone should be casual.", applies=(TaskType.WRITING,)),
    )
    brief = build_brief(code_request(profile))
    assert brief.dropped_slots == ()
    assert not any(f.rule_id == "budget_exceeded" for f in brief.findings)


def test_the_brief_exposes_the_full_selection_for_the_ui():
    profile = profile_with(
        make_slot("keep", "Static export is enabled."),
        make_slot("skip", "Tone should be casual.", applies=(TaskType.WRITING,)),
        make_slot("unsure", "algo raro", needs_review=True),
    )
    brief = build_brief(code_request(profile))
    assert [s.id for s in brief.selection.selected] == ["keep"]
    assert [s.id for s in brief.selection.not_applicable] == ["skip"]
    assert [s.id for s in brief.selection.skipped_for_review] == ["unsure"]


def test_slots_over_budget_are_reported_and_raise_the_budget_finding():
    profile = profile_with(
        make_slot("huge", "x" * 4000), make_slot("small", "Static export."), budget_tokens=100
    )
    brief = build_brief(code_request(profile))
    assert "huge" in brief.dropped_slots
    assert any(f.rule_id == "budget_exceeded" for f in brief.findings)


def test_constraints_inherited_from_the_profile_silence_the_completeness_rule():
    profile = profile_with(
        make_slot("c", "Keep next.config.ts unchanged.", kind=SlotKind.CONSTRAINT)
    )
    brief = build_brief(code_request(profile, constraints=()))
    assert "Keep next.config.ts unchanged." in brief.text
    assert not any(f.rule_id == "missing_constraints" for f in brief.findings)


def test_a_request_with_no_profile_still_produces_a_brief():
    brief = build_brief(BriefRequest(text="add a section", task_type=TaskType.CODE_CHANGE))
    assert "<task>" in brief.text
    assert any(f.rule_id == "missing_success_criteria" for f in brief.findings)


def test_a_debug_request_renders_its_sections_and_silences_its_rules():
    request = BriefRequest(
        text="the cart empties after adding an item",
        task_type=TaskType.DEBUG,
        success_criteria="the item stays in the cart",
        output_format="code",
        file_scope=("src/cart.ts",),
        repro_steps="add an item, refresh",
        expected_vs_actual="expected the item, got an empty cart",
    )
    brief = build_brief(request)
    assert "<reproduction>" in brief.text
    ids = {f.rule_id for f in brief.findings}
    assert "missing_repro" not in ids
    assert "missing_constraints" not in ids  # no aplica a debug


def test_stale_sources_surface_as_a_finding(tmp_path):
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("original", encoding="utf-8")
    profile = Profile(
        name="demo",
        root=str(tmp_path),
        slots=(),
        sources=(SourceFile(path="CLAUDE.md", sha256=hash_file(claude)),),
    )
    claude.write_text("changed", encoding="utf-8")
    brief = build_brief(code_request(profile), root=tmp_path)
    assert any(f.rule_id == "stale_profile" for f in brief.findings)


def test_findings_come_back_sorted_with_errors_first():
    brief = build_brief(BriefRequest(text="arreglalo", task_type=TaskType.CODE_CHANGE))
    order = [Severity.ERROR, Severity.WARNING, Severity.INFO]
    severities = [order.index(f.severity) for f in brief.findings]
    assert severities == sorted(severities)


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_an_empty_request_is_rejected_instead_of_producing_an_empty_brief(text):
    with pytest.raises(EmptyRequestError):
        build_brief(BriefRequest(text=text, task_type=TaskType.CODE_CHANGE))


def test_lint_returns_the_same_findings_without_rendering():
    request = BriefRequest(text="arreglalo", task_type=TaskType.CODE_CHANGE)
    assert lint(request) == build_brief(request).findings
