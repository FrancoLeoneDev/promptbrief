from __future__ import annotations

import re

from promptbrief.core.models import CheckContext, Family, Finding, Severity
from promptbrief.core.rules.base import Rule
from promptbrief.core.text import strip_accents

_DANGLING = re.compile(
    r"\b(?:arreglalo|arreglala|hacelo|hacela|cambialo|cambiala|"
    r"que\s+ande|que\s+funcione|lo\s+mismo\s+de\s+antes|fix\s+it|make\s+it\s+work)\b"
)
# Una extensión de archivo o un sustantivo concreto desactiva la regla: el pronombre
# tiene antecedente aunque sea vago.
_CONCRETE = re.compile(
    r"\.(?:tsx?|jsx?|py|cs|md|json|ya?ml|css)\b"
    r"|\b(?:componente|component|pagina|page|funcion|function|modulo|module|"
    r"endpoint|migracion|migration|test|hook|store)\b"
)
_VAGUE = re.compile(
    r"\b(?:mas\s+rapido|mejor|mejorar|optimizar|optimize|faster|cleaner|mas\s+lindo)\b"
)
_METRIC = re.compile(r"\d+\s*(?:ms|s|kb|mb|%|fps|px|segundos?)\b")
_NEGATIVE = re.compile(r"\b(?:no\s+uses?|no\s+hagas|no\s+toques|evita|don't\s+use|avoid)\b")
# Marcadores de enumeración. Sin grupo de captura: se cuentan con findall, no con split.
# El punto y coma queda deliberadamente afuera: un snippet de código lo usa todo el tiempo.
_TASK_SEPARATOR = re.compile(r"\b(?:y\s+ademas|y\s+tambien|and\s+also)\b")
_SHOUTED_WORD = re.compile(r"\b[A-Z]{4,}\b")
_EMPHASIS_WORD = re.compile(r"\b(?:CRITICAL|MUST|NEVER|SIEMPRE|NUNCA|IMPORTANTE|OBLIGATORIO)\b")
# Siglas técnicas que no son énfasis. Se comparan ya en mayúsculas.
_KNOWN_ACRONYMS = frozenset(
    {
        "JSON", "HTTP", "HTTPS", "REST", "YAML", "HTML", "CSS", "SCSS", "SQL", "CRUD",
        "README", "CLAUDE", "AGENTS", "TODO", "API", "CLI", "GUI", "UUID", "JWT", "RLS",
        "CI", "CD", "MCP", "LLM", "SEO", "SSR", "CSV", "XML", "PDF", "PNG", "SVG",
    }
)
# Dos palabras gritadas desconocidas: una sola suele ser un identificador del dominio.
_MIN_SHOUTED_WORDS = 2
# Un solo marcador ya delata la enumeración. Exigir dos lo volvía inalcanzable:
# solo hay tres marcadores y nadie escribe "y además" dos veces en un pedido.
_MIN_TASK_SEPARATORS = 1


class MissingSuccessCriteria(Rule):
    id = "missing_success_criteria"
    family = Family.TEXT
    severity = Severity.ERROR

    def check(self, ctx: CheckContext) -> Finding | None:
        if ctx.request.success_criteria:
            return None
        return self._finding(
            "No declaraste cuándo la tarea está terminada.",
            "Agregá qué tiene que pasar para considerarla lista: un test que pasa, "
            "algo que se ve en pantalla, un número que baja.",
        )


class DanglingReference(Rule):
    id = "dangling_reference"
    family = Family.TEXT
    severity = Severity.ERROR

    def check(self, ctx: CheckContext) -> Finding | None:
        text = strip_accents(ctx.request.text.lower())
        if not _DANGLING.search(text) or _CONCRETE.search(text):
            return None
        return self._finding(
            'Usaste una referencia sin antecedente ("arreglalo", "que ande").',
            "Nombrá la cosa concreta: qué archivo, qué componente, qué comportamiento.",
        )


class VagueQuantifier(Rule):
    id = "vague_quantifier"
    family = Family.TEXT
    severity = Severity.WARNING

    def check(self, ctx: CheckContext) -> Finding | None:
        text = strip_accents(ctx.request.text.lower())
        if not _VAGUE.search(text) or _METRIC.search(text):
            return None
        return self._finding(
            'Pediste algo "mejor" o "más rápido" sin decir cómo se mide.',
            "Poné el número: de cuánto a cuánto, o contra qué se compara.",
        )


class NegativeInstruction(Rule):
    """Detecta instrucciones en negativo y sugiere la formulación positiva.

    Es F3 del spec: "decile qué hacer, no qué no hacer".
    """

    id = "negative_instruction"
    family = Family.TEXT
    severity = Severity.INFO

    def check(self, ctx: CheckContext) -> Finding | None:
        if not _NEGATIVE.search(strip_accents(ctx.request.text.lower())):
            return None
        return self._finding(
            "Hay instrucciones en negativo. Los modelos siguen mejor las positivas.",
            'Reformulá: en vez de "no uses X", escribí "usá Y".',
        )


class MultipleUnrelatedTasks(Rule):
    id = "multiple_unrelated_tasks"
    family = Family.TEXT
    severity = Severity.WARNING

    def check(self, ctx: CheckContext) -> Finding | None:
        text = strip_accents(ctx.request.text.lower())
        if len(_TASK_SEPARATOR.findall(text)) < _MIN_TASK_SEPARATORS:
            return None
        return self._finding(
            "Parece haber varias tareas sin relación en un mismo pedido.",
            "Separalas en briefs distintos: es la causa número uno de resultados a medias.",
        )


class OverEmphasis(Rule):
    """Detecta lenguaje agresivo: mayúsculas sostenidas, CRITICAL/MUST/NUNCA repetidos.

    Es F5 del spec: ese lenguaje hace sobre-disparar a los modelos actuales.
    """

    id = "over_emphasis"
    family = Family.TEXT
    severity = Severity.INFO

    def check(self, ctx: CheckContext) -> Finding | None:
        text = ctx.request.text
        shouted = [word for word in _SHOUTED_WORD.findall(text) if word not in _KNOWN_ACRONYMS]
        if len(shouted) < _MIN_SHOUTED_WORDS and not _EMPHASIS_WORD.search(text):
            return None
        return self._finding(
            "Hay énfasis de más (mayúsculas sostenidas, CRITICAL/SIEMPRE/NUNCA).",
            "Bajá el tono: los modelos actuales sobre-disparan con lenguaje agresivo, "
            "así que una instrucción normal rinde más.",
        )


TEXT_RULES: tuple[Rule, ...] = (
    MissingSuccessCriteria(),
    DanglingReference(),
    VagueQuantifier(),
    NegativeInstruction(),
    MultipleUnrelatedTasks(),
    OverEmphasis(),
)
