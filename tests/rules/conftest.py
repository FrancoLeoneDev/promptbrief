from collections.abc import Sequence

from promptbrief.core.models import BriefRequest, CheckContext, Selection, Severity, TaskType
from promptbrief.core.rules.base import Rule, run_rules


def fired(
    rules: Sequence[Rule],
    text: str = "hacer la cosa",
    task_type: TaskType = TaskType.CODE_CHANGE,
    selection: Selection | None = None,
    stale_sources: tuple[str, ...] = (),
    **request_kwargs,
) -> dict[str, Severity]:
    """Corre `rules` y devuelve {rule_id: severidad}. Mismo shape en las tres familias."""
    request = BriefRequest(text=text, task_type=task_type, **request_kwargs)
    ctx = CheckContext(
        request=request,
        selection=selection or Selection(),
        stale_sources=stale_sources,
    )
    return {finding.rule_id: finding.severity for finding in run_rules(ctx, rules)}
