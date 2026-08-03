from promptbrief.core.rules.base import Rule, run_rules
from promptbrief.core.rules.text import TEXT_RULES

ALL_RULES: tuple[Rule, ...] = TEXT_RULES

__all__ = ["ALL_RULES", "TEXT_RULES", "Rule", "run_rules"]
