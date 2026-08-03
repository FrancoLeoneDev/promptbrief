from promptbrief.core.budget import (
    XML_OVERHEAD_TOKENS,
    estimate_tokens,
    select_within_budget,
    slot_cost,
)
from promptbrief.core.models import TaskType

from .conftest import make_slot


def test_estimate_tokens_is_a_quarter_of_the_character_count():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 400) == 100


def test_slot_cost_includes_the_xml_wrapper():
    slot = make_slot("s", "a" * 400)
    assert slot_cost(slot) == 100 + XML_OVERHEAD_TOKENS


def test_slots_for_another_task_type_are_not_applicable_not_over_budget():
    slots = [
        make_slot("keep", "relevant", applies=(TaskType.CODE_CHANGE,)),
        make_slot("skip", "irrelevant", applies=(TaskType.WRITING,)),
    ]
    result = select_within_budget(slots, TaskType.CODE_CHANGE, "", 1500)
    assert [s.id for s in result.selected] == ["keep"]
    assert [s.id for s in result.not_applicable] == ["skip"]
    assert result.over_budget == ()


def test_empty_applies_to_means_every_task_type():
    result = select_within_budget(
        [make_slot("universal", "stack info", applies=())], TaskType.WRITING, "", 1500
    )
    assert [s.id for s in result.selected] == ["universal"]


def test_slots_needing_review_are_never_injected():
    slots = [make_slot("unsure", "algo que no se pudo clasificar", needs_review=True)]
    result = select_within_budget(slots, TaskType.CODE_CHANGE, "", 1500)
    assert result.selected == ()
    assert [s.id for s in result.skipped_for_review] == ["unsure"]


def test_slots_matching_the_query_are_ranked_first():
    slots = [
        make_slot("unrelated", "database migrations and locking"),
        make_slot("relevant", "portfolio cards render in a grid"),
    ]
    result = select_within_budget(slots, TaskType.CODE_CHANGE, "add portfolio cards", 1500)
    assert result.selected[0].id == "relevant"


def test_relevance_decides_which_slot_survives_a_tight_budget():
    filler = "palabra " * 100  # los dos slots miden casi lo mismo
    slots = [
        make_slot("unrelated", f"database migrations {filler}"),
        make_slot("relevant", f"portfolio cards {filler}"),
    ]
    # Presupuesto para uno solo. slot_cost incluye el overhead XML: calcularlo con
    # estimate_tokens a secas dejaría a los dos afuera.
    budget = slot_cost(slots[0])
    result = select_within_budget(slots, TaskType.CODE_CHANGE, "portfolio cards", budget)
    assert [s.id for s in result.selected] == ["relevant"]
    assert [s.id for s in result.over_budget] == ["unrelated"]


def test_an_accented_query_still_matches_an_unaccented_slot():
    slots = [
        make_slot("unrelated", "database migrations and locking"),
        make_slot("relevant", "la seccion de proyectos vive en portfolio.ts"),
    ]
    result = select_within_budget(slots, TaskType.CODE_CHANGE, "mejorar la sección", 1500)
    assert result.selected[0].id == "relevant"


def test_budget_cuts_the_tail_and_reports_it_as_over_budget():
    big = "x" * 4000
    slots = [make_slot("first", big), make_slot("second", big)]
    result = select_within_budget(slots, TaskType.CODE_CHANGE, "", 1500)
    assert [s.id for s in result.selected] == ["first"]
    assert [s.id for s in result.over_budget] == ["second"]


def test_a_single_slot_over_budget_is_dropped_not_truncated():
    result = select_within_budget([make_slot("huge", "x" * 8000)], TaskType.CODE_CHANGE, "", 1500)
    assert result.selected == ()
    assert [s.id for s in result.over_budget] == ["huge"]


def test_an_empty_slot_does_not_slip_in_for_free():
    result = select_within_budget([make_slot("empty", "")], TaskType.CODE_CHANGE, "", 0)
    assert result.selected == ()
