# PromptBrief Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir la librería Python que convierte una descripción informal en un brief XML estructurado, inyectando contexto destilado del proyecto dentro de un presupuesto de atención.

**Architecture:** `src/promptbrief/core/` es una librería pura sin I/O de red ni HTTP. Cada familia de reglas expone una tupla explícita; un selector recorta el contexto del perfil al presupuesto distinguiendo *no aplicable* de *no entró*; un renderer rutea cada slot a su sección según su `kind`. `cli.py` es la primera capa fina encima — la segunda (FastAPI) llega en el Plan 2.

**Tech Stack:** Python 3.11+ (3.13 en la máquina), pytest, ruff, PyYAML, Typer, GitHub Actions.

> **Versión 3 (2026-08-03).** Dos rondas de auditoría de cinco frentes cada una. La ronda 2
> corrió `pytest` y `ruff` de verdad y encontró que la v2 **no compilaba la suite**: faltaban
> los `__init__.py` de `tests/`, había una colisión de basename, cuatro tests fallaban contra
> su propia implementación (tres de ellos rotos por los arreglos de la ronda 1) y `ruff` tiraba
> seis errores. Todo eso está corregido acá. Los arreglos de la ronda 1 introdujeron cuatro de
> los siete bloqueantes de la ronda 2: cada cambio se verifica, no se asume.

## Global Constraints

- Python 3.11+ declarado y **probado en CI contra 3.11 y 3.13**. Un floor que no se prueba no existe.
- **`core/` no importa nada de `cli.py` ni de un futuro `server/`**, y no sabe que existe HTTP.
- **Los IDs de regla son contrato público.** Hay un test que los congela contra el §6 del spec.
- El **andamiaje** del brief es inglés y estable; el contenido del usuario y del repo pasa verbatim (D2 del spec). Los mensajes de las reglas van en español.
- **Cero llamadas a IA.** Ninguna dependencia de red en `core/`.
- El brief **nunca** incluye una sección `<role>`.
- Presupuesto por defecto: **1500 tokens**, estimado por caracteres, contando el envoltorio XML.
- El brief lleva **rutas** de archivo, nunca contenido pegado.
- Las secciones vacías **no se emiten**.
- Toda excepción que `core/` levanta por culpa del input hereda de `PromptBriefError`. Lo que no herede de ahí es un bug interno.
- Los commits llevan únicamente a Franco Leone. **Sin trailer `Co-Authored-By`.**

## Estándares de código

El repo es una pieza de portfolio: se lee antes de ejecutarse.

- **Sin estado global mutable.** Las colecciones de reglas son tuplas explícitas.
- **Datos inmutables.** Todos los modelos son `@dataclass(frozen=True)` con campos tupla. Hay un test que lo recorre y lo verifica.
- **Tipado completo**, con `from __future__ import annotations`.
- **`ruff check .` limpio**, incluyendo `tests/`. Es parte del CI y del badge.
- **Una sola fuente de verdad.** Nada de dos definiciones del mismo contrato, ni de derivar una de la otra con cirugía de strings.
- **Sin código inalcanzable.** Si una regla no puede dispararse en el pipeline real, se borra o se rediseña.
- **Los tests prueban comportamiento**, y el caso "no dispara" tiene que ejercitar *la guarda*, no salirse antes por otra condición. Si borrás la guarda y el test sigue verde, el test no sirve.
- **Sin `except` mudos.** El motivo va en un comentario.
- **Sin trucos**: nada de walrus en comprehensions, ni de constantes cuyo valor dependa de un detalle no obvio de la stdlib.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `src/promptbrief/core/models.py` | Enums, `Slot`, `Profile`, `BriefRequest`, `Selection`, `Finding`, `Brief` |
| `src/promptbrief/core/errors.py` | Jerarquía de excepciones propias |
| `src/promptbrief/core/text.py` | Acentos, tokenización, redacción de credenciales |
| `src/promptbrief/core/budget.py` | Estimación de tokens y selección de slots |
| `src/promptbrief/core/tasks.py` | Los tres tipos de tarea y qué exige cada uno |
| `src/promptbrief/core/classify.py` | Detección del tipo de tarea |
| `src/promptbrief/core/rules/base.py` | Clase `Rule` y ejecutor |
| `src/promptbrief/core/rules/{text,completeness,context}.py` | Familias A, B y C |
| `src/promptbrief/core/profile/sources.py` | Descubrimiento, lectura acotada y hash |
| `src/promptbrief/core/profile/distill.py` | Markdown y `package.json` → slots |
| `src/promptbrief/core/profile/store.py` | Persistencia YAML validada |
| `src/promptbrief/core/render.py` | Plantilla XML, ruteo por `kind` |
| `src/promptbrief/core/build.py` | `lint()` y `build_brief()` |
| `src/promptbrief/cli.py` | Comandos `pbrief` |
| `tests/__init__.py`, `tests/rules/__init__.py`, `tests/profile/__init__.py` | **Obligatorios.** Sin ellos los imports relativos entre tests fallan y pytest aborta la colección entera |
| `tests/conftest.py`, `tests/rules/conftest.py` | Helpers compartidos |

---

## Task 1: Scaffold, modelos, errores y utilidades de texto

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.github/workflows/ci.yml`
- Create: `src/promptbrief/__init__.py`, `src/promptbrief/core/__init__.py`, `src/promptbrief/core/models.py`, `src/promptbrief/core/errors.py`, `src/promptbrief/core/text.py`
- Create: `tests/__init__.py` (vacío)
- Test: `tests/test_models.py`, `tests/test_text.py`

**Interfaces:**
- Produces: `Severity`, `TaskType`, `SlotKind`, `Family`, `Provenance`, `Slot`, `SourceFile`, `Profile`, `BriefRequest`, `Selection`, `CheckContext`, `Finding`, `Brief`; `PromptBriefError` y subclases; `strip_accents`, `terms`, `redact_secrets`

- [ ] **Step 1: Crear el scaffold**

`pyproject.toml`:

```toml
[project]
name = "promptbrief"
version = "0.1.0"
description = "Turns informal descriptions into structured briefs for coding agents"
requires-python = ">=3.11"
dependencies = ["pyyaml>=6.0", "typer>=0.12"]

[project.scripts]
pbrief = "promptbrief.cli:app"

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.ruff.lint.isort]
known-first-party = ["promptbrief"]

[tool.ruff.lint.per-file-ignores]
# Typer declara las opciones como llamadas en los defaults: es su API, no un descuido.
"src/promptbrief/cli.py" = ["B008"]
```

`.gitignore`:

```
__pycache__/
*.egg-info/
.pytest_cache/
.ruff_cache/
.venv/
dist/
```

**Crear `tests/__init__.py` vacío ahora.** No es opcional: sin él, `from .conftest import ...` en los tests de las tareas siguientes tira `ImportError: attempted relative import with no known parent package` y pytest **aborta la colección de toda la suite**, no solo de ese archivo. Además evita la colisión de basename entre `tests/test_text.py` (esta tarea) y `tests/rules/test_text.py` (Task 4), que sin paquetes se pisan mutuamente.

- [ ] **Step 2: Escribir los tests que fallan**

`tests/test_models.py`:

```python
import dataclasses

import pytest

from promptbrief.core import models
from promptbrief.core.models import (
    Brief,
    BriefRequest,
    CheckContext,
    Family,
    Finding,
    Profile,
    Provenance,
    Selection,
    Severity,
    Slot,
    SlotKind,
    SourceFile,
    TaskType,
)

MODEL_CLASSES = (
    Provenance, Slot, SourceFile, Profile, BriefRequest, Selection, CheckContext, Finding, Brief,
)


def test_every_model_is_frozen_and_free_of_mutable_defaults():
    for cls in MODEL_CLASSES:
        assert cls.__dataclass_params__.frozen, cls.__name__
        for field in dataclasses.fields(cls):
            assert not isinstance(field.default, (list, dict, set)), f"{cls.__name__}.{field.name}"


def test_every_model_class_in_the_module_is_covered_by_this_test():
    declared = {
        obj
        for obj in vars(models).values()
        if dataclasses.is_dataclass(obj) and obj.__module__ == models.__name__
    }
    assert declared == set(MODEL_CLASSES)


def test_a_slot_cannot_be_mutated_after_creation():
    slot = Slot(
        id="claude-convention-a1b2c3d4",
        kind=SlotKind.CONVENTION,
        content="Static export via output 'export'",
        applies_to=(TaskType.CODE_CHANGE,),
        source=Provenance(file="CLAUDE.md", line=12),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        slot.content = "tampered"


def test_slot_carries_provenance_and_safe_defaults():
    slot = Slot(
        id="claude-convention-a1b2c3d4",
        kind=SlotKind.CONVENTION,
        content="Static export",
        applies_to=(TaskType.CODE_CHANGE, TaskType.DEBUG),
        source=Provenance(file="CLAUDE.md", line=12),
    )
    assert slot.source.line == 12
    assert slot.needs_review is False
    assert slot.redacted is False


def test_profile_defaults_to_1500_token_budget():
    assert Profile(name="demo", root="/tmp/demo", slots=(), sources=()).budget_tokens == 1500


def test_brief_request_defaults_are_empty_tuples_not_none():
    req = BriefRequest(text="add a section", task_type=TaskType.CODE_CHANGE)
    assert req.profile is None
    assert (req.file_scope, req.constraints, req.examples) == ((), (), ())
    assert req.success_criteria is None


def test_selection_separates_the_reasons_a_slot_can_be_left_out():
    selection = Selection()
    assert selection.selected == ()
    assert selection.over_budget == ()
    assert selection.not_applicable == ()
    assert selection.skipped_for_review == ()


def test_check_context_defaults_to_an_empty_selection():
    ctx = CheckContext(request=BriefRequest(text="x", task_type=TaskType.DEBUG))
    assert ctx.selection.selected == ()
    assert ctx.stale_sources == ()


def test_finding_and_brief_shapes():
    finding = Finding(
        rule_id="missing_success_criteria",
        family=Family.TEXT,
        severity=Severity.ERROR,
        message="No declaraste cuándo la tarea está terminada.",
        suggestion="Agregá qué tiene que pasar para considerarla lista.",
    )
    brief = Brief(text="<task>x</task>", findings=(finding,))
    assert brief.findings[0].family == Family.TEXT
    assert brief.dropped_slots == ()
    assert brief.selection.selected == ()
    assert SourceFile(path="CLAUDE.md", sha256="abc").sha256 == "abc"
```

`tests/test_text.py`:

```python
from promptbrief.core.text import redact_secrets, strip_accents, terms


def test_strip_accents_folds_spanish_diacritics():
    assert strip_accents("sección configuración diseño") == "seccion configuracion diseno"


def test_accented_and_unaccented_spellings_produce_the_same_terms():
    assert terms("mejorar la sección") == terms("mejorar la seccion")


def test_terms_keeps_short_technical_tokens():
    assert {"css", "api", "seo"} <= terms("ajustar el CSS del API y el SEO")


def test_terms_drops_tokens_shorter_than_three_characters():
    assert "de" not in terms("el patron de la seccion")


def test_redact_secrets_hides_the_value_and_keeps_the_context():
    text = "Deploy key: STRIPE_KEY=sk_test_EXAMPLEKEYNOTAREALVALUE"
    redacted, found = redact_secrets(text)
    assert found is True
    assert "sk_test_EXAMPLEKEYNOTAREALVALUE" not in redacted
    assert "[REDACTED]" in redacted
    assert "STRIPE_KEY" in redacted


def test_the_labelled_pattern_keeps_the_label_and_drops_the_value():
    # Ejercita la rama del lambda con grupo de captura, que ningún otro patrón usa.
    redacted, found = redact_secrets("API_KEY=abcdefghijklmnop1234")
    assert found is True
    assert redacted == "API_KEY=[REDACTED]"


def test_redact_secrets_catches_common_token_shapes():
    for secret in (
        "ghp_16C7e42F292c6912E7710c838347Ae178B4a",
        "AKIAIOSFODNN7EXAMPLE",
        "xoxb-EXAMPLE-NOT-A-REAL-VALUE",
    ):
        redacted, found = redact_secrets(f"token: {secret}")
        assert found is True, secret
        assert secret not in redacted


def test_redact_secrets_catches_a_connection_string_password():
    redacted, found = redact_secrets("DATABASE_URL=postgres://user:S3cr3tPass@host/db")
    assert found is True
    assert "S3cr3tPass" not in redacted


def test_redact_secrets_catches_a_private_key_block():
    text = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAAB\n"
        "-----END OPENSSH PRIVATE KEY-----"
    )
    redacted, found = redact_secrets(text)
    assert found is True
    assert "b3BlbnNzaC1rZXktdjEA" not in redacted


def test_redact_secrets_leaves_ordinary_prose_alone():
    text = "Usar next.config.ts con output export y images.unoptimized"
    redacted, found = redact_secrets(text)
    assert found is False
    assert redacted == text
```

- [ ] **Step 3: Verificar que fallan**

Run: `python -m pytest tests/ -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'promptbrief'`

- [ ] **Step 4: Implementar errores y modelos**

`src/promptbrief/core/errors.py`:

```python
from __future__ import annotations


class PromptBriefError(Exception):
    """Base de todo error causado por el input, no por un bug interno.

    Un consumidor HTTP puede mapear esta jerarquía completa a 4xx y dejar que
    cualquier otra excepción caiga a 500, que es el comportamiento seguro.
    """


class EmptyRequestError(PromptBriefError):
    """No se puede armar un brief sin una descripción de la tarea."""


class InvalidProfileName(PromptBriefError):
    """El nombre de perfil no sirve como nombre de archivo de forma segura."""


class ProfileNotFound(PromptBriefError):
    """No existe un perfil con ese nombre."""


class ProfileCorrupt(PromptBriefError):
    """El YAML del perfil existe pero no tiene la forma esperada."""
```

`src/promptbrief/core/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Family(StrEnum):
    """Familia de la regla, según el §6 del spec."""

    TEXT = "text"
    COMPLETENESS = "completeness"
    CONTEXT = "context"


class TaskType(StrEnum):
    CODE_CHANGE = "code_change"
    DEBUG = "debug"
    WRITING = "writing"


class SlotKind(StrEnum):
    """Qué clase de dato es un slot. Decide su tag y su sección al renderizar."""

    STACK = "stack"
    CONVENTION = "convention"
    CONSTRAINT = "constraint"
    GLOSSARY = "glossary"
    ARCHITECTURE = "architecture"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class Provenance:
    file: str
    line: int

    def label(self) -> str:
        """Etiqueta legible para mensajes de usuario: 'CLAUDE.md:12'."""
        return f"{self.file}:{self.line}"


@dataclass(frozen=True)
class Slot:
    """Un dato del proyecto, listo para inyectar (o descartar).

    `applies_to` vacío significa "aplica a todos los tipos de tarea", no "a ninguno"
    — la misma convención que usa `Rule.applies_to`.
    """

    id: str
    kind: SlotKind
    content: str
    applies_to: tuple[TaskType, ...]
    source: Provenance | None
    needs_review: bool = False
    redacted: bool = False

    def label(self) -> str:
        """Cómo nombrar este slot ante el usuario: la procedencia si la hay, si no el id."""
        return self.source.label() if self.source else self.id


@dataclass(frozen=True)
class SourceFile:
    path: str
    sha256: str


@dataclass(frozen=True)
class Profile:
    name: str
    root: str
    slots: tuple[Slot, ...]
    sources: tuple[SourceFile, ...]
    budget_tokens: int = 1500


@dataclass(frozen=True)
class BriefRequest:
    text: str
    task_type: TaskType
    profile: Profile | None = None
    success_criteria: str | None = None
    output_format: str | None = None
    file_scope: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    repro_steps: str | None = None
    expected_vs_actual: str | None = None


@dataclass(frozen=True)
class Selection:
    """Resultado de recortar el perfil al presupuesto.

    Los motivos de exclusión se reportan por separado a propósito: solo `over_budget`
    es un problema. `not_applicable` es el filtrado normal por tipo de tarea y
    `skipped_for_review` es lo que la destilación no pudo clasificar.
    """

    selected: tuple[Slot, ...] = ()
    over_budget: tuple[Slot, ...] = ()
    not_applicable: tuple[Slot, ...] = ()
    skipped_for_review: tuple[Slot, ...] = ()

    def all_slots(self) -> tuple[Slot, ...]:
        return (*self.selected, *self.over_budget, *self.not_applicable, *self.skipped_for_review)


@dataclass(frozen=True)
class CheckContext:
    request: BriefRequest
    selection: Selection = Selection()
    stale_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    rule_id: str
    family: Family
    severity: Severity
    message: str
    suggestion: str


@dataclass(frozen=True)
class Brief:
    text: str
    findings: tuple[Finding, ...] = ()
    dropped_slots: tuple[str, ...] = ()
    selection: Selection = Selection()
```

- [ ] **Step 5: Implementar las utilidades de texto**

`src/promptbrief/core/text.py`:

```python
from __future__ import annotations

import re
import unicodedata

_TERM = re.compile(r"[a-z0-9]{3,}")

# Patrones de credencial. El grupo 1, cuando existe, es la parte que se conserva:
# "API_KEY=" sigue siendo información útil una vez tapado el valor.
_SECRETS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"
    ),
    # Credenciales embebidas en una URL de conexión: postgres://user:pass@host
    re.compile(r"(\b\w+://[^\s:/@]+:)[^\s@]{6,}@"),
    re.compile(
        r"((?i:api[_-]?key|secret|token|password|passwd)\s*[:=]\s*)"
        r"['\"]?[A-Za-z0-9_\-/+=]{16,}['\"]?"
    ),
)


def strip_accents(text: str) -> str:
    """Quita tildes para que 'sección' y 'seccion' se traten como la misma palabra."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def terms(text: str) -> set[str]:
    """Tokeniza para comparar relevancia, ignorando tildes y mayúsculas."""
    return set(_TERM.findall(strip_accents(text.lower())))


def _mask(match: re.Match[str]) -> str:
    return f"{match.group(1)}[REDACTED]" if match.groups() else "[REDACTED]"


def redact_secrets(text: str) -> tuple[str, bool]:
    """Reemplaza credenciales por [REDACTED]. Devuelve (texto, se_encontró_algo)."""
    redacted = text
    for pattern in _SECRETS:
        redacted = pattern.sub(_mask, redacted)
    return redacted, redacted != text
```

- [ ] **Step 6: Verificar que pasan**

Run: `pip install -e ".[dev]"` y después `python -m pytest tests/ -v`
Expected: 19 passed

- [ ] **Step 7: Agregar CI y verificar el linter**

`.github/workflows/ci.yml`:

```yaml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -v
```

Run: `ruff check .`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git init
git add .
git commit -m "feat: package scaffold, core models, error hierarchy and text utilities"
```

---

## Task 2: Presupuesto de atención

**Files:**
- Create: `src/promptbrief/core/budget.py`, `tests/conftest.py`
- Test: `tests/test_budget.py`

**Interfaces:**
- Produces: `CHARS_PER_TOKEN`, `XML_OVERHEAD_TOKENS`, `estimate_tokens(text) -> int`, `slot_cost(slot) -> int`, `select_within_budget(slots, task_type, query, budget) -> Selection`

- [ ] **Step 1: Crear los helpers compartidos**

`tests/conftest.py`:

```python
from promptbrief.core.models import Provenance, Slot, SlotKind, TaskType

# Instancia a nivel de módulo, no una llamada en el default del parámetro:
# ruff marca B008 (function call in argument defaults) y el CI corre sobre tests/.
# Provenance es frozen, así que compartir la instancia no tiene riesgo.
_DEFAULT_SOURCE = Provenance(file="CLAUDE.md", line=1)


def make_slot(
    id_: str,
    content: str,
    *,
    kind: SlotKind = SlotKind.CONVENTION,
    applies: tuple[TaskType, ...] = (TaskType.CODE_CHANGE,),
    source: Provenance | None = _DEFAULT_SOURCE,
    needs_review: bool = False,
    redacted: bool = False,
) -> Slot:
    """Slot de prueba con defaults razonables. Compartido por toda la suite."""
    return Slot(
        id=id_,
        kind=kind,
        content=content,
        applies_to=applies,
        source=source,
        needs_review=needs_review,
        redacted=redacted,
    )
```

- [ ] **Step 2: Escribir el test que falla**

`tests/test_budget.py`:

```python
from promptbrief.core.budget import (
    XML_OVERHEAD_TOKENS,
    estimate_tokens,
    select_within_budget,
    slot_cost,
)
from promptbrief.core.models import TaskType

from .conftest import make_slot


def test_estimate_tokens_is_a_quarter_of_the_character_count():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 400) == 100


def test_slot_cost_includes_the_xml_wrapper():
    slot = make_slot("s", "a" * 400)
    assert slot_cost(slot) == 100 + XML_OVERHEAD_TOKENS


def test_slots_for_another_task_type_are_not_applicable_not_over_budget():
    slots = [
        make_slot("keep", "relevant", applies=(TaskType.CODE_CHANGE,)),
        make_slot("skip", "irrelevant", applies=(TaskType.WRITING,)),
    ]
    result = select_within_budget(slots, TaskType.CODE_CHANGE, "", 1500)
    assert [s.id for s in result.selected] == ["keep"]
    assert [s.id for s in result.not_applicable] == ["skip"]
    assert result.over_budget == ()


def test_empty_applies_to_means_every_task_type():
    result = select_within_budget(
        [make_slot("universal", "stack info", applies=())], TaskType.WRITING, "", 1500
    )
    assert [s.id for s in result.selected] == ["universal"]


def test_slots_needing_review_are_never_injected():
    slots = [make_slot("unsure", "algo que no se pudo clasificar", needs_review=True)]
    result = select_within_budget(slots, TaskType.CODE_CHANGE, "", 1500)
    assert result.selected == ()
    assert [s.id for s in result.skipped_for_review] == ["unsure"]


def test_slots_matching_the_query_are_ranked_first():
    slots = [
        make_slot("unrelated", "database migrations and locking"),
        make_slot("relevant", "portfolio cards render in a grid"),
    ]
    result = select_within_budget(slots, TaskType.CODE_CHANGE, "add portfolio cards", 1500)
    assert result.selected[0].id == "relevant"


def test_relevance_decides_which_slot_survives_a_tight_budget():
    filler = "palabra " * 100  # los dos slots miden casi lo mismo
    slots = [
        make_slot("unrelated", f"database migrations {filler}"),
        make_slot("relevant", f"portfolio cards {filler}"),
    ]
    # Presupuesto para uno solo. slot_cost incluye el overhead XML: calcularlo con
    # estimate_tokens a secas dejaría a los dos afuera.
    budget = slot_cost(slots[0])
    result = select_within_budget(slots, TaskType.CODE_CHANGE, "portfolio cards", budget)
    assert [s.id for s in result.selected] == ["relevant"]
    assert [s.id for s in result.over_budget] == ["unrelated"]


def test_an_accented_query_still_matches_an_unaccented_slot():
    slots = [
        make_slot("unrelated", "database migrations and locking"),
        make_slot("relevant", "la seccion de proyectos vive en portfolio.ts"),
    ]
    result = select_within_budget(slots, TaskType.CODE_CHANGE, "mejorar la sección", 1500)
    assert result.selected[0].id == "relevant"


def test_budget_cuts_the_tail_and_reports_it_as_over_budget():
    big = "x" * 4000
    slots = [make_slot("first", big), make_slot("second", big)]
    result = select_within_budget(slots, TaskType.CODE_CHANGE, "", 1500)
    assert [s.id for s in result.selected] == ["first"]
    assert [s.id for s in result.over_budget] == ["second"]


def test_a_single_slot_over_budget_is_dropped_not_truncated():
    result = select_within_budget([make_slot("huge", "x" * 8000)], TaskType.CODE_CHANGE, "", 1500)
    assert result.selected == ()
    assert [s.id for s in result.over_budget] == ["huge"]


def test_an_empty_slot_does_not_slip_in_for_free():
    result = select_within_budget([make_slot("empty", "")], TaskType.CODE_CHANGE, "", 0)
    assert result.selected == ()
```

- [ ] **Step 3: Verificar que falla**

Run: `python -m pytest tests/test_budget.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'promptbrief.core.budget'`

- [ ] **Step 4: Implementar**

`src/promptbrief/core/budget.py`:

```python
from __future__ import annotations

from collections.abc import Sequence

from promptbrief.core.models import Selection, Slot, TaskType
from promptbrief.core.text import terms

CHARS_PER_TOKEN = 4
# Cada slot cuesta además su envoltorio: <convention source="CLAUDE.md:12">…</convention>
XML_OVERHEAD_TOKENS = 12


def estimate_tokens(text: str) -> int:
    """Estimación por caracteres. Suficiente para presupuestar, sin tokenizador."""
    return len(text) // CHARS_PER_TOKEN


def slot_cost(slot: Slot) -> int:
    """Lo que cuesta inyectar un slot, envoltorio XML incluido."""
    return estimate_tokens(slot.content) + XML_OVERHEAD_TOKENS


def _relevance(slot: Slot, query_terms: set[str]) -> int:
    if not query_terms:
        return 0
    return len(terms(slot.content) & query_terms)


def select_within_budget(
    slots: Sequence[Slot],
    task_type: TaskType,
    query: str,
    budget: int,
) -> Selection:
    """Filtra, ordena por relevancia y corta en el presupuesto.

    Nunca trunca el contenido de un slot: entra entero o no entra. Los motivos de
    exclusión se devuelven por separado porque solo uno de ellos es un problema.
    """
    applicable: list[Slot] = []
    not_applicable: list[Slot] = []
    skipped_for_review: list[Slot] = []

    for slot in slots:
        if slot.needs_review:
            skipped_for_review.append(slot)
        elif slot.applies_to and task_type not in slot.applies_to:
            not_applicable.append(slot)
        else:
            applicable.append(slot)

    query_terms = terms(query)
    applicable.sort(key=lambda slot: _relevance(slot, query_terms), reverse=True)

    selected: list[Slot] = []
    over_budget: list[Slot] = []
    spent = 0
    for slot in applicable:
        cost = slot_cost(slot)
        if spent + cost <= budget:
            selected.append(slot)
            spent += cost
        else:
            over_budget.append(slot)

    return Selection(
        selected=tuple(selected),
        over_budget=tuple(over_budget),
        not_applicable=tuple(not_applicable),
        skipped_for_review=tuple(skipped_for_review),
    )
```

- [ ] **Step 5: Verificar que pasa**

Run: `python -m pytest tests/test_budget.py -v`
Expected: 11 passed

- [ ] **Step 6: Commit**

```bash
git add src/promptbrief/core/budget.py tests/test_budget.py tests/conftest.py
git commit -m "feat: attention budget separating not-applicable from over-budget"
```

---

## Task 3: Tipos de tarea y clasificador

**Files:**
- Create: `src/promptbrief/core/tasks.py`, `src/promptbrief/core/classify.py`
- Test: `tests/test_tasks.py`, `tests/test_classify.py`

**Interfaces:**
- Produces: `REQUIRED_SLOTS: Mapping[TaskType, frozenset[str]]`, `tasks_requiring(slot_name) -> tuple[TaskType, ...]`, `classify(text) -> TaskType`

- [ ] **Step 1: Escribir los tests que fallan**

`tests/test_tasks.py`:

```python
import pytest

from promptbrief.core.models import TaskType
from promptbrief.core.tasks import REQUIRED_SLOTS, tasks_requiring


def test_every_task_type_declares_its_required_slots():
    assert set(REQUIRED_SLOTS) == set(TaskType)


def test_success_criteria_is_required_everywhere():
    for required in REQUIRED_SLOTS.values():
        assert "success_criteria" in required


def test_debug_requires_repro_and_expected_vs_actual():
    assert {"repro_steps", "expected_vs_actual"} <= REQUIRED_SLOTS[TaskType.DEBUG]


def test_writing_requires_examples_and_does_not_require_file_scope():
    assert "examples" in REQUIRED_SLOTS[TaskType.WRITING]
    assert "file_scope" not in REQUIRED_SLOTS[TaskType.WRITING]


def test_tasks_requiring_inverts_the_mapping():
    assert set(tasks_requiring("file_scope")) == {TaskType.CODE_CHANGE, TaskType.DEBUG}
    assert tasks_requiring("examples") == (TaskType.WRITING,)
    assert tasks_requiring("nonexistent") == ()


def test_required_slots_cannot_be_mutated():
    with pytest.raises(TypeError):
        REQUIRED_SLOTS[TaskType.CODE_CHANGE] = frozenset()
```

`tests/test_classify.py`:

```python
import pytest

from promptbrief.core.classify import classify
from promptbrief.core.models import TaskType


@pytest.mark.parametrize(
    "text,expected",
    [
        ("quiero agregar una seccion nueva al portfolio", TaskType.CODE_CHANGE),
        ("add a dark mode toggle to the navbar", TaskType.CODE_CHANGE),
        ("el carrito tira error 500 cuando agrego un producto", TaskType.DEBUG),
        ("this test is failing and I don't know why", TaskType.DEBUG),
        ("escribir un post de linkedin sobre el sistema de inventario", TaskType.WRITING),
        ("draft the README for this repo", TaskType.WRITING),
        # Mixto: arreglar algo que se rompe al agregar es debug, no feature.
        ("arreglar el error que aparece al agregar un producto", TaskType.DEBUG),
    ],
)
def test_classify_detects_the_task_type(text, expected):
    assert classify(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "agregar un indice en postgres",       # "post" dentro de "postgres"
        "ajustar el padding del address bar",  # "add" dentro de "padding"/"address"
        "subir el limite a 1500 tokens",       # "500" dentro de "1500"
    ],
)
def test_signals_do_not_match_inside_longer_words(text):
    assert classify(text) == TaskType.CODE_CHANGE


def test_unrecognized_text_falls_back_to_code_change():
    assert classify("mmm no se") == TaskType.CODE_CHANGE
```

- [ ] **Step 2: Verificar que fallan**

Run: `python -m pytest tests/test_tasks.py tests/test_classify.py -v`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Implementar**

`src/promptbrief/core/tasks.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from promptbrief.core.models import TaskType

# Única fuente de verdad sobre qué exige cada tipo de tarea. Las reglas de la
# familia B derivan su applies_to de acá en vez de repetirlo.
REQUIRED_SLOTS: Mapping[TaskType, frozenset[str]] = MappingProxyType(
    {
        TaskType.CODE_CHANGE: frozenset(
            {"success_criteria", "output_format", "file_scope", "constraints"}
        ),
        TaskType.DEBUG: frozenset(
            {
                "success_criteria",
                "output_format",
                "file_scope",
                "repro_steps",
                "expected_vs_actual",
            }
        ),
        TaskType.WRITING: frozenset({"success_criteria", "output_format", "examples"}),
    }
)


def tasks_requiring(slot_name: str) -> tuple[TaskType, ...]:
    """Tipos de tarea que exigen ese slot. Vacío si ninguno lo exige."""
    return tuple(task for task, required in REQUIRED_SLOTS.items() if slot_name in required)
```

`src/promptbrief/core/classify.py`:

```python
from __future__ import annotations

import re

from promptbrief.core.models import TaskType
from promptbrief.core.text import strip_accents

_SIGNALS: dict[TaskType, tuple[str, ...]] = {
    TaskType.DEBUG: (
        "error", "errores", "falla", "fallando", "rompe", "roto", "bug", "bugs",
        "excepcion", "crash", "crashea", "failing", "fails", "broken", "traceback",
        "no anda", "no funciona", "stack trace",
    ),
    TaskType.WRITING: (
        "post", "posteo", "linkedin", "readme", "documentar", "documentacion",
        "redactar", "escribir", "escribi", "draft", "article", "blog", "changelog",
    ),
    TaskType.CODE_CHANGE: (
        "agregar", "agrega", "crear", "crea", "implementar", "modificar", "refactor",
        "add", "create", "implement", "build", "update", "rename", "migrate",
    ),
}

# El orden importa: debug gana sobre code_change cuando aparecen señales de ambos,
# porque "arreglar el error al agregar un producto" es un debug, no un feature.
_PRIORITY = (TaskType.DEBUG, TaskType.WRITING, TaskType.CODE_CHANGE)


def _matcher(signals: tuple[str, ...]) -> re.Pattern[str]:
    # \b en los bordes: "post" no debe matchear dentro de "postgres",
    # ni "add" dentro de "padding".
    return re.compile(r"\b(?:" + "|".join(re.escape(s) for s in signals) + r")\b")


_MATCHERS: dict[TaskType, re.Pattern[str]] = {
    task: _matcher(signals) for task, signals in _SIGNALS.items()
}


def classify(text: str) -> TaskType:
    """Detecta el tipo de tarea. Ante la duda devuelve CODE_CHANGE."""
    normalized = strip_accents(text.lower())
    for task_type in _PRIORITY:
        if _MATCHERS[task_type].search(normalized):
            return task_type
    return TaskType.CODE_CHANGE
```

- [ ] **Step 4: Verificar que pasan**

Run: `python -m pytest tests/test_tasks.py tests/test_classify.py -v`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/core/tasks.py src/promptbrief/core/classify.py tests/test_tasks.py tests/test_classify.py
git commit -m "feat: task requirements as single source of truth and word-anchored classifier"
```

---

## Task 4: Ejecutor de reglas y familia A (texto)

**Files:**
- Create: `src/promptbrief/core/rules/__init__.py`, `src/promptbrief/core/rules/base.py`, `src/promptbrief/core/rules/text.py`
- Create: `tests/rules/__init__.py` (vacío), `tests/rules/conftest.py`
- Test: `tests/rules/test_text.py`

**Interfaces:**
- Produces: `Rule`, `run_rules(ctx, rules) -> tuple[Finding, ...]`, `TEXT_RULES: tuple[Rule, ...]`

- [ ] **Step 1: Crear el paquete de tests y su helper**

**Crear `tests/rules/__init__.py` vacío.** Sin él, `from ..conftest import make_slot` tira `ImportError: attempted relative import beyond top-level package`.

`tests/rules/conftest.py` — un solo helper para las tres familias:

```python
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
```

- [ ] **Step 2: Escribir el test que falla**

`tests/rules/test_text.py`:

```python
from promptbrief.core.models import Severity
from promptbrief.core.rules.text import TEXT_RULES

from .conftest import fired


def text_findings(text: str, **kwargs) -> dict[str, Severity]:
    return fired(TEXT_RULES, text=text, **kwargs)


def test_missing_success_criteria_fires_when_absent():
    assert "missing_success_criteria" in text_findings("agregar una seccion de python")


def test_missing_success_criteria_silent_when_provided():
    assert "missing_success_criteria" not in text_findings(
        "agregar una seccion", success_criteria="se ve igual que game dev"
    )


def test_dangling_reference_fires_on_a_pronoun_with_no_antecedent():
    assert "dangling_reference" in text_findings("arreglalo por favor")
    assert "dangling_reference" in text_findings("hace que ande")


def test_dangling_reference_silent_when_the_same_text_names_something_concrete():
    # Dispara _DANGLING ("arreglalo") y aun así calla por la guarda de antecedente.
    # Si se borra la guarda, este test falla.
    assert "dangling_reference" not in text_findings(
        "arreglalo, me refiero al componente de filtros"
    )


def test_vague_quantifier_fires_without_a_metric():
    assert "vague_quantifier" in text_findings("hacer que cargue mas rapido")


def test_vague_quantifier_silent_when_the_same_text_carries_a_metric():
    assert "vague_quantifier" not in text_findings(
        "hacer que cargue mas rapido: de 800ms a 200ms"
    )


def test_negative_instruction_is_info_severity():
    result = text_findings("agregar la seccion, no uses tailwind")
    assert result["negative_instruction"] == Severity.INFO


def test_negative_instruction_silent_on_positive_phrasing():
    assert "negative_instruction" not in text_findings("agregar la seccion usando css modules")


def test_multiple_unrelated_tasks_fires_on_an_enumeration():
    assert "multiple_unrelated_tasks" in text_findings(
        "agregar la seccion de python, arreglar el favicon y ademas escribir el readme"
    )


def test_multiple_unrelated_tasks_silent_on_a_single_semicolon():
    # Un punto y coma no es un marcador de enumeración: un snippet de código
    # ("const x = 1; const y = 2") no puede disparar la regla.
    assert "multiple_unrelated_tasks" not in text_findings(
        "agregar la seccion; seguir el patron existente"
    )


def test_over_emphasis_fires_on_shouting():
    assert "over_emphasis" in text_findings("ES MUY IMPORTANTE que uses TypeScript SIEMPRE")


def test_over_emphasis_silent_on_technical_acronyms():
    assert "over_emphasis" not in text_findings("actualizar README y CLAUDE.md con la convencion")
    assert "over_emphasis" not in text_findings("devolver JSON sobre HTTP usando REST")


def test_over_emphasis_silent_on_a_single_unknown_shouted_word():
    # Ejercita el umbral _MIN_SHOUTED_WORDS, no la lista de siglas.
    assert "over_emphasis" not in text_findings("revisar el TOOLTIP de la tabla")
```

- [ ] **Step 3: Verificar que falla**

Run: `python -m pytest tests/rules/test_text.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'promptbrief.core.rules'`

- [ ] **Step 4: Implementar el ejecutor**

`src/promptbrief/core/rules/base.py`:

```python
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
```

`src/promptbrief/core/rules/__init__.py` — versión de esta tarea; crece en las Tareas 5 y 6:

```python
from promptbrief.core.rules.base import Rule, run_rules
from promptbrief.core.rules.text import TEXT_RULES

ALL_RULES: tuple[Rule, ...] = TEXT_RULES

__all__ = ["ALL_RULES", "TEXT_RULES", "Rule", "run_rules"]
```

- [ ] **Step 5: Implementar la familia A**

`src/promptbrief/core/rules/text.py`:

```python
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
```

- [ ] **Step 6: Verificar que pasa**

Run: `python -m pytest tests/rules/test_text.py -v`
Expected: 13 passed

- [ ] **Step 7: Commit**

```bash
git add src/promptbrief/core/rules tests/rules
git commit -m "feat: rule executor and family A text-defect rules"
```

---

## Task 5: Familia B (completitud)

**Files:**
- Create: `src/promptbrief/core/rules/completeness.py`
- Modify: `src/promptbrief/core/rules/__init__.py`
- Test: `tests/rules/test_completeness.py`

**Interfaces:**
- Produces: `COMPLETENESS_RULES: tuple[Rule, ...]`; cada regla expone `slot_name: str`

Cada regla declara **explícitamente** qué slot vigila y deriva su `applies_to` con `tasks_requiring(slot_name)`. El `slot_name` es un atributo propio, no se infiere del `id`: `missing_repro` vigila `repro_steps`, así que derivarlo con `removeprefix` daba un nombre que no existe en `REQUIRED_SLOTS`.

- [ ] **Step 1: Escribir el test que falla**

`tests/rules/test_completeness.py`:

```python
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
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/rules/test_completeness.py -v`
Expected: FAIL con `ModuleNotFoundError: ... rules.completeness`

- [ ] **Step 3: Implementar**

`src/promptbrief/core/rules/completeness.py`:

```python
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
    MissingOutputFormat(),
    MissingFileScope(),
    MissingConstraints(),
    MissingExamples(),
    MissingRepro(),
    MissingExpectedVsActual(),
)
```

Actualizar `src/promptbrief/core/rules/__init__.py` para sumar `COMPLETENESS_RULES` a `ALL_RULES`.

- [ ] **Step 4: Verificar que pasa**

Run: `python -m pytest tests/rules/ -v`
Expected: 26 passed (13 de Task 4 + 13 nuevos)

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/core/rules/completeness.py src/promptbrief/core/rules/__init__.py tests/rules/test_completeness.py
git commit -m "feat: family B completeness rules derived from task requirements"
```

---

## Task 6: Familia C (salud del contexto) y contrato de IDs

**Files:**
- Create: `src/promptbrief/core/rules/context.py`
- Modify: `src/promptbrief/core/rules/__init__.py`
- Test: `tests/rules/test_context.py`, `tests/rules/test_registry.py`

**Interfaces:**
- Produces: `CONTEXT_RULES: tuple[Rule, ...]`, `ALL_RULES: tuple[Rule, ...]`

Los mensajes de esta familia nombran los slots por **procedencia** (`CLAUDE.md:12`), no por id: el id lleva un hash y no le dice nada al usuario.

- [ ] **Step 1: Escribir los tests que fallan**

`tests/rules/test_context.py`:

```python
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
```

`tests/rules/test_registry.py`:

```python
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
```

- [ ] **Step 2: Verificar que fallan**

Run: `python -m pytest tests/rules/ -v`
Expected: FAIL con `ModuleNotFoundError: ... rules.context`

- [ ] **Step 3: Implementar**

`src/promptbrief/core/rules/context.py`:

```python
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
```

`src/promptbrief/core/rules/__init__.py` — versión final:

```python
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
```

- [ ] **Step 4: Verificar que pasan**

Run: `python -m pytest tests/rules/ -v`
Expected: 61 passed (26 previos + 16 de contexto + 2 de registro + 17 del parametrize por regla)

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/core/rules/context.py src/promptbrief/core/rules/__init__.py tests/rules/test_context.py tests/rules/test_registry.py
git commit -m "feat: family C context-health rules and public rule-id contract test"
```

---

## Task 7: Lectura segura de fuentes

**Files:**
- Create: `src/promptbrief/core/profile/__init__.py`, `src/promptbrief/core/profile/sources.py`
- Create: `tests/profile/__init__.py` (vacío)
- Test: `tests/profile/test_sources.py`

**Interfaces:**
- Produces: `SOURCE_PRIORITY`, `MAX_SOURCE_BYTES`, `discover_sources(root)`, `read_source(path) -> str | None`, `hash_file(path)`, `stale_sources(profile, root)`

- [ ] **Step 1: Escribir el test que falla**

**Crear `tests/profile/__init__.py` vacío** antes de nada.

`tests/profile/test_sources.py`:

```python
import sys

import pytest

from promptbrief.core.models import Profile, SourceFile
from promptbrief.core.profile.sources import (
    MAX_SOURCE_BYTES,
    discover_sources,
    hash_file,
    read_source,
    stale_sources,
)


def test_discover_finds_all_four_known_sources_in_priority_order(tmp_path):
    for name in ("README.md", "package.json", "AGENTS.md", "CLAUDE.md"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    names = [path.name for path in discover_sources(tmp_path)]
    assert names == ["CLAUDE.md", "AGENTS.md", "README.md", "package.json"]


def test_discover_ignores_unknown_files(tmp_path):
    (tmp_path / "NOTES.md").write_text("nope", encoding="utf-8")
    assert discover_sources(tmp_path) == []


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin on Windows")
def test_discover_refuses_to_follow_a_symlink(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("id_rsa contents", encoding="utf-8")
    (tmp_path / "CLAUDE.md").symlink_to(secret)
    assert discover_sources(tmp_path) == []


def test_read_source_strips_a_utf8_bom(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_bytes(b"\xef\xbb\xbf# Titulo\n")
    assert read_source(path).startswith("# Titulo")


def test_read_source_returns_none_for_undecodable_bytes(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_bytes(b"\xff\xfe\x00\x01 binario")
    assert read_source(path) is None


def test_read_source_returns_none_for_an_oversized_file(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_bytes(b"x" * (MAX_SOURCE_BYTES + 1))
    assert read_source(path) is None


def test_read_source_accepts_a_file_exactly_at_the_limit(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_bytes(b"x" * MAX_SOURCE_BYTES)
    assert read_source(path) is not None


def test_hash_is_stable_and_changes_with_content(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text("original", encoding="utf-8")
    first = hash_file(path)
    assert hash_file(path) == first
    path.write_text("changed", encoding="utf-8")
    assert hash_file(path) != first


def test_stale_sources_reports_only_what_changed(tmp_path):
    claude = tmp_path / "CLAUDE.md"
    readme = tmp_path / "README.md"
    claude.write_text("a", encoding="utf-8")
    readme.write_text("b", encoding="utf-8")
    profile = Profile(
        name="demo",
        root=str(tmp_path),
        slots=(),
        sources=(
            SourceFile(path="CLAUDE.md", sha256=hash_file(claude)),
            SourceFile(path="README.md", sha256=hash_file(readme)),
        ),
    )
    assert stale_sources(profile, tmp_path) == []
    claude.write_text("modified", encoding="utf-8")
    assert stale_sources(profile, tmp_path) == ["CLAUDE.md"]


def test_a_deleted_source_counts_as_stale(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text("a", encoding="utf-8")
    profile = Profile(
        name="demo",
        root=str(tmp_path),
        slots=(),
        sources=(SourceFile(path="CLAUDE.md", sha256=hash_file(path)),),
    )
    path.unlink()
    assert stale_sources(profile, tmp_path) == ["CLAUDE.md"]
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/profile/test_sources.py -v`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Implementar**

`src/promptbrief/core/profile/sources.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from promptbrief.core.models import Profile

SOURCE_PRIORITY: tuple[str, ...] = ("CLAUDE.md", "AGENTS.md", "README.md", "package.json")
MAX_SOURCE_BYTES = 1_000_000


def discover_sources(root: Path) -> list[Path]:
    """Fuentes conocidas presentes en `root`, en orden de prioridad.

    Los symlinks se ignoran a propósito: un CLAUDE.md que apunta a ~/.ssh/id_rsa
    se leería y se destilaría igual.
    """
    return [
        root / name
        for name in SOURCE_PRIORITY
        if (root / name).is_file() and not (root / name).is_symlink()
    ]


def read_source(path: Path) -> str | None:
    """Lee una fuente acotada. Devuelve None si excede el límite o no decodifica.

    Lee en una sola operación con tope en vez de consultar el tamaño y después leer:
    entre las dos llamadas el archivo puede cambiar, y el chequeo no protegería nada.
    Devolver None en lugar de propagar la excepción también es deliberado: un archivo
    ilegible no puede abortar el scan de todo el proyecto.
    """
    with path.open("rb") as handle:
        data = handle.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        return None
    try:
        # utf-8-sig descarta el BOM que dejan Notepad y otras herramientas de Windows.
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stale_sources(profile: Profile, root: Path) -> list[str]:
    """Fuentes cuyo contenido cambió (o que desaparecieron) desde la destilación."""
    changed: list[str] = []
    for source in profile.sources:
        path = root / source.path
        if not path.is_file() or hash_file(path) != source.sha256:
            changed.append(source.path)
    return changed
```

Crear `src/promptbrief/core/profile/__init__.py` vacío.

- [ ] **Step 4: Verificar que pasa**

Run: `python -m pytest tests/profile/test_sources.py -v`
Expected: 10 passed (9 en Windows: se saltea el de symlinks)

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/core/profile tests/profile
git commit -m "feat: source discovery with symlink, size and encoding guards"
```

---

## Task 8: Destilación

**Files:**
- Create: `src/promptbrief/core/profile/distill.py`
- Test: `tests/profile/test_distill.py`, `tests/profile/fixtures/sample_claude.md`

**Interfaces:**
- Produces: `MAX_SLOTS_PER_SOURCE`, `distill_markdown(text, path)`, `distill_package_json(text, path)`, `distill_project(root, name=None) -> Profile`

- [ ] **Step 1: Crear el fixture**

`tests/profile/fixtures/sample_claude.md`:

````markdown
# PersonalPage

Portfolio personal en Next.js.

## Convenciones

- Static export: `next.config.ts` usa `output: "export"` con `images.unoptimized`
- Las imagenes se sirven tal cual se commitean

## Prohibido

- No modificar `next.config.ts`
- Do not add new runtime dependencies

## Glosario

- **gameSystems**: el array de sistemas de gameplay en `src/data/portfolio.ts`

## Convenciones y restricciones

- No tocar la carpeta public/systems

## Deploy

```bash
- este bullet vive adentro de un bloque de codigo y no es un slot
```

## Notas sueltas

- STRIPE_KEY=sk_test_EXAMPLEKEYNOTAREALVALUE
````

- [ ] **Step 2: Escribir el test que falla**

`tests/profile/test_distill.py`:

```python
import json
from pathlib import Path

import pytest

from promptbrief.core.models import SlotKind, TaskType
from promptbrief.core.profile.distill import (
    MAX_SLOTS_PER_SOURCE,
    distill_markdown,
    distill_package_json,
    distill_project,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_claude.md"


@pytest.fixture
def sample_slots():
    return tuple(distill_markdown(FIXTURE.read_text(encoding="utf-8"), "CLAUDE.md"))


def by_kind(slots, kind):
    return [slot for slot in slots if slot.kind is kind]


def test_bullets_under_a_heading_become_slots_with_provenance(sample_slots):
    static = next(slot for slot in sample_slots if "output" in slot.content)
    assert static.kind is SlotKind.CONVENTION
    assert static.source.file == "CLAUDE.md"
    assert static.source.line > 0


def test_spanish_prohibitions_are_rewritten_positively_in_spanish(sample_slots):
    slot = next(
        s for s in by_kind(sample_slots, SlotKind.CONSTRAINT) if "next.config.ts" in s.content
    )
    assert not slot.content.lower().startswith("no ")
    assert "sin cambios" in slot.content.lower()


def test_english_prohibitions_are_rewritten_positively_in_english(sample_slots):
    slot = next(
        s for s in by_kind(sample_slots, SlotKind.CONSTRAINT) if "dependencies" in s.content
    )
    assert not slot.content.lower().startswith("do not")
    assert "without" in slot.content.lower()


def test_a_prohibition_under_an_ambiguous_heading_is_still_a_constraint(sample_slots):
    # "## Convenciones y restricciones" contiene los dos tokens; además el bullet
    # empieza con "No tocar". La reformulación tiene que ganarle al heading.
    slot = next(s for s in sample_slots if "public/systems" in s.content)
    assert slot.kind is SlotKind.CONSTRAINT
    assert "sin cambios" in slot.content.lower()


def test_glossary_entries_do_not_apply_to_writing_tasks(sample_slots):
    glossary = by_kind(sample_slots, SlotKind.GLOSSARY)
    assert glossary
    assert all(TaskType.WRITING not in slot.applies_to for slot in glossary)


def test_bullets_inside_a_fenced_code_block_are_ignored(sample_slots):
    assert not any("adentro de un bloque" in slot.content for slot in sample_slots)


def test_bullets_after_a_closed_fence_are_still_read(sample_slots):
    # Prueba que el fence se cierra: el bullet de "## Notas sueltas" viene después.
    assert any("STRIPE_KEY" in slot.content for slot in sample_slots)


def test_a_credential_is_redacted_and_flagged(sample_slots):
    slot = next(s for s in sample_slots if "STRIPE_KEY" in s.content)
    assert slot.redacted is True
    assert "sk_test_EXAMPLEKEYNOTAREALVALUE" not in slot.content
    assert "[REDACTED]" in slot.content


def test_unrecognized_headings_yield_slots_marked_for_review():
    slots = distill_markdown("## Notas\n\n- algo que no encaja\n", "CLAUDE.md")
    assert slots
    assert all(slot.needs_review for slot in slots)
    assert all(slot.kind is SlotKind.UNCLASSIFIED for slot in slots)


def test_slot_ids_are_stable_across_reruns_and_insertions():
    first = distill_markdown("## Convenciones\n\n- usar pnpm\n", "CLAUDE.md")
    with_prefix = distill_markdown(
        "## Convenciones\n\n- bullet nuevo arriba\n- usar pnpm\n", "CLAUDE.md"
    )
    assert first[0].id in {slot.id for slot in with_prefix}


def test_a_source_with_too_many_bullets_is_truncated():
    text = "## Convenciones\n\n" + "".join(f"- regla {i}\n" for i in range(MAX_SLOTS_PER_SOURCE + 50))
    assert len(distill_markdown(text, "CLAUDE.md")) == MAX_SLOTS_PER_SOURCE


def test_package_json_yields_a_stack_slot_for_every_task_type():
    payload = json.dumps({"dependencies": {"next": "15.0.0", "react": "19.0.0"}})
    slots = distill_package_json(payload, "package.json")
    assert len(slots) == 1
    assert slots[0].kind is SlotKind.STACK
    assert "next" in slots[0].content
    assert slots[0].applies_to == ()


def test_a_token_in_a_git_dependency_url_is_redacted():
    payload = json.dumps(
        {
            "dependencies": {
                "privado": "git+https://ghp_16C7e42F292c6912E7710c838347Ae178B4a@github.com/o/r.git"
            }
        }
    )
    slots = distill_package_json(payload, "package.json")
    assert slots[0].redacted is True
    assert "ghp_16C7e42F292c6912E7710c838347Ae178B4a" not in slots[0].content


def test_package_json_that_is_not_an_object_is_ignored_without_crashing():
    assert distill_package_json("[]", "package.json") == []
    assert distill_package_json("null", "package.json") == []
    assert distill_package_json("not json at all", "package.json") == []


def test_distill_project_records_sources_and_keeps_ids_unique(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "README.md").write_text("## Notas\n\n- algo suelto\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"dependencies":{"next":"15.0.0"}}', encoding="utf-8")

    profile = distill_project(tmp_path, name="demo")

    assert profile.name == "demo"
    assert {source.path for source in profile.sources} == {
        "CLAUDE.md", "README.md", "package.json"
    }
    assert all(len(source.sha256) == 64 for source in profile.sources)
    ids = [slot.id for slot in profile.slots]
    assert len(ids) == len(set(ids)), "dos archivos no pueden producir el mismo id"


def test_an_unreadable_source_is_still_registered_so_staleness_can_watch_it(tmp_path):
    (tmp_path / "CLAUDE.md").write_bytes(b"\xff\xfe\x00\x01 binario")
    profile = distill_project(tmp_path, name="demo")
    assert [source.path for source in profile.sources] == ["CLAUDE.md"]
    assert profile.slots == ()


def test_distill_project_on_an_empty_directory_yields_an_empty_profile(tmp_path):
    profile = distill_project(tmp_path, name="empty")
    assert profile.slots == ()
    assert profile.sources == ()
```

- [ ] **Step 3: Verificar que falla**

Run: `python -m pytest tests/profile/test_distill.py -v`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 4: Implementar**

`src/promptbrief/core/profile/distill.py`:

```python
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from promptbrief.core.models import Profile, Provenance, Slot, SlotKind, SourceFile, TaskType
from promptbrief.core.profile.sources import discover_sources, hash_file, read_source
from promptbrief.core.text import redact_secrets, strip_accents

_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*]\s+(.+)$")
_FENCE = re.compile(r"^\s*```")

_DEV_TASKS: tuple[TaskType, ...] = (TaskType.CODE_CHANGE, TaskType.DEBUG)

# Techo por archivo. Sin esto, un markdown de un millón de bullets cortos produce
# un perfil que hay que recorrer entero en cada build_brief — justo el context rot
# que la herramienta existe para evitar.
MAX_SLOTS_PER_SOURCE = 500

# Token del heading (sin tildes, en minúscula) -> (kind, a qué tareas aplica).
_HEADING_KINDS: dict[str, tuple[SlotKind, tuple[TaskType, ...]]] = {
    "convencion": (SlotKind.CONVENTION, _DEV_TASKS),
    "convention": (SlotKind.CONVENTION, _DEV_TASKS),
    "prohibi": (SlotKind.CONSTRAINT, _DEV_TASKS),
    "forbidden": (SlotKind.CONSTRAINT, _DEV_TASKS),
    "restriccion": (SlotKind.CONSTRAINT, _DEV_TASKS),
    "constraint": (SlotKind.CONSTRAINT, _DEV_TASKS),
    "glosario": (SlotKind.GLOSSARY, _DEV_TASKS),
    "glossary": (SlotKind.GLOSSARY, _DEV_TASKS),
    "stack": (SlotKind.STACK, ()),
    "arquitectura": (SlotKind.ARCHITECTURE, _DEV_TASKS),
    "architecture": (SlotKind.ARCHITECTURE, _DEV_TASKS),
}

# Reformulación de negativo a positivo (F3), en el idioma de la fuente.
# Traducir sería inventar: el brief conserva el idioma del repo (ver D2 del spec).
_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"^no\s+(?:modificar|tocar|cambiar)\s+(?P<target>.+)$", re.I),
        "Mantener {target} sin cambios.",
    ),
    (re.compile(r"^no\s+agregar\s+(?P<target>.+)$", re.I), "Resolver sin agregar {target}."),
    (re.compile(r"^no\s+usar\s+(?P<target>.+)$", re.I), "Resolver sin usar {target}."),
    (
        re.compile(r"^(?:do not|don't|never)\s+(?:modify|touch|change)\s+(?P<target>.+)$", re.I),
        "Keep {target} unchanged.",
    ),
    (
        re.compile(r"^(?:do not|don't|never)\s+add\s+(?P<target>.+)$", re.I),
        "Solve it without adding {target}.",
    ),
    (
        re.compile(r"^(?:do not|don't|never)\s+use\s+(?P<target>.+)$", re.I),
        "Solve it without using {target}.",
    ),
)


def _classify_heading(heading: str) -> tuple[SlotKind, tuple[TaskType, ...]] | None:
    """Clasifica un heading por el token que aparece PRIMERO en el texto.

    Recorrer el diccionario y quedarse con el primer token que matchea haría que
    "Convenciones y restricciones" cayera en CONVENTION solo porque esa clave está
    antes en el dict, aunque el heading hable de restricciones.
    """
    key = strip_accents(heading.strip().lower())
    matches = [(key.index(token), value) for token, value in _HEADING_KINDS.items() if token in key]
    if not matches:
        return None
    return min(matches, key=lambda match: match[0])[1]


def _to_positive(text: str) -> str:
    """Reescribe una prohibición como instrucción positiva. Devuelve el original si no aplica."""
    stripped = text.strip()
    for pattern, template in _REWRITES:
        match = pattern.match(stripped)
        if match:
            return template.format(target=match.group("target").rstrip("."))
    return stripped


def _slot_id(source_path: str, kind: SlotKind, content: str) -> str:
    """ID estable: no depende de la posición del bullet en el archivo.

    Un contador posicional haría que agregar un bullet arriba renumere todo lo de
    abajo, y cada re-scan reportaría el perfil entero como cambiado.
    """
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    return f"{Path(source_path).stem.lower()}-{kind.value}-{digest}"


def distill_markdown(text: str, path: str) -> list[Slot]:
    """Extrae slots de un markdown.

    El heading da el `kind` por defecto, pero un bullet que se reescribe como
    prohibición se promueve a CONSTRAINT sin importar bajo qué heading esté.
    Lo que no se puede clasificar se marca `needs_review`, y eso implica que no
    se inyecta.
    """
    slots: list[Slot] = []
    heading_kind = SlotKind.UNCLASSIFIED
    heading_applies: tuple[TaskType, ...] = ()
    in_code_fence = False

    for lineno, line in enumerate(text.splitlines(), start=1):
        if _FENCE.match(line):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue

        heading = _HEADING.match(line)
        if heading:
            resolved = _classify_heading(heading.group(1))
            heading_kind, heading_applies = resolved or (SlotKind.UNCLASSIFIED, ())
            continue

        bullet = _BULLET.match(line)
        if not bullet:
            continue
        if len(slots) >= MAX_SLOTS_PER_SOURCE:
            break

        content = bullet.group(1).strip()
        kind, applies = heading_kind, heading_applies

        positive = _to_positive(content)
        if positive != content:
            content, kind, applies = positive, SlotKind.CONSTRAINT, _DEV_TASKS

        content, redacted = redact_secrets(content)
        slots.append(
            Slot(
                id=_slot_id(path, kind, content),
                kind=kind,
                content=content,
                applies_to=applies,
                source=Provenance(file=path, line=lineno),
                needs_review=kind is SlotKind.UNCLASSIFIED,
                redacted=redacted,
            )
        )
    return slots


def distill_package_json(text: str, path: str) -> list[Slot]:
    """Extrae un slot de stack a partir de las dependencias.

    Devuelve una lista vacía en silencio ante JSON roto, no-objeto o sin
    dependencias: ninguno de esos casos justifica abortar el scan del proyecto.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []

    dependencies = data.get("dependencies")
    if not isinstance(dependencies, dict) or not dependencies:
        return []

    listed = ", ".join(f"{name} {version}" for name, version in sorted(dependencies.items()))
    # Una dependencia privada puede traer un token en la URL: git+https://ghp_xxx@…
    content, redacted = redact_secrets(listed)
    return [
        Slot(
            id=_slot_id(path, SlotKind.STACK, content),
            kind=SlotKind.STACK,
            content=content,
            applies_to=(),
            source=Provenance(file=path, line=1),
            redacted=redacted,
        )
    ]


def distill_project(root: Path, name: str | None = None) -> Profile:
    """Destila todas las fuentes conocidas de `root` en un perfil.

    Una fuente ilegible se registra igual, aunque no aporte slots: si no quedara
    registrada, `stale_sources` nunca avisaría cuando cambie.
    """
    slots: list[Slot] = []
    sources: list[SourceFile] = []
    seen_ids: set[str] = set()

    for path in discover_sources(root):
        sources.append(SourceFile(path=path.name, sha256=hash_file(path)))

        text = read_source(path)
        if text is None:
            continue

        produced = (
            distill_package_json(text, path.name)
            if path.name == "package.json"
            else distill_markdown(text, path.name)
        )
        for slot in produced:
            if slot.id not in seen_ids:
                seen_ids.add(slot.id)
                slots.append(slot)

    return Profile(
        name=name or root.name,
        root=str(root),
        slots=tuple(slots),
        sources=tuple(sources),
    )
```

- [ ] **Step 5: Verificar que pasa**

Run: `python -m pytest tests/profile/ -v`
Expected: 27 passed (26 en Windows)

- [ ] **Step 6: Commit**

```bash
git add src/promptbrief/core/profile/distill.py tests/profile/test_distill.py tests/profile/fixtures/
git commit -m "feat: distill markdown into typed slots with stable ids and secret redaction"
```

---

## Task 9: Persistencia del perfil

**Files:**
- Create: `src/promptbrief/core/profile/store.py`
- Test: `tests/profile/test_store.py`

**Interfaces:**
- Produces: `profiles_dir()`, `save_profile(profile, directory=None) -> Path`, `load_profile(name, directory=None) -> Profile`, `list_profiles(directory=None) -> list[str]`

- [ ] **Step 1: Escribir el test que falla**

`tests/profile/test_store.py`:

```python
import pytest

from promptbrief.core.errors import InvalidProfileName, ProfileCorrupt, ProfileNotFound
from promptbrief.core.models import Profile, Provenance, Slot, SlotKind, SourceFile, TaskType
from promptbrief.core.profile.store import list_profiles, load_profile, profiles_dir, save_profile


def sample() -> Profile:
    return Profile(
        name="demo",
        root="/tmp/demo",
        slots=(
            Slot(
                id="claude-convention-a1b2c3d4",
                kind=SlotKind.CONVENTION,
                content="Static export via output 'export'",
                applies_to=(TaskType.CODE_CHANGE, TaskType.DEBUG),
                source=Provenance(file="CLAUDE.md", line=12),
            ),
            Slot(
                id="package-stack-e5f6a7b8",
                kind=SlotKind.STACK,
                content="Next.js 15",
                applies_to=(),
                source=None,
                redacted=True,
            ),
        ),
        sources=(SourceFile(path="CLAUDE.md", sha256="a" * 64),),
        budget_tokens=900,
    )


def test_round_trip_preserves_everything(tmp_path):
    save_profile(sample(), tmp_path)
    assert load_profile("demo", tmp_path) == sample()


def test_saved_file_is_human_editable_yaml(tmp_path):
    path = save_profile(sample(), tmp_path)
    text = path.read_text(encoding="utf-8")
    assert path.suffix == ".yml"
    assert "claude-convention-a1b2c3d4" in text
    assert "CLAUDE.md" in text


def test_a_hand_written_minimal_profile_loads(tmp_path):
    (tmp_path / "manual.yml").write_text(
        "name: manual\n"
        "root: /tmp/manual\n"
        "slots:\n"
        "  - id: mine-convention-1\n"
        "    kind: convention\n"
        "    content: Usar pnpm\n",
        encoding="utf-8",
    )
    profile = load_profile("manual", tmp_path)
    assert profile.budget_tokens == 1500
    assert profile.slots[0].applies_to == ()
    assert profile.slots[0].source is None
    assert profile.slots[0].needs_review is False


@pytest.mark.parametrize(
    "body",
    [
        "- soy una lista",
        "",
        "solo un string suelto",
        "name: x\nroot: /tmp\nslots: no soy una lista\n",
        "name: x\nroot: /tmp\nslots:\n  - id: a\n    kind: banana\n    content: c\n",
        "name: x\nroot: /tmp\nslots:\n  - kind: convention\n",
        "root: /tmp\n",
    ],
)
def test_a_malformed_profile_raises_profile_corrupt_not_a_traceback(tmp_path, body):
    (tmp_path / "broken.yml").write_text(body, encoding="utf-8")
    with pytest.raises(ProfileCorrupt):
        load_profile("broken", tmp_path)


def test_list_profiles_returns_sorted_names(tmp_path):
    save_profile(sample(), tmp_path)
    save_profile(Profile(name="alpha", root="/tmp/a", slots=(), sources=()), tmp_path)
    assert list_profiles(tmp_path) == ["alpha", "demo"]


def test_loading_a_missing_profile_raises_profile_not_found(tmp_path):
    with pytest.raises(ProfileNotFound):
        load_profile("nope", tmp_path)


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "..\\escape",
        "C:\\Windows\\evil",
        "/etc/passwd",
        "with space",
        "",
        "CON",
        "nul",
        "trailing\n",
    ],
)
def test_dangerous_profile_names_are_rejected_on_read_and_write(tmp_path, name):
    with pytest.raises(InvalidProfileName):
        load_profile(name, tmp_path)
    with pytest.raises(InvalidProfileName):
        save_profile(Profile(name=name, root="/tmp/x", slots=(), sources=()), tmp_path)


def test_a_rejected_name_never_creates_a_file_outside_the_directory(tmp_path):
    outside = tmp_path.parent / "escaped.yml"
    with pytest.raises(InvalidProfileName):
        save_profile(Profile(name="../escaped", root="/tmp/x", slots=(), sources=()), tmp_path)
    assert not outside.exists()


def test_profiles_dir_honours_the_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path))
    assert profiles_dir() == tmp_path / "projects"


def test_profiles_dir_defaults_to_the_documented_config_path(monkeypatch, tmp_path):
    monkeypatch.delenv("PROMPTBRIEF_HOME", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert profiles_dir() == tmp_path / ".config" / "promptbrief" / "projects"
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/profile/test_store.py -v`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Implementar**

`src/promptbrief/core/profile/store.py`:

```python
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from promptbrief.core.errors import InvalidProfileName, ProfileCorrupt, ProfileNotFound
from promptbrief.core.models import Profile, Provenance, Slot, SlotKind, SourceFile, TaskType

# fullmatch, no match: con `$` el motor acepta un \n final y dejaría pasar "perfil\n".
_SAFE_NAME = re.compile(r"[A-Za-z0-9._-]{1,64}")
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def profiles_dir() -> Path:
    """~/.config/promptbrief/projects, o PROMPTBRIEF_HOME/projects si está definido."""
    override = os.environ.get("PROMPTBRIEF_HOME")
    base = Path(override) if override else Path.home() / ".config" / "promptbrief"
    return base / "projects"


def _profile_path(name: str, directory: Path) -> Path:
    """Ruta del perfil, validando que el nombre no escape del directorio.

    Sin esto, un nombre con `..` escapa; y en Windows un nombre absoluto como
    `C:\\evil` hace que `directory / name` descarte `directory` por completo.
    """
    if not _SAFE_NAME.fullmatch(name) or name.upper() in _WINDOWS_RESERVED:
        raise InvalidProfileName(
            f"Nombre de perfil inválido: {name!r}. "
            "Se permiten letras, números, punto, guion y guion bajo (hasta 64)."
        )
    path = (directory / f"{name}.yml").resolve()
    if not path.is_relative_to(directory.resolve()):
        raise InvalidProfileName(f"Nombre de perfil inválido: {name!r}")
    return path


def _slot_to_dict(slot: Slot) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": slot.id,
        "kind": slot.kind.value,
        "content": slot.content,
        "applies_to": [task.value for task in slot.applies_to],
        "needs_review": slot.needs_review,
        "redacted": slot.redacted,
    }
    if slot.source is not None:
        data["source"] = {"file": slot.source.file, "line": slot.source.line}
    return data


def _slot_from_dict(data: dict[str, Any]) -> Slot:
    source = data.get("source")
    return Slot(
        id=data["id"],
        kind=SlotKind(data.get("kind", SlotKind.UNCLASSIFIED.value)),
        content=data["content"],
        applies_to=tuple(TaskType(task) for task in data.get("applies_to", [])),
        source=Provenance(file=source["file"], line=source["line"]) if source else None,
        needs_review=data.get("needs_review", False),
        redacted=data.get("redacted", False),
    )


def save_profile(profile: Profile, directory: Path | None = None) -> Path:
    """Persiste el perfil como YAML legible. Devuelve la ruta escrita."""
    target = directory or profiles_dir()
    path = _profile_path(profile.name, target)
    target.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": profile.name,
        "root": profile.root,
        "budget_tokens": profile.budget_tokens,
        "sources": [{"path": s.path, "sha256": s.sha256} for s in profile.sources],
        "slots": [_slot_to_dict(slot) for slot in profile.slots],
    }
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return path


def load_profile(name: str, directory: Path | None = None) -> Profile:
    """Carga un perfil del disco.

    El YAML se edita a mano por diseño, así que cualquier deformidad se traduce a
    ProfileCorrupt en vez de dejar escapar un KeyError o un ValueError crudo.
    """
    path = _profile_path(name, directory or profiles_dir())
    if not path.is_file():
        raise ProfileNotFound(f"No existe el perfil '{name}' en {path.parent}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ProfileCorrupt(f"El perfil '{name}' no es YAML válido: {error}") from error

    if not isinstance(data, dict):
        raise ProfileCorrupt(f"El perfil '{name}' no tiene un mapeo en la raíz.")

    raw_slots = data.get("slots", [])
    raw_sources = data.get("sources", [])
    if not isinstance(raw_slots, list) or not isinstance(raw_sources, list):
        raise ProfileCorrupt(f"En el perfil '{name}', 'slots' y 'sources' deben ser listas.")

    try:
        return Profile(
            name=data["name"],
            root=data["root"],
            slots=tuple(_slot_from_dict(slot) for slot in raw_slots),
            sources=tuple(
                SourceFile(path=s["path"], sha256=s["sha256"]) for s in raw_sources
            ),
            budget_tokens=data.get("budget_tokens", 1500),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ProfileCorrupt(f"El perfil '{name}' tiene un campo inválido: {error}") from error


def list_profiles(directory: Path | None = None) -> list[str]:
    """Nombres de los perfiles guardados, ordenados alfabéticamente."""
    target = directory or profiles_dir()
    if not target.is_dir():
        return []
    return sorted(path.stem for path in target.glob("*.yml"))
```

- [ ] **Step 4: Verificar que pasa**

Run: `python -m pytest tests/profile/ -v`
Expected: 51 passed (50 en Windows)

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/core/profile/store.py tests/profile/test_store.py
git commit -m "feat: YAML profile persistence with safe names and schema validation"
```

---

## Task 10: Renderer del brief

**Files:**
- Create: `src/promptbrief/core/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Produces: `render_brief(request, selected) -> str`

- [ ] **Step 1: Escribir el test que falla**

`tests/test_render.py`:

```python
from xml.etree import ElementTree

from promptbrief.core.models import BriefRequest, Provenance, SlotKind, TaskType
from promptbrief.core.render import render_brief

from .conftest import make_slot


def full_request(**overrides) -> BriefRequest:
    base = dict(
        text="Add a Python projects section",
        task_type=TaskType.CODE_CHANGE,
        success_criteria="Cards render like the Game Dev ones",
        output_format="Code changes with file paths",
        file_scope=("src/data/portfolio.ts", "src/components/GameDev.tsx"),
        constraints=("Keep next.config.ts unchanged",),
    )
    base.update(overrides)
    return BriefRequest(**base)


def test_sections_appear_in_the_documented_order():
    out = render_brief(full_request(), [make_slot("s", "Next.js 15", kind=SlotKind.STACK)])
    positions = [
        out.index("<project_context>"),
        out.index("<constraints>"),
        out.index("<task>"),
        out.index("<success_criteria>"),
        out.index("<output_format>"),
    ]
    assert positions == sorted(positions)


def test_each_slot_kind_becomes_its_own_tag():
    slots = [
        make_slot("s", "Next.js 15", kind=SlotKind.STACK),
        make_slot("c", "Static export enabled", kind=SlotKind.CONVENTION),
    ]
    out = render_brief(full_request(), slots)
    assert "<stack" in out
    assert "<convention" in out


def test_constraint_slots_land_in_constraints_not_in_project_context():
    slots = [make_slot("c", "Keep next.config.ts unchanged.", kind=SlotKind.CONSTRAINT)]
    out = render_brief(full_request(constraints=()), slots)
    constraints_block = out[out.index("<constraints>") : out.index("</constraints>")]
    assert "Keep next.config.ts unchanged." in constraints_block
    assert "Keep next.config.ts unchanged." not in out[: out.index("<constraints>")]


def test_provenance_is_emitted_as_a_double_quoted_attribute():
    slots = [make_slot("c", "Static export", source=Provenance(file="CLAUDE.md", line=12))]
    assert 'source="CLAUDE.md:12"' in render_brief(full_request(), slots)


def test_a_quote_in_a_filename_cannot_break_out_of_the_attribute():
    slots = [make_slot("c", "Static export", source=Provenance(file='we"ird.md', line=3))]
    out = render_brief(full_request(), slots)
    # El marcado sigue siendo parseable y el atributo round-trippea intacto.
    root = ElementTree.fromstring(f"<root>{out}</root>")
    assert root.find(".//convention").get("source") == 'we"ird.md:3'


def test_the_whole_brief_is_well_formed_xml():
    slots = [make_slot("c", "a < b && c > d", source=Provenance(file="CLAUDE.md", line=1))]
    out = render_brief(full_request(), slots)
    ElementTree.fromstring(f"<root>{out}</root>")


def test_file_scope_lists_paths_and_never_file_contents():
    out = render_brief(full_request(), [])
    assert "<relevant_paths>" in out
    assert "src/data/portfolio.ts" in out


def test_debug_sections_render_above_the_task():
    request = BriefRequest(
        text="the cart is empty after adding an item",
        task_type=TaskType.DEBUG,
        repro_steps="add an item, refresh",
        expected_vs_actual="expected the item, got an empty cart",
    )
    out = render_brief(request, [])
    assert out.index("<reproduction>") < out.index("<task>")
    assert out.index("<expected_vs_actual>") < out.index("<task>")


def test_empty_sections_are_omitted_entirely():
    out = render_brief(BriefRequest(text="do it", task_type=TaskType.CODE_CHANGE), [])
    for tag in ("<constraints>", "<success_criteria>", "<examples>", "<project_context>"):
        assert tag not in out
    assert "<task>" in out


def test_no_role_section_is_ever_emitted():
    out = render_brief(full_request(), [make_slot("s", "Next.js 15", kind=SlotKind.STACK)])
    assert "<role>" not in out


def test_examples_are_wrapped_individually():
    request = BriefRequest(
        text="write a post",
        task_type=TaskType.WRITING,
        examples=("first sample", "second sample"),
    )
    assert render_brief(request, []).count("<example>") == 2


def test_xml_special_characters_in_the_task_are_escaped():
    out = render_brief(BriefRequest(text="fix a < b && c > d", task_type=TaskType.CODE_CHANGE), [])
    assert "&lt;" in out and "&amp;" in out
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/test_render.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'promptbrief.core.render'`

- [ ] **Step 3: Implementar**

`src/promptbrief/core/render.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from xml.sax.saxutils import escape, quoteattr

from promptbrief.core.models import BriefRequest, Slot, SlotKind

_INDENT = "  "
# quoteattr cambia a comilla simple si el valor tiene una comilla doble. Forzar el
# escapado mantiene el atributo siempre con comillas dobles, como el §7 del spec.
_ATTR_ESCAPES = {'"': "&quot;"}


def _indent(text: str, level: int = 1) -> str:
    pad = _INDENT * level
    return "\n".join(f"{pad}{line}" if line.strip() else line for line in text.splitlines())


def _slot_element(slot: Slot) -> str:
    attr = ""
    if slot.source:
        attr = f" source={quoteattr(slot.source.label(), _ATTR_ESCAPES)}"
    tag = slot.kind.value
    return f"{_INDENT}<{tag}{attr}>{escape(slot.content)}</{tag}>"


def _project_context(slots: Sequence[Slot], paths: Sequence[str]) -> str:
    if not slots and not paths:
        return ""
    lines = ["<project_context>"]
    lines.extend(_slot_element(slot) for slot in slots)
    if paths:
        lines.append(f"{_INDENT}<relevant_paths>")
        lines.extend(f"{_INDENT * 2}{escape(path)}" for path in paths)
        lines.append(f"{_INDENT}</relevant_paths>")
    lines.append("</project_context>")
    return "\n".join(lines)


def _section(tag: str, body: str) -> str:
    if not body.strip():
        return ""
    return f"<{tag}>\n{_indent(escape(body.strip()))}\n</{tag}>"


def _examples(examples: Sequence[str]) -> str:
    if not examples:
        return ""
    blocks = [
        f"{_INDENT}<example>\n{_indent(escape(text.strip()), 2)}\n{_INDENT}</example>"
        for text in examples
    ]
    return "<examples>\n" + "\n".join(blocks) + "\n</examples>"


def render_brief(request: BriefRequest, selected: Sequence[Slot]) -> str:
    """Emite el brief. Contexto largo arriba, consulta abajo (F1 del spec).

    Las secciones vacías no se emiten. Nunca se emite <role>. Los slots de tipo
    CONSTRAINT van a <constraints>, no a <project_context>.
    """
    context_slots = [slot for slot in selected if slot.kind is not SlotKind.CONSTRAINT]
    inherited = [slot.content for slot in selected if slot.kind is SlotKind.CONSTRAINT]

    sections = [
        _project_context(context_slots, request.file_scope),
        _section("constraints", "\n".join([*inherited, *request.constraints])),
        _examples(request.examples),
        _section("reproduction", request.repro_steps or ""),
        _section("expected_vs_actual", request.expected_vs_actual or ""),
        _section("task", request.text),
        _section("success_criteria", request.success_criteria or ""),
        _section("output_format", request.output_format or ""),
    ]
    return "\n\n".join(section for section in sections if section)
```

- [ ] **Step 4: Verificar que pasa**

Run: `python -m pytest tests/test_render.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/core/render.py tests/test_render.py
git commit -m "feat: XML renderer routing slots by kind, with attribute-safe provenance"
```

---

## Task 11: Orquestación

**Files:**
- Create: `src/promptbrief/core/build.py`
- Test: `tests/test_build.py`

**Interfaces:**
- Produces: `resolve_profile(name) -> Profile`, `lint(request, root=None) -> tuple[Finding, ...]`, `build_brief(request, root=None) -> Brief`

`lint()` existe aparte para que el `POST /api/lint` del Plan 2 no tenga que renderizar un brief para tirarlo. `resolve_profile()` existe para que CLI y servidor compartan la resolución en vez de reimplementarla cada uno.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_build.py`:

```python
import pytest

from promptbrief.core.build import build_brief, lint
from promptbrief.core.errors import EmptyRequestError
from promptbrief.core.models import BriefRequest, Profile, Severity, SlotKind, SourceFile, TaskType
from promptbrief.core.profile.sources import hash_file

from .conftest import make_slot


def code_request(profile: Profile | None = None, **overrides) -> BriefRequest:
    base = dict(
        text="add a python section",
        task_type=TaskType.CODE_CHANGE,
        profile=profile,
        success_criteria="it renders",
        output_format="code",
        file_scope=("src/x.ts",),
        constraints=("keep config unchanged",),
    )
    base.update(overrides)
    return BriefRequest(**base)


def profile_with(*slots, **kwargs) -> Profile:
    return Profile(name="demo", root="/tmp", sources=(), slots=slots, **kwargs)


def test_applicable_slots_reach_the_brief_and_others_do_not():
    profile = profile_with(
        make_slot("keep", "Static export is enabled."),
        make_slot("skip", "Tone should be casual.", applies=(TaskType.WRITING,)),
    )
    brief = build_brief(code_request(profile))
    assert "Static export is enabled." in brief.text
    assert "Tone should be casual." not in brief.text


def test_filtering_by_task_type_is_not_reported_as_a_budget_problem():
    profile = profile_with(
        make_slot("keep", "Static export is enabled."),
        make_slot("skip", "Tone should be casual.", applies=(TaskType.WRITING,)),
    )
    brief = build_brief(code_request(profile))
    assert brief.dropped_slots == ()
    assert not any(f.rule_id == "budget_exceeded" for f in brief.findings)


def test_the_brief_exposes_the_full_selection_for_the_ui():
    profile = profile_with(
        make_slot("keep", "Static export is enabled."),
        make_slot("skip", "Tone should be casual.", applies=(TaskType.WRITING,)),
        make_slot("unsure", "algo raro", needs_review=True),
    )
    brief = build_brief(code_request(profile))
    assert [s.id for s in brief.selection.selected] == ["keep"]
    assert [s.id for s in brief.selection.not_applicable] == ["skip"]
    assert [s.id for s in brief.selection.skipped_for_review] == ["unsure"]


def test_slots_over_budget_are_reported_and_raise_the_budget_finding():
    profile = profile_with(
        make_slot("huge", "x" * 4000), make_slot("small", "Static export."), budget_tokens=100
    )
    brief = build_brief(code_request(profile))
    assert "huge" in brief.dropped_slots
    assert any(f.rule_id == "budget_exceeded" for f in brief.findings)


def test_constraints_inherited_from_the_profile_silence_the_completeness_rule():
    profile = profile_with(
        make_slot("c", "Keep next.config.ts unchanged.", kind=SlotKind.CONSTRAINT)
    )
    brief = build_brief(code_request(profile, constraints=()))
    assert "Keep next.config.ts unchanged." in brief.text
    assert not any(f.rule_id == "missing_constraints" for f in brief.findings)


def test_a_request_with_no_profile_still_produces_a_brief():
    brief = build_brief(BriefRequest(text="add a section", task_type=TaskType.CODE_CHANGE))
    assert "<task>" in brief.text
    assert any(f.rule_id == "missing_success_criteria" for f in brief.findings)


def test_a_debug_request_renders_its_sections_and_silences_its_rules():
    request = BriefRequest(
        text="the cart empties after adding an item",
        task_type=TaskType.DEBUG,
        success_criteria="the item stays in the cart",
        output_format="code",
        file_scope=("src/cart.ts",),
        repro_steps="add an item, refresh",
        expected_vs_actual="expected the item, got an empty cart",
    )
    brief = build_brief(request)
    assert "<reproduction>" in brief.text
    ids = {f.rule_id for f in brief.findings}
    assert "missing_repro" not in ids
    assert "missing_constraints" not in ids  # no aplica a debug


def test_stale_sources_surface_as_a_finding(tmp_path):
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("original", encoding="utf-8")
    profile = Profile(
        name="demo",
        root=str(tmp_path),
        slots=(),
        sources=(SourceFile(path="CLAUDE.md", sha256=hash_file(claude)),),
    )
    claude.write_text("changed", encoding="utf-8")
    brief = build_brief(code_request(profile), root=tmp_path)
    assert any(f.rule_id == "stale_profile" for f in brief.findings)


def test_findings_come_back_sorted_with_errors_first():
    brief = build_brief(BriefRequest(text="arreglalo", task_type=TaskType.CODE_CHANGE))
    order = [Severity.ERROR, Severity.WARNING, Severity.INFO]
    severities = [order.index(f.severity) for f in brief.findings]
    assert severities == sorted(severities)


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_an_empty_request_is_rejected_instead_of_producing_an_empty_brief(text):
    with pytest.raises(EmptyRequestError):
        build_brief(BriefRequest(text=text, task_type=TaskType.CODE_CHANGE))


def test_lint_returns_the_same_findings_without_rendering():
    request = BriefRequest(text="arreglalo", task_type=TaskType.CODE_CHANGE)
    assert lint(request) == build_brief(request).findings
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/test_build.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'promptbrief.core.build'`

- [ ] **Step 3: Implementar**

`src/promptbrief/core/build.py`:

```python
from __future__ import annotations

from pathlib import Path

from promptbrief.core.budget import select_within_budget
from promptbrief.core.errors import EmptyRequestError
from promptbrief.core.models import Brief, BriefRequest, CheckContext, Finding, Profile
from promptbrief.core.profile.sources import stale_sources
from promptbrief.core.profile.store import load_profile
from promptbrief.core.render import render_brief
from promptbrief.core.rules import ALL_RULES, run_rules


def resolve_profile(name: str) -> Profile:
    """Carga un perfil por nombre. Compartida por la CLI y el servidor del Plan 2.

    Levanta ProfileNotFound, InvalidProfileName o ProfileCorrupt — todas bajo
    PromptBriefError, así que un consumidor HTTP las mapea a 4xx de una.
    """
    return load_profile(name)


def _context(request: BriefRequest, root: Path | None) -> CheckContext:
    if not request.text.strip():
        raise EmptyRequestError("La descripción de la tarea está vacía.")

    profile = request.profile
    if profile is None:
        return CheckContext(request=request)

    selection = select_within_budget(
        profile.slots, request.task_type, request.text, profile.budget_tokens
    )
    target = root or Path(profile.root)
    stale = stale_sources(profile, target) if profile.sources and target.is_dir() else []
    return CheckContext(request=request, selection=selection, stale_sources=tuple(stale))


def lint(request: BriefRequest, root: Path | None = None) -> tuple[Finding, ...]:
    """Hallazgos sin renderizar el brief."""
    return run_rules(_context(request, root), ALL_RULES)


def build_brief(request: BriefRequest, root: Path | None = None) -> Brief:
    """Selecciona contexto, corre las reglas y renderiza. Punto de entrada del core."""
    ctx = _context(request, root)
    return Brief(
        text=render_brief(request, ctx.selection.selected),
        findings=run_rules(ctx, ALL_RULES),
        dropped_slots=tuple(slot.id for slot in ctx.selection.over_budget),
        selection=ctx.selection,
    )
```

- [ ] **Step 4: Verificar que pasa**

Run: `python -m pytest -v`
Expected: toda la suite en verde, 184 tests (183 en Windows)

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/core/build.py tests/test_build.py
git commit -m "feat: orchestrate selection, rules and rendering; expose lint and resolve_profile"
```

---

## Task 12: CLI y README

**Files:**
- Create: `src/promptbrief/cli.py`, `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `pbrief scan [PATH] [--name NAME] [--force]`, `pbrief profiles`, `pbrief lint TEXT`, `pbrief brief TEXT [--profile NAME]`

- [ ] **Step 1: Escribir el test que falla**

`tests/test_cli.py`:

```python
from typer.testing import CliRunner

from promptbrief.cli import app

runner = CliRunner()


def write_project(tmp_path, folder="proj"):
    project = tmp_path / folder
    project.mkdir()
    (project / "CLAUDE.md").write_text(
        "# Proj\n\n## Convenciones\n\n- Static export is enabled in next.config.ts\n",
        encoding="utf-8",
    )
    return project


def test_scan_creates_a_profile_and_lists_it(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    project = write_project(tmp_path)

    result = runner.invoke(app, ["scan", str(project)])
    assert result.exit_code == 0
    assert "proj" in result.stdout
    assert "proj" in runner.invoke(app, ["profiles"]).stdout


def test_scan_refuses_to_overwrite_without_force(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    project = write_project(tmp_path)
    runner.invoke(app, ["scan", str(project)])

    again = runner.invoke(app, ["scan", str(project)])
    assert again.exit_code == 1
    assert "--force" in again.stdout
    assert runner.invoke(app, ["scan", str(project), "--force"]).exit_code == 0


def test_scan_fails_on_a_directory_with_no_known_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    empty = tmp_path / "empty"
    empty.mkdir()
    assert runner.invoke(app, ["scan", str(empty)]).exit_code == 1


def test_a_folder_name_with_a_space_reports_cleanly_and_suggests_name(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    project = write_project(tmp_path, folder="Personal Page")
    result = runner.invoke(app, ["scan", str(project)])
    assert result.exit_code == 1
    assert "Traceback" not in result.stdout
    assert "--name" in result.stdout


def test_scan_accepts_an_explicit_name(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    project = write_project(tmp_path, folder="Personal Page")
    result = runner.invoke(app, ["scan", str(project), "--name", "personal-page"])
    assert result.exit_code == 0
    assert "personal-page" in runner.invoke(app, ["profiles"]).stdout


def test_lint_exits_nonzero_and_names_the_rule_on_an_error():
    result = runner.invoke(app, ["lint", "arreglalo"])
    assert result.exit_code == 1
    assert "dangling_reference" in result.stdout


def test_lint_exits_zero_when_there_are_only_warnings():
    result = runner.invoke(
        app, ["lint", "Add a Python section", "--success", "cards render", "--format", "code"]
    )
    assert result.exit_code == 0
    assert "missing_file_scope" in result.stdout


def test_brief_prints_the_rendered_xml():
    result = runner.invoke(
        app,
        [
            "brief", "Add a Python section",
            "--success", "cards render",
            "--format", "code changes",
            "--file", "src/data/portfolio.ts",
        ],
    )
    assert result.exit_code == 0
    assert "<task>" in result.stdout
    assert "<success_criteria>" in result.stdout


def test_an_unknown_profile_reports_cleanly_instead_of_a_traceback(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    result = runner.invoke(app, ["brief", "add a section", "--profile", "nope"])
    assert result.exit_code == 1
    assert "Traceback" not in result.stdout
    assert "nope" in result.stdout


def test_a_corrupt_profile_reports_cleanly(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "projects").mkdir(parents=True)
    (home / "projects" / "roto.yml").write_text("- soy una lista", encoding="utf-8")
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(home))

    result = runner.invoke(app, ["brief", "add a section", "--profile", "roto"])
    assert result.exit_code == 1
    assert "Traceback" not in result.stdout


def test_an_empty_request_reports_cleanly():
    result = runner.invoke(app, ["brief", "   "])
    assert result.exit_code == 1
    assert "Traceback" not in result.stdout
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'promptbrief.cli'`

- [ ] **Step 3: Implementar**

`src/promptbrief/cli.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

import typer

from promptbrief.core.build import build_brief, lint, resolve_profile
from promptbrief.core.classify import classify
from promptbrief.core.errors import PromptBriefError
from promptbrief.core.models import BriefRequest, Finding, Severity
from promptbrief.core.profile.distill import distill_project
from promptbrief.core.profile.store import list_profiles, save_profile

app = typer.Typer(help="Turns informal descriptions into structured briefs for coding agents.")

_MARK = {Severity.ERROR: "[error]", Severity.WARNING: "[warn ]", Severity.INFO: "[info ]"}


def _fail(message: str) -> NoReturn:
    """Imprime el error y termina con código 1. Es terminal: se llama sin `raise`."""
    typer.echo(message)
    raise typer.Exit(code=1)


def _build_request(
    text: str,
    profile_name: str | None,
    success: str | None,
    output_format: str | None,
    files: list[str],
) -> BriefRequest:
    profile = None
    if profile_name:
        try:
            profile = resolve_profile(profile_name)
        except PromptBriefError as error:
            _fail(f"{error} Corré 'pbrief profiles' para ver los perfiles disponibles.")
    return BriefRequest(
        text=text,
        task_type=classify(text),
        profile=profile,
        success_criteria=success,
        output_format=output_format,
        file_scope=tuple(files),
    )


def _print_findings(findings: Sequence[Finding]) -> bool:
    """Imprime los hallazgos. Devuelve True si alguno es un error."""
    for finding in findings:
        typer.echo(f"{_MARK[finding.severity]} {finding.rule_id}: {finding.message}")
        typer.echo(f"         -> {finding.suggestion}")
    return any(finding.severity is Severity.ERROR for finding in findings)


@app.command()
def scan(
    path: str = typer.Argument(".", help="Directorio del proyecto"),
    name: str = typer.Option(None, "--name", help="Nombre del perfil (por defecto, la carpeta)"),
    force: bool = typer.Option(False, "--force", help="Sobrescribir un perfil existente"),
) -> None:
    """Destila CLAUDE.md, AGENTS.md, README.md y package.json en un perfil."""
    root = Path(path).resolve()
    if not root.is_dir():
        _fail(f"No existe el directorio {root}")

    profile = distill_project(root, name=name)
    if not profile.sources:
        _fail(f"No encontré CLAUDE.md, AGENTS.md, README.md ni package.json en {root}")
    if profile.name in list_profiles() and not force:
        _fail(
            f"Ya existe el perfil '{profile.name}'. Usá --force para sobrescribirlo "
            "(vas a perder las ediciones manuales del YAML)."
        )

    try:
        saved = save_profile(profile)
    except PromptBriefError as error:
        _fail(f"{error} Usá --name para elegir un nombre de perfil válido.")

    typer.echo(f"Perfil '{profile.name}' guardado en {saved}")
    typer.echo(f"  {len(profile.slots)} datos desde {len(profile.sources)} archivos")

    needs_review = [slot.label() for slot in profile.slots if slot.needs_review]
    if needs_review:
        typer.echo(f"  {len(needs_review)} sin clasificar: no se inyectan hasta revisarlos")
    redacted = [slot.label() for slot in profile.slots if slot.redacted]
    if redacted:
        typer.echo(f"  credenciales tapadas en: {', '.join(redacted)}")


@app.command()
def profiles() -> None:
    """Lista los perfiles guardados."""
    names = list_profiles()
    if not names:
        typer.echo("No hay perfiles todavía. Corré 'pbrief scan' dentro de un proyecto.")
        return
    for profile_name in names:
        typer.echo(profile_name)


@app.command(name="lint")
def lint_command(
    text: str,
    success: str = typer.Option(None, "--success"),
    output_format: str = typer.Option(None, "--format"),
    file: list[str] = typer.Option([], "--file"),
) -> None:
    """Analiza un prompt sin generar el brief."""
    request = _build_request(text, None, success, output_format, file)
    try:
        findings = lint(request)
    except PromptBriefError as error:
        _fail(str(error))

    if not findings:
        typer.echo("Sin hallazgos.")
        return
    if _print_findings(findings):
        raise typer.Exit(code=1)


@app.command()
def brief(
    text: str,
    profile: str = typer.Option(None, "--profile"),
    success: str = typer.Option(None, "--success"),
    output_format: str = typer.Option(None, "--format"),
    file: list[str] = typer.Option([], "--file"),
) -> None:
    """Genera el brief y lo imprime."""
    request = _build_request(text, profile, success, output_format, file)
    try:
        result = build_brief(request)
    except PromptBriefError as error:
        _fail(str(error))

    typer.echo(result.text)
    if result.findings:
        typer.echo("\n---")
        _print_findings(result.findings)


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Verificar que pasa**

Run: `python -m pytest -v` y después `ruff check .`
Expected: 195 tests en verde (194 en Windows) y `All checks passed!`

- [ ] **Step 5: Escribir el README**

En inglés, cubriendo:

- **Qué hace**, en dos frases, con una entrada y una salida reales copiadas de una corrida.
- **"How it differs"** — los linters de prompts analizan el texto del prompt; PromptBrief lee el proyecto. Nombrar `prompt-control-plane`. **No afirmar novedad.**
- **"Why these rules"** — la tabla F1–F8 del spec con link a la documentación de prompt engineering de Anthropic y al artículo de context engineering.
- **"Design decisions"** — no se emite `<role>`; el brief lleva rutas y no contenido pegado; el contexto tiene un presupuesto de atención y se informa qué quedó afuera y por qué motivo.
- **"Security"** — redacción de credenciales, nombres de perfil validados, symlinks no seguidos, límite de tamaño.
- Instalación, los cuatro comandos, y cómo correr los tests.

- [ ] **Step 6: Commit**

```bash
git add src/promptbrief/cli.py tests/test_cli.py README.md
git commit -m "feat: pbrief CLI with scan, profiles, lint and brief commands"
```

- [ ] **Step 7: Publicar el repo**

Confirmar con Franco antes de ejecutar — es público e irreversible.

```bash
gh repo create promptbrief --public --source=. --remote=origin --push
```

---

## Verificación final

- [ ] `pytest -v` en verde, 195 tests (194 en Windows por el skip de symlinks)
- [ ] `ruff check .` sin hallazgos
- [ ] CI verde en GitHub, en 3.11 y en 3.13
- [ ] `core/` no importa la CLI: `grep -rn "promptbrief.cli" src/promptbrief/core/` no devuelve nada
- [ ] `pbrief scan C:\Franco\Proyectos\Web\PersonalPage` produce un perfil con datos reales de ese `CLAUDE.md`, reporta cuántos quedaron sin clasificar, y no tira ningún traceback
- [ ] `pbrief brief "agregar una seccion de python al portfolio" --profile PersonalPage` produce un brief usable
- [ ] Ningún commit contiene el trailer `Co-Authored-By`

---

## Después de este plan

**Plan 2 — `web`**: FastAPI sobre `core/` y el front Angular. Antes de escribirlo hay que resolver dos cosas que este plan deja abiertas a propósito:

1. **`diff_profiles(old, new)`** para el endpoint `sync`. Con IDs derivados del contenido, un bullet editado no es "mismo id, contenido nuevo" sino un id nuevo que reemplaza a uno viejo; reportar "qué cambió" de forma útil necesita reconciliar por `(archivo, kind)`. Esa lógica va en `core/`, no en `server/`.
2. **El contrato de seguridad del servidor**, que hoy el spec cubre a medias. Escuchar solo en loopback **no alcanza**: cualquier página abierta en el navegador puede hacer `fetch` a `127.0.0.1`. El servidor tiene que validar `Origin`, limitar el tamaño del body, y validar contra esquema todo lo que persista.

**v2 — el hook** de Claude Code, que reusa `lint()` sin tocar nada más.
