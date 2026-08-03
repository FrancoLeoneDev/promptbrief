import dataclasses

import pytest

from promptbrief.core import models
from promptbrief.core.models import (
    Brief,
    BriefRequest,
    CheckContext,
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

MODEL_CLASSES = (
    Provenance, Slot, SourceFile, Profile, BriefRequest, Selection, CheckContext, Finding, Brief,
)


def test_every_model_is_frozen_and_free_of_mutable_defaults():
    for cls in MODEL_CLASSES:
        assert cls.__dataclass_params__.frozen, cls.__name__
        for field in dataclasses.fields(cls):
            assert not isinstance(field.default, (list, dict, set)), f"{cls.__name__}.{field.name}"


def test_every_model_class_in_the_module_is_covered_by_this_test():
    declared = {
        obj
        for obj in vars(models).values()
        if dataclasses.is_dataclass(obj) and obj.__module__ == models.__name__
    }
    assert declared == set(MODEL_CLASSES)


def test_a_slot_cannot_be_mutated_after_creation():
    slot = Slot(
        id="claude-convention-a1b2c3d4",
        kind=SlotKind.CONVENTION,
        content="Static export via output 'export'",
        applies_to=(TaskType.CODE_CHANGE,),
        source=Provenance(file="CLAUDE.md", line=12),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        slot.content = "tampered"


def test_slot_carries_provenance_and_safe_defaults():
    slot = Slot(
        id="claude-convention-a1b2c3d4",
        kind=SlotKind.CONVENTION,
        content="Static export",
        applies_to=(TaskType.CODE_CHANGE, TaskType.DEBUG),
        source=Provenance(file="CLAUDE.md", line=12),
    )
    assert slot.source.line == 12
    assert slot.needs_review is False
    assert slot.redacted is False


def test_profile_defaults_to_1500_token_budget():
    assert Profile(name="demo", root="/tmp/demo", slots=(), sources=()).budget_tokens == 1500


def test_brief_request_defaults_are_empty_tuples_not_none():
    req = BriefRequest(text="add a section", task_type=TaskType.CODE_CHANGE)
    assert req.profile is None
    assert (req.file_scope, req.constraints, req.examples) == ((), (), ())
    assert req.success_criteria is None


def test_selection_separates_the_reasons_a_slot_can_be_left_out():
    selection = Selection()
    assert selection.selected == ()
    assert selection.over_budget == ()
    assert selection.not_applicable == ()
    assert selection.skipped_for_review == ()


def test_check_context_defaults_to_an_empty_selection():
    ctx = CheckContext(request=BriefRequest(text="x", task_type=TaskType.DEBUG))
    assert ctx.selection.selected == ()
    assert ctx.stale_sources == ()


def test_finding_and_brief_shapes():
    finding = Finding(
        rule_id="missing_success_criteria",
        family=Family.TEXT,
        severity=Severity.ERROR,
        message="No declaraste cuándo la tarea está terminada.",
        suggestion="Agregá qué tiene que pasar para considerarla lista.",
    )
    brief = Brief(text="<task>x</task>", findings=(finding,))
    assert brief.findings[0].family == Family.TEXT
    assert brief.dropped_slots == ()
    assert brief.selection.selected == ()
    assert SourceFile(path="CLAUDE.md", sha256="abc").sha256 == "abc"
