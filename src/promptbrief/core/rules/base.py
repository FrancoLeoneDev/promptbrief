from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from promptbrief.core.models import CheckContext, Family, Finding, Severity, TaskType

_SEVERITY_ORDER = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


class Rule(ABC):
    """Interfaz uniforme de todas las reglas.

    `id` es contrato público: no se renombra una vez publicado.
    `applies_to` vacío significa "todos los tipos de tarea".
    """

    id: str
    family: Family
    severity: Severity
    applies_to: tuple[TaskType, ...] = ()

    @abstractmethod
    def check(self, ctx: CheckContext) -> Finding | None: ...

    def _finding(self, message: str, suggestion: str) -> Finding:
        return Finding(
            rule_id=self.id,
            family=self.family,
            severity=self.severity,
            message=message,
            suggestion=suggestion,
        )


def run_rules(ctx: CheckContext, rules: Sequence[Rule]) -> tuple[Finding, ...]:
    """Corre las reglas aplicables al tipo de tarea. Devuelve errores primero."""
    findings: list[Finding] = []
    for rule in rules:
        if rule.applies_to and ctx.request.task_type not in rule.applies_to:
            continue
        finding = rule.check(ctx)
        if finding is not None:
            findings.append(finding)
    findings.sort(key=lambda finding: _SEVERITY_ORDER[finding.severity])
    return tuple(findings)
