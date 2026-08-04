from __future__ import annotations

from promptbrief.core.models import CheckContext, Family, Finding, Severity, SlotKind
from promptbrief.core.rules.base import Rule
from promptbrief.core.tasks import tasks_requiring


class CompletenessRule(Rule):
    """Regla que vigila un slot concreto de REQUIRED_SLOTS.

    `slot_name` es explícito y no se infiere del `id`: `missing_repro` vigila
    `repro_steps`, así que derivarlo del id daría una clave inexistente.
    """

    family = Family.COMPLETENESS
    slot_name: str

    def _finding(self, message: str, suggestion: str, slot_name: str | None = None) -> Finding:
        return super()._finding(message, suggestion, slot_name=slot_name or self.slot_name)


class MissingSuccessCriteria(CompletenessRule):
    id = "missing_success_criteria"
    slot_name = "success_criteria"
    severity = Severity.ERROR
    applies_to = tasks_requiring("success_criteria")

    def check(self, ctx: CheckContext) -> Finding | None:
        if ctx.request.success_criteria:
            return None
        return self._finding(
            "No declaraste cuándo la tarea está terminada.",
            "Agregá qué tiene que pasar para considerarla lista: un test que pasa, "
            "algo que se ve en pantalla, un número que baja.",
        )


class MissingOutputFormat(CompletenessRule):
    id = "missing_output_format"
    slot_name = "output_format"
    severity = Severity.WARNING
    applies_to = tasks_requiring("output_format")

    def check(self, ctx: CheckContext) -> Finding | None:
        if ctx.request.output_format:
            return None
        return self._finding(
            "No dijiste qué forma tiene que tener la respuesta.",
            "Elegí una: cambios de código con rutas, una lista de opciones, un diff, un texto.",
        )


class MissingFileScope(CompletenessRule):
    id = "missing_file_scope"
    slot_name = "file_scope"
    severity = Severity.WARNING
    applies_to = tasks_requiring("file_scope")

    def check(self, ctx: CheckContext) -> Finding | None:
        if ctx.request.file_scope:
            return None
        return self._finding(
            "No hay ningún archivo ni módulo en el alcance.",
            "Nombrá al menos por dónde empezar, o decí explícitamente que no sabés: "
            "el agente puede buscarlo, pero conviene que sepa que tiene que buscar.",
        )


class MissingConstraints(CompletenessRule):
    id = "missing_constraints"
    slot_name = "constraints"
    severity = Severity.WARNING
    applies_to = tasks_requiring("constraints")

    def check(self, ctx: CheckContext) -> Finding | None:
        inherited = any(slot.kind is SlotKind.CONSTRAINT for slot in ctx.selection.selected)
        if ctx.request.constraints or inherited:
            return None
        return self._finding(
            "No declaraste ninguna restricción, y el perfil tampoco aportó.",
            "Nombrá qué no hay que tocar, qué patrón seguir, qué dependencia no agregar.",
        )


class MissingExamples(CompletenessRule):
    """Exige ejemplos en tareas de escritura.

    Es F7 del spec: los ejemplos few-shot son de lo más efectivo para fijar
    tono y formato.
    """

    id = "missing_examples"
    slot_name = "examples"
    severity = Severity.WARNING
    applies_to = tasks_requiring("examples")

    def check(self, ctx: CheckContext) -> Finding | None:
        if ctx.request.examples:
            return None
        return self._finding(
            "Tarea de escritura sin ejemplos.",
            "Pegá uno o dos textos tuyos que suenen como querés: es lo que más mueve "
            "la aguja en tono y formato.",
        )


class MissingRepro(CompletenessRule):
    id = "missing_repro"
    slot_name = "repro_steps"
    severity = Severity.ERROR
    applies_to = tasks_requiring("repro_steps")

    def check(self, ctx: CheckContext) -> Finding | None:
        if ctx.request.repro_steps:
            return None
        return self._finding(
            "No hay pasos para reproducir el problema.",
            "Contá qué hacés, en qué orden, y desde qué estado inicial.",
        )


class MissingExpectedVsActual(CompletenessRule):
    id = "missing_expected_vs_actual"
    slot_name = "expected_vs_actual"
    severity = Severity.ERROR
    applies_to = tasks_requiring("expected_vs_actual")

    def check(self, ctx: CheckContext) -> Finding | None:
        if ctx.request.expected_vs_actual:
            return None
        return self._finding(
            'Falta el par "qué esperaba que pase" / "qué pasa en realidad".',
            "Escribí los dos: sin eso, el agente adivina cuál de los dos comportamientos "
            "es el bug.",
        )


COMPLETENESS_RULES: tuple[Rule, ...] = (
    MissingSuccessCriteria(),
    MissingOutputFormat(),
    MissingFileScope(),
    MissingConstraints(),
    MissingExamples(),
    MissingRepro(),
    MissingExpectedVsActual(),
)
