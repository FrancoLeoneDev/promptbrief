import pytest

from promptbrief.core.models import BriefRequest, CheckContext, Family, Selection, TaskType
from promptbrief.core.rules import ALL_RULES

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
