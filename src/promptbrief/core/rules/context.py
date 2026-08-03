from __future__ import annotations

from promptbrief.core.budget import estimate_tokens
from promptbrief.core.models import CheckContext, Family, Finding, Severity, SlotKind
from promptbrief.core.rules.base import Rule

# ~12 caracteres. Por debajo de esto un dato no dice nada accionable ("ser prolijo").
MIN_USEFUL_TOKENS = 3
# ~480 caracteres. Por encima, la regla es tan específica que cualquier refactor la rompe.
MAX_HEALTHY_TOKENS = 120
# Si menos de la mitad de los datos del perfil aplican, está calibrado para otro trabajo.
MIN_APPLICABLE_RATIO = 0.5


class BudgetExceeded(Rule):
    id = "budget_exceeded"
    family = Family.CONTEXT
    severity = Severity.ERROR

    def check(self, ctx: CheckContext) -> Finding | None:
        if not ctx.selection.over_budget:
            return None
        names = ", ".join(slot.label() for slot in ctx.selection.over_budget)
        return self._finding(
            f"Contexto aplicable que no entró en el presupuesto: {names}.",
            "Recortá el perfil o subí el presupuesto. Inyectar de más también empeora "
            "el resultado: cuanto más largo el contexto, peor recupera el modelo lo "
            "importante.",
        )


class ProfileMostlyIrrelevant(Rule):
    id = "profile_mostly_irrelevant"
    family = Family.CONTEXT
    severity = Severity.INFO

    def check(self, ctx: CheckContext) -> Finding | None:
        selection = ctx.selection
        # over_budget cuenta como aplicable: quedó afuera por tamaño, no por tipo.
        applicable = len(selection.selected) + len(selection.over_budget)
        considered = applicable + len(selection.not_applicable)
        if considered == 0 or applicable / considered >= MIN_APPLICABLE_RATIO:
            return None
        return self._finding(
            f"Solo {applicable} de {considered} datos del perfil aplican a este tipo de tarea.",
            "Revisá el campo applies_to del perfil: probablemente esté calibrado para "
            "otro tipo de trabajo del que hacés en este repo.",
        )


class WrongAltitude(Rule):
    """Detecta datos del perfil que no sirven por ser demasiado vagos o demasiado frágiles.

    La metáfora es la "altitud correcta" de F6 del spec: un dato tiene que ser
    específico como para guiar y general como para sobrevivir a un refactor.
    """

    id = "wrong_altitude"
    family = Family.CONTEXT
    severity = Severity.INFO

    def check(self, ctx: CheckContext) -> Finding | None:
        too_vague: list[str] = []
        too_brittle: list[str] = []
        for slot in ctx.selection.selected:
            # Las restricciones son cortas por naturaleza ("Sin npm."), así que el
            # piso de longitud no les aplica.
            size = estimate_tokens(slot.content)
            if size < MIN_USEFUL_TOKENS and slot.kind is not SlotKind.CONSTRAINT:
                too_vague.append(slot.label())
            elif size > MAX_HEALTHY_TOKENS:
                too_brittle.append(slot.label())

        if not too_vague and not too_brittle:
            return None

        parts: list[str] = []
        if too_vague:
            parts.append(f"demasiado vagos: {', '.join(too_vague)}")
        if too_brittle:
            parts.append(f"demasiado específicos y frágiles: {', '.join(too_brittle)}")
        return self._finding(
            f"Hay datos del perfil fuera de altura ({'; '.join(parts)}).",
            "Apuntá al punto medio: específico como para guiar, general como para no "
            "romperse cuando el código cambie.",
        )


class StaleProfile(Rule):
    id = "stale_profile"
    family = Family.CONTEXT
    severity = Severity.WARNING

    def check(self, ctx: CheckContext) -> Finding | None:
        if not ctx.stale_sources:
            return None
        return self._finding(
            f"Estos archivos cambiaron desde la última destilación: "
            f"{', '.join(ctx.stale_sources)}.",
            "Corré pbrief scan de nuevo para actualizar el perfil.",
        )


class SecretRedacted(Rule):
    """Avisa que se tapó una credencial, la haya inyectado o no.

    Mira todos los slots del perfil, no solo los seleccionados: un secreto suelto
    suele caer bajo un heading no reconocido y terminar en `skipped_for_review`,
    así que mirar solo `selected` volvería la regla prácticamente inalcanzable.
    """

    id = "secret_redacted"
    family = Family.CONTEXT
    severity = Severity.WARNING

    def check(self, ctx: CheckContext) -> Finding | None:
        scrubbed = [slot.label() for slot in ctx.selection.all_slots() if slot.redacted]
        if not scrubbed:
            return None
        return self._finding(
            f"Se tapó algo con forma de credencial al destilar: {', '.join(scrubbed)}.",
            "Sacá el secreto del archivo fuente y movelo a una variable de entorno. "
            "El valor no salió en el brief, pero sigue estando en el repo.",
        )


CONTEXT_RULES: tuple[Rule, ...] = (
    BudgetExceeded(),
    ProfileMostlyIrrelevant(),
    WrongAltitude(),
    StaleProfile(),
    SecretRedacted(),
)
