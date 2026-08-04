import pytest

from promptbrief.core.models import BriefRequest, CheckContext, Family, Selection, TaskType
from promptbrief.core.rules import ALL_RULES
from promptbrief.core.tasks import REQUIRED_SLOTS

from ..conftest import make_slot

# Los IDs del §6 del spec. Esta lista es el contrato público: cambiarla lo rompe.
SPEC_RULE_IDS = frozenset(
    {
        "missing_success_criteria",
        "dangling_reference",
        "vague_quantifier",
        "negative_instruction",
        "multiple_unrelated_tasks",
        "over_emphasis",
        "missing_output_format",
        "missing_file_scope",
        "missing_constraints",
        "missing_examples",
        "missing_repro",
        "missing_expected_vs_actual",
        "budget_exceeded",
        "profile_mostly_irrelevant",
        "wrong_altitude",
        "stale_profile",
        "secret_redacted",
    }
)


def test_all_rules_expose_exactly_the_public_rule_ids():
    ids = [rule.id for rule in ALL_RULES]
    assert len(ids) == len(set(ids)), "hay IDs duplicados entre familias"
    assert set(ids) == SPEC_RULE_IDS


def test_every_rule_declares_its_family():
    for rule in ALL_RULES:
        assert isinstance(rule.family, Family), rule.id


def _worst_case_context() -> CheckContext:
    """Un contexto armado para que las 17 reglas disparen a la vez.

    El texto acumula a propósito un defecto por cada regla de la familia A:
    referencia sin antecedente, cuantificador vago, instrucción negativa,
    enumeración de tareas y énfasis de más.
    """
    selection = Selection(
        selected=(make_slot("short", "x", redacted=True),),
        over_budget=(make_slot("big", "y" * 8000),),
        not_applicable=tuple(
            make_slot(f"skip{i}", "z", applies=(TaskType.WRITING,)) for i in range(4)
        ),
    )
    request = BriefRequest(
        text="CRITICAL: arreglalo mas rapido, no uses eso y ademas mejoralo",
        task_type=TaskType.DEBUG,
    )
    return CheckContext(request=request, selection=selection, stale_sources=("CLAUDE.md",))


@pytest.mark.parametrize("rule", ALL_RULES, ids=lambda rule: rule.id)
def test_every_rule_produces_a_non_empty_message_and_suggestion(rule):
    finding = rule.check(_worst_case_context())
    assert finding is not None, f"{rule.id} no dispara ni en el peor caso"
    assert finding.message.strip()
    assert finding.suggestion.strip()
    assert finding.rule_id == rule.id


def test_every_finding_that_maps_to_a_field_says_which_one():
    # El front arma el formulario con esto. Sin slot_name tendría que hardcodear el
    # mapeo rule_id -> campo, que es una segunda fuente de verdad sobre REQUIRED_SLOTS.
    every_required = set().union(*REQUIRED_SLOTS.values())
    guarded = {rule.slot_name for rule in ALL_RULES if getattr(rule, "slot_name", None)}
    assert every_required == guarded


def test_the_slot_name_travels_in_the_finding():
    rule = next(r for r in ALL_RULES if r.id == "missing_success_criteria")
    finding = rule.check(_worst_case_context())
    assert finding is not None
    assert finding.slot_name == "success_criteria"


def test_rules_without_a_field_leave_slot_name_empty():
    rule = next(r for r in ALL_RULES if r.id == "dangling_reference")
    finding = rule.check(_worst_case_context())
    assert finding is not None
    assert finding.slot_name is None


def test_missing_success_criteria_derives_its_scope_like_the_rest():
    from promptbrief.core.tasks import tasks_requiring

    rule = next(r for r in ALL_RULES if r.id == "missing_success_criteria")
    assert set(rule.applies_to) == set(tasks_requiring("success_criteria"))
