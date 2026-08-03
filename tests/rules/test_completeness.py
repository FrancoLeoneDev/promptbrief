from promptbrief.core.models import Selection, SlotKind, TaskType
from promptbrief.core.rules.completeness import COMPLETENESS_RULES
from promptbrief.core.tasks import REQUIRED_SLOTS

from ..conftest import make_slot
from .conftest import fired


def completeness(task_type: TaskType, **kwargs) -> dict[str, object]:
    return fired(COMPLETENESS_RULES, task_type=task_type, **kwargs)


def test_each_rule_applies_exactly_where_required_slots_says():
    for rule in COMPLETENESS_RULES:
        expected = {
            task for task, required in REQUIRED_SLOTS.items() if rule.slot_name in required
        }
        assert set(rule.applies_to) == expected, rule.id


def test_every_required_slot_has_a_rule_guarding_it():
    guarded = {rule.slot_name for rule in COMPLETENESS_RULES}
    required = set().union(*REQUIRED_SLOTS.values())
    assert required - guarded == {"success_criteria"}, "success_criteria lo cubre la familia A"


def test_missing_output_format_fires_on_every_task_type():
    for task_type in TaskType:
        assert "missing_output_format" in completeness(task_type)


def test_missing_output_format_silent_when_provided():
    assert "missing_output_format" not in completeness(
        TaskType.CODE_CHANGE, output_format="code changes with paths"
    )


def test_missing_file_scope_fires_on_code_change_but_not_on_writing():
    assert "missing_file_scope" in completeness(TaskType.CODE_CHANGE)
    assert "missing_file_scope" not in completeness(TaskType.WRITING)


def test_missing_file_scope_silent_when_paths_are_given():
    assert "missing_file_scope" not in completeness(
        TaskType.CODE_CHANGE, file_scope=("src/data/portfolio.ts",)
    )


def test_missing_constraints_silent_when_the_user_declared_them():
    assert "missing_constraints" not in completeness(
        TaskType.CODE_CHANGE, constraints=("keep next.config.ts unchanged",)
    )


def test_missing_constraints_silent_when_the_profile_supplied_them():
    # La regla dice "ni heredada del perfil": tiene que mirar lo inyectado.
    selection = Selection(
        selected=(make_slot("c1", "Keep next.config.ts unchanged.", kind=SlotKind.CONSTRAINT),)
    )
    assert "missing_constraints" not in completeness(TaskType.CODE_CHANGE, selection=selection)


def test_missing_constraints_fires_when_neither_source_supplied_any():
    selection = Selection(selected=(make_slot("s1", "Next.js 15", kind=SlotKind.STACK),))
    assert "missing_constraints" in completeness(TaskType.CODE_CHANGE, selection=selection)


def test_missing_examples_fires_only_on_writing():
    assert "missing_examples" in completeness(TaskType.WRITING)
    assert "missing_examples" not in completeness(TaskType.CODE_CHANGE)


def test_missing_examples_silent_when_provided():
    assert "missing_examples" not in completeness(
        TaskType.WRITING, examples=("un texto de ejemplo",)
    )


def test_debug_specific_rules_fire_only_on_debug():
    debug = completeness(TaskType.DEBUG)
    assert {"missing_repro", "missing_expected_vs_actual"} <= set(debug)
    assert "missing_repro" not in completeness(TaskType.CODE_CHANGE)


def test_debug_rules_silent_when_provided():
    ids = completeness(
        TaskType.DEBUG,
        repro_steps="agregar un producto al carrito y refrescar",
        expected_vs_actual="esperaba ver el item, veo el carrito vacio",
    )
    assert "missing_repro" not in ids
    assert "missing_expected_vs_actual" not in ids
