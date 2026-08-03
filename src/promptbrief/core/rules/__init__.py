from promptbrief.core.rules.base import Rule, run_rules
from promptbrief.core.rules.completeness import COMPLETENESS_RULES
from promptbrief.core.rules.context import CONTEXT_RULES
from promptbrief.core.rules.text import TEXT_RULES

ALL_RULES: tuple[Rule, ...] = TEXT_RULES + COMPLETENESS_RULES + CONTEXT_RULES

__all__ = [
    "ALL_RULES",
    "COMPLETENESS_RULES",
    "CONTEXT_RULES",
    "TEXT_RULES",
    "Rule",
    "run_rules",
]
