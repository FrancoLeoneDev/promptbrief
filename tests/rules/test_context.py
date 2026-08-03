from promptbrief.core.models import (
    BriefRequest,
    CheckContext,
    Selection,
    Severity,
    SlotKind,
    TaskType,
)
from promptbrief.core.rules.base import run_rules
from promptbrief.core.rules.context import CONTEXT_RULES

from ..conftest import make_slot
from .conftest import fired


def context_findings(**kwargs) -> dict[str, Severity]:
    return fired(CONTEXT_RULES, **kwargs)


def context_objects(selection: Selection):
    """Los Finding completos, cuando hace falta inspeccionar el mensaje."""
    request = BriefRequest(text="hacer la cosa", task_type=TaskType.CODE_CHANGE)
    return run_rules(CheckContext(request=request, selection=selection), CONTEXT_RULES)


def test_budget_exceeded_fires_when_an_applicable_slot_did_not_fit():
    selection = Selection(over_budget=(make_slot("big", "x" * 8000),))
    assert context_findings(selection=selection)["budget_exceeded"] == Severity.ERROR


def test_budget_exceeded_silent_when_the_only_drop_was_for_task_type():
    # Filtrar por tipo de tarea NO es exceder el presupuesto.
    selection = Selection(
        selected=(make_slot("keep", "Static export is enabled in next.config.ts."),),
        not_applicable=(make_slot("skip", "Tone casual", applies=(TaskType.WRITING,)),),
    )
    assert "budget_exceeded" not in context_findings(selection=selection)


def test_budget_exceeded_silent_when_everything_fit():
    selection = Selection(selected=(make_slot("a", "Static export is enabled."),))
    assert "budget_exceeded" not in context_findings(selection=selection)


def test_budget_exceeded_names_slots_by_provenance_not_by_id():
    selection = Selection(over_budget=(make_slot("claude-convention-a1b2c3d4", "x" * 8000),))
    finding = next(
        f for f in context_objects(selection) if f.rule_id == "budget_exceeded"
    )
    assert "CLAUDE.md:1" in finding.message
    assert "a1b2c3d4" not in finding.message


def test_profile_mostly_irrelevant_fires_when_most_slots_did_not_apply():
    selection = Selection(
        selected=(make_slot("keep", "Static export is enabled."),),
        not_applicable=tuple(
            make_slot(f"skip{i}", "Tone casual", applies=(TaskType.WRITING,)) for i in range(4)
        ),
    )
    assert context_findings(selection=selection)["profile_mostly_irrelevant"] == Severity.INFO


def test_profile_mostly_irrelevant_silent_on_a_well_matched_profile():
    selection = Selection(
        selected=tuple(make_slot(f"k{i}", "Static export is enabled.") for i in range(4)),
        not_applicable=(make_slot("skip", "Tone casual", applies=(TaskType.WRITING,)),),
    )
    assert "profile_mostly_irrelevant" not in context_findings(selection=selection)


def test_profile_mostly_irrelevant_counts_over_budget_slots_as_applicable():
    # Quedaron afuera por tamaño, no por tipo: el perfil sí está calibrado.
    selection = Selection(
        over_budget=tuple(make_slot(f"big{i}", "x" * 8000) for i in range(4)),
        not_applicable=(make_slot("skip", "Tone casual", applies=(TaskType.WRITING,)),),
    )
    assert "profile_mostly_irrelevant" not in context_findings(selection=selection)


def test_wrong_altitude_flags_a_slot_too_short_to_be_actionable():
    selection = Selection(selected=(make_slot("vague", "prolijo"),))
    assert "wrong_altitude" in context_findings(selection=selection)


def test_wrong_altitude_flags_a_slot_too_long_to_survive_a_refactor():
    selection = Selection(selected=(make_slot("brittle", "si x entonces y. " * 60),))
    assert "wrong_altitude" in context_findings(selection=selection)


def test_a_short_constraint_does_not_trip_the_altitude_rule():
    # "Sin npm." son 2 tokens: por debajo del piso. La guarda por kind es lo único
    # que lo salva, así que borrarla hace fallar este test.
    selection = Selection(selected=(make_slot("c", "Sin npm.", kind=SlotKind.CONSTRAINT),))
    assert "wrong_altitude" not in context_findings(selection=selection)


def test_the_same_short_text_as_a_convention_does_trip_it():
    selection = Selection(selected=(make_slot("c", "Sin npm.", kind=SlotKind.CONVENTION),))
    assert "wrong_altitude" in context_findings(selection=selection)


def test_stale_profile_fires_when_a_source_changed():
    assert context_findings(stale_sources=("CLAUDE.md",))["stale_profile"] == Severity.WARNING


def test_stale_profile_silent_when_nothing_changed():
    assert "stale_profile" not in context_findings()


def test_secret_redacted_fires_for_a_slot_that_was_never_injected():
    # Un secreto suele caer bajo un heading no reconocido, así que termina en
    # skipped_for_review. Si la regla solo mirara `selected`, sería inalcanzable.
    selection = Selection(
        skipped_for_review=(make_slot("key", "STRIPE_KEY=[REDACTED]", redacted=True),)
    )
    assert context_findings(selection=selection)["secret_redacted"] == Severity.WARNING


def test_secret_redacted_fires_for_an_injected_slot_too():
    selection = Selection(selected=(make_slot("key", "STRIPE_KEY=[REDACTED]", redacted=True),))
    assert "secret_redacted" in context_findings(selection=selection)


def test_secret_redacted_silent_on_a_clean_profile():
    selection = Selection(selected=(make_slot("clean", "Static export is enabled."),))
    assert "secret_redacted" not in context_findings(selection=selection)
