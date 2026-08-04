# PromptBrief Server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exponer el core de PromptBrief por HTTP en localhost, con el contrato de seguridad del §10 del spec, para que el front Angular tenga qué consumir.

**Architecture:** Cuatro tareas cierran huecos en `core/` (política de scan, trazabilidad de hallazgos a campos, serialización, diff). Las seis siguientes son la capa HTTP: seguridad primero, después los endpoints. `server/` es traducción HTTP y nada más: si un endpoint necesita decidir algo, esa decisión va a `core/`.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, pytest (con `TestClient`), ruff.

> **Versión 2 (2026-08-03).** La v1 se auditó antes de ejecutarse, con tres frentes que
> **reprodujeron los defectos ejecutando**, no leyendo. Encontraron seis hallazgos altos —
> incluida una lectura de archivos arbitrarios del disco vía `/api/brief`, un tope de body
> evadible con `Transfer-Encoding: chunked`, y una API que **no le alcanzaba al front Angular**
> para armar su formulario dinámico. Tres de esos seis cambian el diseño, así que el plan se
> reescribió entero en vez de parchearse.

## Global Constraints

- Python 3.11+, probado en CI contra 3.11 y 3.13.
- **`core/` sigue sin importar nada de `server/` ni de `cli.py`.**
- **`server/` no contiene lógica de negocio.** Valida el request, llama a una primitiva de `core/`, traduce el resultado y los errores.
- **`PromptBriefError` y subclases → 4xx. Cualquier otra excepción → 500.**
- **Toda ruta del disco que llegue de afuera pasa por la allowlist. Sin excepciones y en todos los endpoints que la toquen**, no solo en el que la recibe primero.
- **El token de sesión viaja en un header custom.** Nunca en la query string, salvo en la carga inicial del documento.
- `ruff check .` limpio, incluyendo `tests/`. `line-length = 100`.
- Tipado completo, con `from __future__ import annotations`.
- Los tests prueban comportamiento; el caso negativo ejercita la guarda. **Y existe al menos un caso mixto** por cada colección de guardas: la auditoría del core encontró que probar "todo bien" y "todo mal" deja el medio sin cubrir, que es donde viven los bugs.
- Los commits llevan únicamente a Franco Leone. **Sin trailer `Co-Authored-By`.**
- **No declares conteos de tests en los pasos.** Reportá el número real que salga.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `src/promptbrief/core/errors.py` | Se le suman `NoKnownSources`, `ProfileAlreadyExists`, `RootNotFound`, `StoredProfileCorrupt` |
| `src/promptbrief/core/profile/scan.py` | `scan_project()` — la política de escanear y guardar |
| `src/promptbrief/core/profile/serialize.py` | Serialización pública y validada del perfil |
| `src/promptbrief/core/profile/diff.py` | `ProfileDiff`, `diff_profiles()` |
| `src/promptbrief/server/security.py` | Token, `Host`, `Sec-Fetch-Site`, `Origin`, tope de body |
| `src/promptbrief/server/schemas.py` | Modelos Pydantic de borde |
| `src/promptbrief/server/errors.py` | Mapeo `PromptBriefError` → 4xx |
| `src/promptbrief/server/paths.py` | `checked_root()` — la allowlist de directorios |
| `src/promptbrief/server/app.py` | `create_app()` y las rutas |
| `tests/server/` | Un archivo por grupo |

---

## Task 1: Errores nuevos y `scan_project`

**Files:**
- Modify: `src/promptbrief/core/errors.py`, `src/promptbrief/core/profile/store.py`, `src/promptbrief/cli.py`
- Create: `src/promptbrief/core/profile/scan.py`
- Test: `tests/profile/test_scan.py`

**Interfaces:**
- Produces: `NoKnownSources`, `ProfileAlreadyExists`, `RootNotFound`, `validate_profile_name(name) -> None`, `scan_project(root, name=None, force=False) -> tuple[Profile, Path]`

**Dos correcciones de la auditoría respecto de la v1:**

1. **`RootNotFound` hereda de `PromptBriefError`.** La v1 usaba `NotADirectoryError` de la stdlib "porque es culpa del llamador, no del input". Eso funcionaba cuando el único llamador era la CLI, que validaba antes. Con el servidor deja de funcionar: por la regla global, cualquier cosa que no sea `PromptBriefError` cae a 500, así que un `root` inexistente daría un error de servidor cuando es claramente culpa del pedido.

2. **El nombre se valida ANTES de destilar.** La v1 dejaba que `save_profile` rechazara el nombre al final, después de leer y hashear todos los `.md` del repo. En la CLI era un desperdicio; en el servidor es I/O completo antes de devolver un 400. Además el test que lo cubría no probaba a `scan_project` sino a `save_profile`: pasaba igual si `scan_project` no existiera.

- [ ] **Step 1: Escribir el test que falla**

`tests/profile/test_scan.py`:

```python
import pytest

from promptbrief.core.errors import (
    InvalidProfileName,
    NoKnownSources,
    ProfileAlreadyExists,
    PromptBriefError,
    RootNotFound,
)
from promptbrief.core.profile.scan import scan_project


def write_project(tmp_path, folder="proj"):
    project = tmp_path / folder
    project.mkdir()
    (project / "CLAUDE.md").write_text(
        "# Proj\n\n## Convenciones\n\n- Static export is enabled\n", encoding="utf-8"
    )
    return project


def test_scan_distills_and_saves(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    profile, path = scan_project(write_project(tmp_path))
    assert profile.name == "proj"
    assert profile.slots
    assert path.is_file()


@pytest.mark.parametrize("error", [RootNotFound, NoKnownSources, ProfileAlreadyExists])
def test_every_rejection_is_a_promptbrief_error(error):
    # El servidor mapea la jerarquía entera a 4xx. Una excepción de la stdlib acá
    # se convertiría en un 500 por algo que es culpa del pedido.
    assert issubclass(error, PromptBriefError)


def test_a_missing_directory_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    with pytest.raises(RootNotFound):
        scan_project(tmp_path / "nope")


def test_a_file_instead_of_a_directory_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    target = tmp_path / "archivo.md"
    target.write_text("no soy un directorio", encoding="utf-8")
    with pytest.raises(RootNotFound):
        scan_project(target)


def test_a_directory_with_no_known_sources_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(NoKnownSources):
        scan_project(empty)


def test_an_existing_profile_is_not_overwritten_without_force(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    project = write_project(tmp_path)
    scan_project(project)

    with pytest.raises(ProfileAlreadyExists):
        scan_project(project)
    assert scan_project(project, force=True)[0].name == "proj"


def test_an_explicit_name_overrides_the_folder_name(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    project = write_project(tmp_path, folder="Personal Page")
    assert scan_project(project, name="personal-page")[0].name == "personal-page"


def test_a_bad_name_is_rejected_before_anything_is_read(tmp_path, monkeypatch):
    # La guarda es de scan_project, no de save_profile: tiene que disparar antes de
    # destilar. Si se borra, el error igual sale (más tarde y tras leer todo el repo),
    # así que el test mide el momento, no solo el tipo.
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    project = write_project(tmp_path, folder="Personal Page")

    called = []
    monkeypatch.setattr(
        "promptbrief.core.profile.scan.distill_project",
        lambda *a, **k: called.append(1),
    )
    with pytest.raises(InvalidProfileName):
        scan_project(project)
    assert called == [], "no se debe destilar nada si el nombre ya es inválido"


def test_an_explicit_bad_name_is_rejected_too(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    with pytest.raises(InvalidProfileName):
        scan_project(write_project(tmp_path), name="con espacio")
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/profile/test_scan.py -v`
Expected: FAIL con `ImportError: cannot import name 'RootNotFound'`

- [ ] **Step 3: Agregar las excepciones y exponer la validación de nombre**

En `core/errors.py`:

```python
class NoKnownSources(PromptBriefError):
    """El directorio no tiene ninguna de las fuentes que PromptBrief sabe leer."""


class ProfileAlreadyExists(PromptBriefError):
    """Ya hay un perfil con ese nombre y no se pidió sobrescribirlo."""


class RootNotFound(PromptBriefError):
    """El directorio del proyecto no existe o no es un directorio.

    Hereda de PromptBriefError a propósito: para un consumidor HTTP esto es culpa
    del pedido (4xx), no una falla del servidor.
    """


class StoredProfileCorrupt(ProfileCorrupt):
    """El perfil guardado en disco está deformado.

    Se distingue de ProfileCorrupt porque el cliente no lo mandó ni puede arreglarlo
    reenviando otra cosa: es integridad de datos del servidor, y va a 500.
    """
```

En `store.py`, extraer la validación del nombre a una función pública `validate_profile_name(name: str) -> None` que levante `InvalidProfileName`, y que `_profile_path` la use. Una sola implementación, dos llamadores.

- [ ] **Step 4: Implementar**

`src/promptbrief/core/profile/scan.py`:

```python
from __future__ import annotations

from pathlib import Path

from promptbrief.core.errors import NoKnownSources, ProfileAlreadyExists, RootNotFound
from promptbrief.core.models import Profile
from promptbrief.core.profile.distill import distill_project
from promptbrief.core.profile.store import (
    list_profiles,
    save_profile,
    validate_profile_name,
)


def scan_project(
    root: Path,
    name: str | None = None,
    force: bool = False,
) -> tuple[Profile, Path]:
    """Destila un directorio y guarda el perfil. Devuelve (perfil, ruta escrita).

    La política vive acá y no en la CLI porque el servidor la necesita igual: en la
    capa de presentación se duplicaría con reglas apenas distintas.

    El nombre se valida antes de destilar: leer y hashear todos los .md del repo para
    después rechazar por el nombre de la carpeta es trabajo tirado, y en el servidor
    es I/O completo antes de un 400.
    """
    if not root.is_dir():
        raise RootNotFound(f"No existe el directorio {root}")

    validate_profile_name(name if name is not None else root.name)

    profile = distill_project(root, name=name)
    if not profile.sources:
        raise NoKnownSources(
            f"No encontré CLAUDE.md, AGENTS.md, README.md ni package.json en {root}"
        )
    if profile.name in list_profiles() and not force:
        raise ProfileAlreadyExists(f"Ya existe el perfil '{profile.name}'.")

    return profile, save_profile(profile)
```

- [ ] **Step 5: Que la CLI lo use, conservando las sugerencias de flag**

`scan` en `cli.py` pasa a llamar a `scan_project` y **solo traduce**. Ojo con esto, que la v1 lo tenía mal: los mensajes de `core/` no pueden nombrar flags de la CLI, así que la CLI tiene que agregarlos ella. Dos tests existentes lo exigen (`test_scan_refuses_to_overwrite_without_force` busca `"--force"`, `test_a_folder_name_with_a_space_reports_cleanly_and_suggests_name` busca `"--name"`), y **ninguno de los dos se toca**:

- `except ProfileAlreadyExists` → el mensaje del error + `"Usá --force para sobrescribirlo (vas a perder las ediciones manuales del YAML)."`
- `except InvalidProfileName` → el mensaje del error + `"Usá --name para elegir un nombre de perfil válido."`
- `except (RootNotFound, NoKnownSources)` → el mensaje pelado.

Sugerir un flag es presentación legítima. Lo que la CLI **no** puede tener es la decisión de cuándo rechazar.

- [ ] **Step 6: Verificar**

Run: `python -m pytest -v` y `python -m ruff check .`
Expected: verde, con los tests de CLI existentes **sin modificar**

- [ ] **Step 7: Commit**

```bash
git add src/promptbrief/core src/promptbrief/cli.py tests/profile/test_scan.py
git commit -m "refactor: move the scan-and-save policy into core, with input-shaped errors"
```

---

## Task 2: Trazar cada hallazgo a su campo

**Files:**
- Modify: `src/promptbrief/core/models.py`, `src/promptbrief/core/rules/base.py`, `src/promptbrief/core/rules/text.py`, `src/promptbrief/core/rules/completeness.py`
- Test: `tests/rules/test_registry.py`, `tests/rules/test_completeness.py`

**Interfaces:**
- Produces: `Finding.slot_name: str | None`; `MissingSuccessCriteria` pasa a ser una `CompletenessRule`

**Esta tarea existe porque la auditoría encontró que la API no le alcanzaba al front.** El generador del front es un interrogatorio: clasifica la tarea, detecta qué falta y pregunta **solo eso**. Con lo que había, `Finding` trae `rule_id` y un mensaje, pero nada que diga a qué campo del formulario corresponde. El front tendría que hardcodear el mapeo `rule_id` → campo, que es una segunda fuente de verdad sobre `REQUIRED_SLOTS` — justo lo que el core declara como única.

Y hay una inconsistencia de fondo: `missing_success_criteria` vive en la familia de texto con `applies_to=()` hardcodeado, pese a que `success_criteria` está en `REQUIRED_SLOTS` para los tres tipos de tarea. Es el campo más universal de los siete y es el único sin el gancho.

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/rules/test_registry.py`:

```python
from promptbrief.core.tasks import REQUIRED_SLOTS


def test_every_finding_that_maps_to_a_field_says_which_one():
    # El front arma el formulario con esto. Sin slot_name tendría que hardcodear el
    # mapeo rule_id -> campo, que es una segunda fuente de verdad sobre REQUIRED_SLOTS.
    every_required = set().union(*REQUIRED_SLOTS.values())
    guarded = {rule.slot_name for rule in ALL_RULES if getattr(rule, "slot_name", None)}
    assert every_required == guarded


def test_the_slot_name_travels_in_the_finding():
    rule = next(r for r in ALL_RULES if r.id == "missing_success_criteria")
    finding = rule.check(_worst_case_context())
    assert finding is not None
    assert finding.slot_name == "success_criteria"


def test_rules_without_a_field_leave_slot_name_empty():
    rule = next(r for r in ALL_RULES if r.id == "dangling_reference")
    finding = rule.check(_worst_case_context())
    assert finding is not None
    assert finding.slot_name is None


def test_missing_success_criteria_derives_its_scope_like_the_rest():
    from promptbrief.core.tasks import tasks_requiring

    rule = next(r for r in ALL_RULES if r.id == "missing_success_criteria")
    assert set(rule.applies_to) == set(tasks_requiring("success_criteria"))
```

Agregar a `tests/rules/test_completeness.py`:

```python
def test_missing_success_criteria_is_now_part_of_this_family():
    from promptbrief.core.rules.completeness import COMPLETENESS_RULES

    assert any(rule.id == "missing_success_criteria" for rule in COMPLETENESS_RULES)


def test_every_required_slot_has_a_rule_guarding_it():
    # Ya no hay excepción: success_criteria dejó de ser el caso especial.
    guarded = {rule.slot_name for rule in COMPLETENESS_RULES}
    assert set().union(*REQUIRED_SLOTS.values()) == guarded
```

El test viejo `test_every_required_slot_has_a_rule_guarding_it`, que afirmaba `required - guarded == {"success_criteria"}`, se reemplaza por éste. Es el único test existente que cambia, y cambia porque el comportamiento cambió a propósito.

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/rules/ -v`
Expected: FAIL — `Finding` no tiene `slot_name`

- [ ] **Step 3: Implementar**

- `Finding` gana `slot_name: str | None = None`.
- `Rule._finding` acepta un `slot_name` opcional; `CompletenessRule` lo pasa desde `self.slot_name` automáticamente, así que las seis reglas existentes no cambian su cuerpo.
- `MissingSuccessCriteria` se muda de `text.py` a `completeness.py`, hereda de `CompletenessRule`, declara `slot_name = "success_criteria"` y `applies_to = tasks_requiring("success_criteria")`. Su `id` **no cambia**: es contrato público y `test_registry.py` lo congela.
- `TEXT_RULES` pierde esa regla y `COMPLETENESS_RULES` la gana. `ALL_RULES` sigue teniendo 17.

- [ ] **Step 4: Verificar**

Run: `python -m pytest -v` y `python -m ruff check .`
Expected: verde. El contrato de los 17 IDs sigue intacto.

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/core tests/rules
git commit -m "feat: findings name the field they guard so a client can build the form"
```

---

## Task 3: Serialización pública y escritura atómica

**Files:**
- Create: `src/promptbrief/core/profile/serialize.py`
- Modify: `src/promptbrief/core/profile/store.py`
- Test: `tests/profile/test_serialize.py`

**Interfaces:**
- Produces: `slot_to_dict`, `slot_from_dict`, `profile_to_dict`, `profile_from_dict(data, *, label="el perfil")`

**Tres correcciones respecto de la v1**, las tres de la auditoría:

1. **Se validan los tipos de los strings.** La v1 chequeaba que `slots` fuera lista y que cada elemento fuera dict, pero no que `name`, `root`, `content`, `id`, `sources[].path` y `sources[].sha256` fueran strings. Un `{"path": 5}` pasaba, se persistía, y después `root / 5` reventaba con un `TypeError` **fuera** del `try` → 500 en cada lectura posterior. Es exactamente el escenario que el spec dice querer evitar.
2. **`sources[].path` no puede ser absoluto ni contener `..`.** `Path("C:/base") / "C:/Windows/win.ini"` descarta la base entera en Windows. Con eso, un perfil guardado por API convierte `stale_sources` en un lector de rutas arbitrarias.
3. **La escritura es atómica.** `write_text` trunca y después escribe; los endpoints de FastAPI definidos con `def` corren en un threadpool, así que dos escrituras concurrentes dejan un YAML truncado y el perfil queda `ProfileCorrupt` para siempre.

- [ ] **Step 1: Escribir el test que falla**

`tests/profile/test_serialize.py`:

```python
import json
import threading

import pytest

from promptbrief.core.errors import ProfileCorrupt
from promptbrief.core.models import Profile, Provenance, Slot, SlotKind, SourceFile, TaskType
from promptbrief.core.profile.serialize import (
    profile_from_dict,
    profile_to_dict,
    slot_from_dict,
    slot_to_dict,
)


def sample() -> Profile:
    return Profile(
        name="demo",
        root="/tmp/demo",
        slots=(
            Slot(
                id="claude-convention-a1b2c3d4",
                kind=SlotKind.CONVENTION,
                content="Static export",
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


def test_a_profile_round_trips_through_dicts():
    assert profile_from_dict(profile_to_dict(sample())) == sample()


def test_the_dict_form_is_json_serializable_without_a_custom_encoder():
    payload = json.loads(json.dumps(profile_to_dict(sample())))
    assert payload["slots"][0]["kind"] == "convention"
    assert payload["slots"][0]["applies_to"] == ["code_change", "debug"]


def test_a_slot_without_provenance_keeps_its_none():
    slot = sample().slots[1]
    assert "source" not in slot_to_dict(slot)
    assert slot_from_dict(slot_to_dict(slot)).source is None


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "x"},
        {"name": "x", "root": "/tmp", "slots": "no soy una lista"},
        {"name": "x", "root": "/tmp", "slots": ["no soy un mapeo"]},
        {"name": "x", "root": "/tmp", "slots": [{"id": "a", "kind": "banana", "content": "c"}]},
        {"name": "x", "root": "/tmp", "budget_tokens": "mucho"},
        {"name": "x", "root": "/tmp", "budget_tokens": True},
        {"name": 5, "root": "/tmp"},
        {"name": "x", "root": 5},
        {"name": "x", "root": "/tmp", "slots": [{"id": 5, "kind": "stack", "content": "c"}]},
        {"name": "x", "root": "/tmp", "slots": [{"id": "a", "kind": "stack", "content": 5}]},
        {"name": "x", "root": "/tmp", "sources": [{"path": 5, "sha256": "a"}]},
        {"name": "x", "root": "/tmp", "sources": ["no soy un mapeo"]},
    ],
)
def test_a_malformed_payload_raises_profile_corrupt(payload):
    with pytest.raises(ProfileCorrupt):
        profile_from_dict(payload)


@pytest.mark.parametrize("path", ["C:/Windows/win.ini", "/etc/passwd", "../fuera.md", "a/../../b"])
def test_a_source_path_that_escapes_its_root_is_rejected(path):
    # `Path("C:/base") / "C:/Windows/win.ini"` descarta la base entera. Sin esta guarda,
    # un perfil guardado por API convierte stale_sources en un lector arbitrario.
    payload = {
        "name": "x",
        "root": "/tmp",
        "sources": [{"path": path, "sha256": "a" * 64}],
    }
    with pytest.raises(ProfileCorrupt):
        profile_from_dict(payload)


def test_a_plain_relative_source_path_is_accepted():
    payload = {"name": "x", "root": "/tmp", "sources": [{"path": "CLAUDE.md", "sha256": "a" * 64}]}
    assert profile_from_dict(payload).sources[0].path == "CLAUDE.md"


def test_the_error_names_the_profile_when_it_has_one():
    with pytest.raises(ProfileCorrupt, match="perfil 'roto'"):
        profile_from_dict({"name": "x"}, label="el perfil 'roto'")


def test_the_same_validation_protects_the_yaml_path(tmp_path):
    from promptbrief.core.profile.store import load_profile

    (tmp_path / "roto.yml").write_text(
        "name: x\nroot: /tmp\nslots:\n  - solo_una_cadena\n", encoding="utf-8"
    )
    with pytest.raises(ProfileCorrupt):
        load_profile("roto", tmp_path)


def test_concurrent_writes_never_leave_a_truncated_file(tmp_path):
    # Los endpoints con `def` corren en un threadpool: la concurrencia es real.
    from promptbrief.core.profile.store import load_profile, save_profile

    big = Profile(
        name="demo",
        root="/tmp",
        sources=(),
        slots=tuple(
            Slot(id=f"s{i}", kind=SlotKind.CONVENTION, content="x" * 500,
                 applies_to=(), source=None)
            for i in range(200)
        ),
    )
    errors: list[Exception] = []

    def writer() -> None:
        try:
            for _ in range(20):
                save_profile(big, tmp_path)
                load_profile("demo", tmp_path)
        except Exception as error:  # noqa: BLE001 - lo re-lanzamos al final
            errors.append(error)

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/profile/test_serialize.py -v`
Expected: FAIL con `ModuleNotFoundError: ... profile.serialize`

- [ ] **Step 3: Implementar**

Mover el mapeo desde `store.py` a `serialize.py`, sin prefijo `_`, sumando:

- Un helper `_text(value, field, label)` que exija `isinstance(value, str)` y levante `ProfileCorrupt` con el campo nombrado si no.
- Un helper que rechace un `sources[].path` absoluto o con `..`, usando `PurePosixPath`/`PureWindowsPath` para cubrir las dos formas de separador.
- El parámetro `label` en `profile_from_dict`, para que `load_profile` conserve el diagnóstico que hoy tiene ("En el perfil 'x', el slot en la posición 2 no es un mapeo").

`store.py` importa las cuatro funciones. `save_profile` escribe a un temporal en el mismo directorio y hace `os.replace()`, que es atómico en NTFS y en POSIX. `load_profile` usa `profile_from_dict` y **no deja ninguna copia de la validación**.

El `except` de `load_profile` conserva `(KeyError, TypeError, ValueError)` **sin `AttributeError`**, con su comentario: los guards ya cubren el input y capturarlo taparía bugs internos.

- [ ] **Step 4: Verificar**

Run: `python -m pytest -v` y `python -m ruff check .`
Expected: verde, con `tests/profile/test_store.py` **sin modificar**

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/core/profile tests/profile/test_serialize.py
git commit -m "feat: validated, public profile serialization with atomic writes"
```

---

## Task 4: `diff_profiles`

**Files:**
- Create: `src/promptbrief/core/profile/diff.py`
- Test: `tests/profile/test_diff.py`

**Interfaces:**
- Produces: `ProfileDiff` (`added`, `removed`, `modified`, `unchanged`), `diff_profiles(old, new) -> ProfileDiff`

**Tres correcciones de la auditoría**, que reprodujo los defectos ejecutando la versión v1 del algoritmo:

1. **El emparejamiento fallaba en el caso más común.** La v1 emparejaba solo cuando había exactamente uno de cada lado bajo la misma clave. Editar un bullet **y agregar otro** bajo el mismo heading —lo normal al tocar un `CLAUDE.md`— dejaba `modified` vacío y reportaba todo como churn, que es justo lo que la función existe para evitar. Ahora empareja por cercanía de línea, greedy.
2. **`unchanged` ocultaba cambios reales.** El `id` sale de `(archivo, kind, hash(contenido))`; no incluye `needs_review` ni la línea. Un fence sin cerrar pone `needs_review=True` en todos los slots —o sea que dejan de inyectarse— y el diff decía "no cambió nada". Ahora los ids compartidos se comparan campo a campo.
3. **El orden de salida no era determinístico.** Iteraba sobre la unión de dos sets de tuplas, cuyo orden depende de `PYTHONHASHSEED` y cambia entre corridas. Para una pantalla de sync es una lista que se reordena sola.

- [ ] **Step 1: Escribir el test que falla**

`tests/profile/test_diff.py`:

```python
from promptbrief.core.models import Profile, Provenance, Slot, SlotKind
from promptbrief.core.profile.diff import diff_profiles


def slot(id_, content, *, file="CLAUDE.md", line=1, kind=SlotKind.CONVENTION,
         needs_review=False):
    return Slot(
        id=id_, kind=kind, content=content, applies_to=(),
        source=Provenance(file=file, line=line), needs_review=needs_review,
    )


def profile(*slots):
    return Profile(name="demo", root="/tmp", slots=slots, sources=())


def test_identical_profiles_have_no_changes():
    result = diff_profiles(profile(slot("a", "uno")), profile(slot("a", "uno")))
    assert result.is_empty()
    assert [s.id for s in result.unchanged] == ["a"]


def test_two_empty_profiles_do_not_break():
    assert diff_profiles(profile(), profile()).is_empty()


def test_a_new_slot_is_added_and_a_deleted_one_is_removed():
    result = diff_profiles(
        profile(slot("a", "uno", line=1)),
        profile(slot("a", "uno", line=1), slot("b", "dos", line=2, kind=SlotKind.CONSTRAINT)),
    )
    assert [s.id for s in result.added] == ["b"]
    assert result.removed == ()


def test_an_edited_slot_is_modified_not_add_plus_remove():
    old = profile(slot("aaaa", "usar pnpm", line=4))
    new = profile(slot("bbbb", "usar pnpm, nunca npm", line=4))
    result = diff_profiles(old, new)

    assert result.added == () and result.removed == ()
    before, after = result.modified[0]
    assert (before.content, after.content) == ("usar pnpm", "usar pnpm, nunca npm")


def test_editing_one_bullet_while_adding_another_still_pairs_the_edit():
    # El caso más común al tocar un CLAUDE.md, y el que la v1 no resolvía.
    old = profile(slot("a1", "usar pnpm", line=4), slot("a2", "usar vitest", line=5))
    new = profile(
        slot("b1", "usar pnpm", line=4),
        slot("b2", "usar vitest, no jest", line=5),
        slot("b3", "usar biome", line=6),
    )
    result = diff_profiles(old, new)

    assert [s.id for s in result.added] == ["b3"]
    assert result.removed == ()
    assert len(result.modified) == 1
    assert result.modified[0][1].content == "usar vitest, no jest"


def test_pairing_prefers_the_closest_line():
    old = profile(slot("a1", "primero", line=2), slot("a2", "segundo", line=20))
    new = profile(slot("b1", "PRIMERO", line=3), slot("b2", "SEGUNDO", line=21))
    result = diff_profiles(old, new)

    pairs = {before.content: after.content for before, after in result.modified}
    assert pairs == {"primero": "PRIMERO", "segundo": "SEGUNDO"}


def test_edits_in_different_files_or_kinds_do_not_get_paired():
    assert diff_profiles(
        profile(slot("a", "uno", file="CLAUDE.md")),
        profile(slot("b", "dos", file="README.md")),
    ).modified == ()
    assert diff_profiles(
        profile(slot("a", "uno", kind=SlotKind.CONVENTION)),
        profile(slot("b", "dos", kind=SlotKind.CONSTRAINT)),
    ).modified == ()


def test_a_change_that_keeps_the_id_is_still_reported():
    # Un fence sin cerrar pone needs_review=True en todos los slots sin tocar el
    # contenido, así que el id no cambia y el slot deja de inyectarse. Decir
    # "no cambió nada" sería mentir.
    old = profile(slot("a", "usar pnpm", needs_review=False))
    new = profile(slot("a", "usar pnpm", needs_review=True))
    result = diff_profiles(old, new)

    assert not result.is_empty()
    assert len(result.modified) == 1
    assert result.modified[0][1].needs_review is True
    assert result.unchanged == ()


def test_a_moved_line_is_reported_too():
    old = profile(slot("a", "usar pnpm", line=4))
    new = profile(slot("a", "usar pnpm", line=9))
    result = diff_profiles(old, new)
    assert len(result.modified) == 1
    assert result.unchanged == ()


def test_the_output_order_is_deterministic():
    # Iterar sobre la unión de dos sets depende de PYTHONHASHSEED. Para una pantalla
    # de sync eso es una lista que se reordena sola en cada request.
    old = profile()
    new = profile(*(slot(f"n{i}", f"c{i}", file=f"F{i}.md") for i in range(6)))
    orders = {tuple(s.id for s in diff_profiles(old, new).added) for _ in range(5)}
    assert len(orders) == 1
    assert orders.pop() == ("n0", "n1", "n2", "n3", "n4", "n5")
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/profile/test_diff.py -v`
Expected: FAIL con `ModuleNotFoundError: ... profile.diff`

- [ ] **Step 3: Implementar**

`src/promptbrief/core/profile/diff.py`:

```python
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from promptbrief.core.models import Profile, Slot


@dataclass(frozen=True)
class ProfileDiff:
    """Qué cambió entre dos destilaciones del mismo proyecto.

    `modified` lleva pares (antes, después) para que la UI muestre los dos lados.
    """

    added: tuple[Slot, ...] = ()
    removed: tuple[Slot, ...] = ()
    modified: tuple[tuple[Slot, Slot], ...] = ()
    unchanged: tuple[Slot, ...] = ()

    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.modified)


def _pair_key(slot: Slot) -> tuple[str, str]:
    """Identidad aproximada de un slot, independiente de su contenido."""
    return (slot.source.file if slot.source else "", slot.kind.value)


def _line(slot: Slot) -> int:
    return slot.source.line if slot.source else 0


def _same(before: Slot, after: Slot) -> bool:
    """Igualdad observable de dos slots con el mismo id.

    El id no incluye `needs_review` ni la línea, así que dos slots pueden compartirlo
    y aun así comportarse distinto: uno que pasa a `needs_review` deja de inyectarse.
    """
    return (
        before.needs_review == after.needs_review
        and before.redacted == after.redacted
        and before.applies_to == after.applies_to
        and _line(before) == _line(after)
    )


def _pair_by_proximity(
    before: list[Slot], after: list[Slot]
) -> tuple[list[tuple[Slot, Slot]], list[Slot], list[Slot]]:
    """Empareja greedy por cercanía de línea. Lo que sobra queda sin par.

    Emparejar solo cuando hay uno de cada lado dejaba sin resolver el caso más común
    —editar un bullet y agregar otro bajo el mismo heading— y lo reportaba como churn.
    """
    pending_after = sorted(after, key=_line)
    pairs: list[tuple[Slot, Slot]] = []
    unpaired_before: list[Slot] = []

    for old_slot in sorted(before, key=_line):
        if not pending_after:
            unpaired_before.append(old_slot)
            continue
        closest = min(pending_after, key=lambda new: abs(_line(new) - _line(old_slot)))
        pending_after.remove(closest)
        pairs.append((old_slot, closest))

    return pairs, unpaired_before, pending_after


def diff_profiles(old: Profile, new: Profile) -> ProfileDiff:
    """Reconcilia dos destilaciones del mismo proyecto.

    Los ids derivan del contenido, así que un bullet editado aparece como un id nuevo
    que reemplaza a uno viejo. Sin reconciliación, toda edición se vería como un
    agregado más un borrado.

    El emparejamiento por cercanía de línea es una heurística y puede errar cuando se
    reordenan varios bullets a la vez; el costo de errar es mostrar un par raro, no
    perder información: los dos lados están en el resultado igual.
    """
    old_by_id = {slot.id: slot for slot in old.slots}
    new_by_id = {slot.id: slot for slot in new.slots}
    shared = old_by_id.keys() & new_by_id.keys()

    unchanged: list[Slot] = []
    modified: list[tuple[Slot, Slot]] = []
    for slot_id, slot in new_by_id.items():
        if slot_id not in shared:
            continue
        if _same(old_by_id[slot_id], slot):
            unchanged.append(slot)
        else:
            modified.append((old_by_id[slot_id], slot))

    pending_old: dict[tuple[str, str], list[Slot]] = defaultdict(list)
    pending_new: dict[tuple[str, str], list[Slot]] = defaultdict(list)
    for slot in old.slots:
        if slot.id not in shared:
            pending_old[_pair_key(slot)].append(slot)
    for slot in new.slots:
        if slot.id not in shared:
            pending_new[_pair_key(slot)].append(slot)

    added: list[Slot] = []
    removed: list[Slot] = []
    # sorted() y no la unión de sets: el orden de un set de tuplas depende de
    # PYTHONHASHSEED y cambiaría entre requests.
    for key in sorted(pending_old.keys() | pending_new.keys()):
        pairs, unpaired_old, unpaired_new = _pair_by_proximity(
            pending_old.get(key, []), pending_new.get(key, [])
        )
        modified.extend(pairs)
        removed.extend(unpaired_old)
        added.extend(unpaired_new)

    return ProfileDiff(
        added=tuple(added),
        removed=tuple(removed),
        modified=tuple(modified),
        unchanged=tuple(unchanged),
    )
```

- [ ] **Step 4: Verificar**

Run: `python -m pytest tests/profile/test_diff.py -v` y la suite completa
Expected: verde

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/core/profile/diff.py tests/profile/test_diff.py
git commit -m "feat: reconcile distillations so edits read as edits, not churn"
```

---

## Task 5: Seguridad del servidor

**Files:**
- Modify: `pyproject.toml`
- Create: `src/promptbrief/server/__init__.py`, `security.py`, `errors.py`
- Test: `tests/server/__init__.py`, `tests/server/test_security.py`

**Interfaces:**
- Produces: `SecurityConfig`, `MAX_BODY_BYTES`, `TOKEN_HEADER`, `install_security(app, config)`, `to_http_exception(error)`

**Cuatro correcciones de la auditoría, todas reproducidas ejecutando la v1:**

1. **`hmac.compare_digest` sobre `str` exige ASCII puro.** Un `?token=ñ` desde cualquier página abierta en el navegador daba un `TypeError` → **500 sin autenticar**. Se compara en bytes.
2. **El tope de body no existía** con `Transfer-Encoding: chunked`: pasaron 5 MB por un tope de 1 MB. Se cuenta lo que efectivamente llega, envolviendo `receive`.
3. **El token en la query string quedaba en el access log de uvicorn**, verificado en la salida real, más el historial del navegador. Pasa a viajar **solo en un header custom** para `/api/*`. Como no hay `CORSMiddleware`, un header custom es imposible de mandar cross-origin sin preflight, y el preflight come un 401: el CSRF queda estructuralmente cerrado, no dependiendo de un chequeo.
4. **`Origin` no cubría el DNS rebinding**, que es lo que su propio docstring afirmaba. Bajo rebinding la request es same-origin, no manda `Origin` y pasaba. Se agrega la validación de `Host` —lo único anómalo en esa request— y de `Sec-Fetch-Site`, que viaja donde `Origin` no (`<img>`, `<script>`, navegación).

- [ ] **Step 1: Dependencias**

`fastapi>=0.115` y `uvicorn[standard]>=0.30` en `dependencies`; `httpx>=0.27` en `optional-dependencies.dev`.

- [ ] **Step 2: Escribir el test que falla**

`tests/server/test_security.py`:

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from promptbrief.core.errors import (
    ProfileAlreadyExists,
    ProfileNotFound,
    PromptBriefError,
    StoredProfileCorrupt,
)
from promptbrief.server.errors import to_http_exception
from promptbrief.server.security import (
    MAX_BODY_BYTES,
    TOKEN_HEADER,
    SecurityConfig,
    install_security,
)

CONFIG = SecurityConfig(token="t" * 40, port=8765)


@pytest.fixture
def client():
    app = FastAPI()

    @app.get("/api/ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/api/echo")
    def echo(payload: dict) -> dict:
        return payload

    install_security(app, CONFIG)
    return TestClient(app)


def auth() -> dict[str, str]:
    return {TOKEN_HEADER: CONFIG.token, "Host": "127.0.0.1:8765"}


def test_a_request_without_a_token_is_rejected(client):
    assert client.get("/api/ping").status_code == 401


def test_a_request_with_the_wrong_token_is_rejected(client):
    assert client.get("/api/ping", headers={TOKEN_HEADER: "adivinado"}).status_code == 401


def test_a_request_with_the_right_token_passes(client):
    assert client.get("/api/ping", headers=auth()).status_code == 200


def test_a_non_ascii_token_is_a_401_not_a_500(client):
    # compare_digest sobre str exige ASCII puro: sin encode esto es un TypeError
    # y un 500 que cualquiera puede disparar sin conocer el token.
    assert client.get("/api/ping", headers={TOKEN_HEADER: "ñoño"}).status_code == 401
    assert client.get(f"/api/ping?token={'ñ'}").status_code == 401


def test_the_api_does_not_accept_the_token_from_the_query_string(client):
    # Viajaría en el access log de uvicorn y en el historial del navegador.
    assert client.get(f"/api/ping?token={CONFIG.token}").status_code == 401


def test_a_foreign_host_is_rejected_even_with_a_valid_token(client):
    # DNS rebinding: la IP es 127.0.0.1 y no hay Origin, pero el Host delata.
    headers = {TOKEN_HEADER: CONFIG.token, "Host": "evil.example"}
    assert client.get("/api/ping", headers=headers).status_code == 403


def test_localhost_is_accepted_as_host(client):
    headers = {TOKEN_HEADER: CONFIG.token, "Host": "localhost:8765"}
    assert client.get("/api/ping", headers=headers).status_code == 200


def test_a_foreign_origin_is_rejected(client):
    assert client.get(
        "/api/ping", headers={**auth(), "Origin": "https://evil.example"}
    ).status_code == 403


def test_the_own_origin_is_accepted(client):
    assert client.get(
        "/api/ping", headers={**auth(), "Origin": CONFIG.origin}
    ).status_code == 200


def test_a_cross_site_fetch_without_origin_is_rejected(client):
    # Sec-Fetch-Site viaja donde Origin no: <img>, <script>, navegación, no-cors.
    assert client.get(
        "/api/ping", headers={**auth(), "Sec-Fetch-Site": "cross-site"}
    ).status_code == 403


def test_a_same_origin_fetch_passes(client):
    assert client.get(
        "/api/ping", headers={**auth(), "Sec-Fetch-Site": "same-origin"}
    ).status_code == 200


def test_a_request_with_neither_origin_nor_sec_fetch_passes(client):
    # curl y los tests no mandan ninguno de los dos; el token y el Host los cubren.
    assert client.get("/api/ping", headers=auth()).status_code == 200


def test_an_oversized_body_is_rejected(client):
    response = client.post(
        "/api/echo", headers=auth(), content=b'{"x":"' + b"a" * (MAX_BODY_BYTES + 10) + b'"}'
    )
    assert response.status_code == 413


def test_an_oversized_chunked_body_is_rejected_too(client):
    # Sin Content-Length el chequeo del header no ve nada: hay que contar lo que llega.
    def chunks():
        yield b'{"x":"'
        for _ in range((MAX_BODY_BYTES // 1000) + 5):
            yield b"a" * 1000
        yield b'"}'

    assert client.post("/api/echo", headers=auth(), content=chunks()).status_code == 413


def test_a_normal_body_passes(client):
    assert client.post("/api/echo", headers=auth(), json={"x": "corto"}).status_code == 200


def test_a_post_without_a_token_is_rejected_too(client):
    # Los negativos de token no pueden ser todos GET: una guarda que solo cubriera
    # métodos seguros pasaría igual.
    assert client.post("/api/echo", json={"x": "y"}).status_code == 401


def test_the_generated_config_is_unguessable_and_fresh():
    first = SecurityConfig.generate(port=8765)
    assert len(first.token) >= 32
    assert first.origin == "http://127.0.0.1:8765"
    assert SecurityConfig.generate(port=8765).token != first.token


def test_a_short_token_is_refused_at_construction():
    # Un SecurityConfig(token="") abriría el servidor entero.
    with pytest.raises(ValueError):
        SecurityConfig(token="corto", port=8765)


def test_the_error_mapping_covers_the_hierarchy():
    assert to_http_exception(ProfileNotFound("x")).status_code == 404
    assert to_http_exception(ProfileAlreadyExists("x")).status_code == 409
    assert to_http_exception(PromptBriefError("x")).status_code == 400


def test_a_corrupt_profile_on_disk_is_not_the_clients_fault():
    # El cliente no lo mandó ni puede arreglarlo reenviando otra cosa.
    with pytest.raises(TypeError):
        to_http_exception(StoredProfileCorrupt("el YAML del servidor está roto"))


def test_an_internal_error_is_refused_by_the_mapper():
    with pytest.raises(TypeError):
        to_http_exception(RuntimeError("bug interno"))
```

- [ ] **Step 3: Verificar que falla**

Run: `python -m pytest tests/server/test_security.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'promptbrief.server'`

- [ ] **Step 4: Implementar**

`server/errors.py` — el mapeo recorre el MRO en vez de usar `type()` exacto, para que una subclase futura no caiga al genérico. `StoredProfileCorrupt` **no** está en la tabla y su presencia hace levantar `TypeError`: es un fallo de integridad del servidor, no del pedido, y tiene que llegar como 500.

`server/security.py`:

```python
from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

TOKEN_HEADER = "X-PromptBrief-Token"
# El `text` de un lint corre las reglas sobre el string completo; sin cota el costo
# crece con el tamaño del body. Medido: ~0,5 s por MB.
MAX_BODY_BYTES = 1_000_000
MIN_TOKEN_LENGTH = 32
_SAFE_FETCH_SITES = frozenset({"same-origin", "same-site", "none"})


@dataclass(frozen=True)
class SecurityConfig:
    token: str
    port: int

    def __post_init__(self) -> None:
        if len(self.token) < MIN_TOKEN_LENGTH:
            raise ValueError(f"El token necesita al menos {MIN_TOKEN_LENGTH} caracteres.")

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return frozenset({f"127.0.0.1:{self.port}", f"localhost:{self.port}"})

    @classmethod
    def generate(cls, port: int) -> SecurityConfig:
        return cls(token=secrets.token_urlsafe(32), port=port)


class BodyLimit:
    """Corta el body en MAX_BODY_BYTES contando lo que llega.

    Mirar `Content-Length` no alcanza: una request con `Transfer-Encoding: chunked`
    no lo trae y pasaría sin cota. Middleware ASGI puro y no BaseHTTPMiddleware,
    porque hay que envolver `receive` antes de que nadie lea el body.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        seen = 0
        too_big = False

        async def limited_receive():
            nonlocal seen, too_big
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    too_big = True
                    return {"type": "http.disconnect"}
            return message

        if too_big:
            await JSONResponse({"detail": "Cuerpo demasiado grande."}, 413)(scope, receive, send)
            return
        await self.app(scope, limited_receive, send)
```

> **Nota para el implementador:** el esqueleto de `BodyLimit` de arriba tiene el flag
> `too_big` chequeado antes de tiempo. Resolvelo como te resulte más claro —lo natural
> es que `limited_receive` devuelva un `http.disconnect` y que el handler responda 413,
> o envolver `send` para interceptar—, pero el comportamiento observable no se negocia:
> **el test del body chunked tiene que dar 413.** Si tu solución no lo logra, es la
> solución la que está mal, no el test.

`install_security` monta `BodyLimit` y un middleware HTTP que, en este orden: compara el token **en bytes** contra el header (nunca la query string), valida `Host` contra `allowed_hosts`, rechaza un `Sec-Fetch-Site` que no esté en `_SAFE_FETCH_SITES`, y rechaza un `Origin` distinto del propio.

- [ ] **Step 5: Verificar**

Run: `python -m pytest tests/server/ -v`, la suite completa y `ruff check .`
Expected: verde

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/promptbrief/server tests/server
git commit -m "feat: token, host, fetch-site and a real body cap for the local server"
```

---

## Task 6: Allowlist de rutas, esquemas y app

**Files:**
- Create: `src/promptbrief/server/paths.py`, `schemas.py`, `app.py`
- Test: `tests/server/test_paths.py`, `tests/server/test_app.py`

**Interfaces:**
- Produces: `checked_root(raw, allowed) -> Path`, los modelos Pydantic, `create_app(config, allowed_roots) -> FastAPI`

**`checked_root` vive en su propio módulo y se testea solo**, porque cuatro endpoints van a depender de ella y la auditoría encontró que en la v1 dos no la usaban.

Dos detalles que la auditoría marcó:

- **Validar la forma del string antes de `resolve()`.** `Path("\\\\evil.com\\share\\x").resolve()` dispara DNS y un intento de SMB **antes** de la comparación: en Windows eso es una fuga de hash NTLM hacia un host del atacante.
- **`task_type` se tipa con el enum**, no con `str`. Con `str`, un valor inválido pasa Pydantic y revienta en `TaskType(...)` con un `ValueError` → 500 por algo que es claramente culpa del pedido.

- [ ] **Step 1: Escribir el test que falla**

`tests/server/test_paths.py`:

```python
import sys

import pytest
from fastapi import HTTPException

from promptbrief.server.paths import checked_root


def test_a_path_inside_the_allowlist_passes(tmp_path):
    inner = tmp_path / "proj"
    inner.mkdir()
    assert checked_root(str(inner), (tmp_path,)) == inner.resolve()


def test_the_allowed_root_itself_passes(tmp_path):
    assert checked_root(str(tmp_path), (tmp_path,)) == tmp_path.resolve()


@pytest.mark.parametrize("raw", ["/etc", "C:/Windows", "//evil.example/share/x",
                                 "\\\\evil.example\\share\\x"])
def test_a_path_outside_the_allowlist_is_rejected(raw):
    with pytest.raises(HTTPException) as caught:
        checked_root(raw, (Path(__file__).parent,))
    assert caught.value.status_code == 403


def test_a_unc_path_is_rejected_without_touching_the_network(tmp_path, monkeypatch):
    # resolve() sobre una UNC dispara DNS y un intento de SMB: en Windows eso es una
    # fuga de hash NTLM. La forma se valida antes de resolver.
    resolved = []
    original = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda self, *a, **k: resolved.append(self) or original(self))

    with pytest.raises(HTTPException):
        checked_root("\\\\evil.example\\share", (tmp_path,))
    assert all("evil.example" not in str(p) for p in resolved)


def test_escaping_with_dotdot_is_rejected(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    with pytest.raises(HTTPException):
        checked_root(str(base / ".." / "otro"), (base,))


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin on Windows")
def test_a_symlink_that_escapes_is_rejected(tmp_path):
    base, outside = tmp_path / "base", tmp_path / "afuera"
    base.mkdir()
    outside.mkdir()
    (base / "link").symlink_to(outside)
    with pytest.raises(HTTPException):
        checked_root(str(base / "link"), (base,))
```

`tests/server/test_app.py`:

```python
import pytest
from fastapi.testclient import TestClient

from promptbrief.core.errors import ProfileNotFound, StoredProfileCorrupt
from promptbrief.server.app import create_app
from promptbrief.server.security import TOKEN_HEADER, SecurityConfig

CONFIG = SecurityConfig(token="t" * 40, port=8765)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    client = TestClient(create_app(CONFIG, allowed_roots=(tmp_path,)))
    client.headers.update({TOKEN_HEADER: CONFIG.token, "Host": "127.0.0.1:8765"})
    return client


def test_health_answers(api):
    assert api.get("/api/health").json()["status"] == "ok"


def test_health_still_needs_the_token(api):
    assert TestClient(api.app).get("/api/health").status_code == 401


def test_an_unknown_route_is_a_404(api):
    assert api.get("/api/nope").status_code == 404


def test_a_promptbrief_error_becomes_its_4xx(api):
    @api.app.get("/api/notfound")
    def notfound() -> None:
        raise ProfileNotFound("no existe")

    assert api.get("/api/notfound").status_code == 404


def test_a_stored_corruption_is_a_500_not_a_4xx(api):
    # El caso mixto: hereda de ProfileCorrupt, que sí es 400, pero éste no.
    @api.app.get("/api/rotten")
    def rotten() -> None:
        raise StoredProfileCorrupt("el YAML del servidor está roto")

    lenient = TestClient(api.app, raise_server_exceptions=False)
    lenient.headers.update(api.headers)
    assert lenient.get("/api/rotten").status_code == 500


def test_an_internal_bug_surfaces_as_500(api):
    @api.app.get("/api/boom")
    def boom() -> None:
        raise RuntimeError("bug interno")

    lenient = TestClient(api.app, raise_server_exceptions=False)
    lenient.headers.update(api.headers)
    assert lenient.get("/api/boom").status_code == 500


def test_the_allowlist_reaches_the_app_state(api, tmp_path):
    assert api.app.state.allowed_roots == (tmp_path,)
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/server/ -v`
Expected: FAIL con `ModuleNotFoundError: ... server.paths`

- [ ] **Step 3: Implementar**

`paths.py` — `checked_root` rechaza por forma (UNC, `\\?\`, cualquier cosa que empiece con `//` o `\\`) **antes** de `resolve()`, y después exige `is_relative_to` contra alguna base resuelta. Levanta `HTTPException(403)`.

`schemas.py` — `BriefRequestBody` con `task_type: TaskType | None = None` (el `StrEnum` de `core.models`; un enum es un tipo de valor, no dominio filtrándose, y evita una tercera fuente de verdad). `FindingOut` incluye **`slot_name`**, que es lo que le permite al front armar el formulario. `BriefOut` incluye **`task_type`**, el resuelto server-side, para que el front no tenga que inferirlo. `ScanBody`, `ProfileIn`, `SelectionOut`, `DiffOut`.

`app.py` — `create_app(config, allowed_roots)` guarda `allowed_roots` en `app.state`, monta la seguridad, registra el handler de `PromptBriefError` que usa `to_http_exception`, y expone `GET /api/health`.

- [ ] **Step 4: Verificar**

Run: `python -m pytest -v` y `ruff check .`
Expected: verde (el test de symlink se saltea en Windows)

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/server tests/server
git commit -m "feat: path allowlist, edge schemas and the app factory"
```

---

## Task 7: Endpoints de perfil

**Files:**
- Modify: `src/promptbrief/server/app.py`
- Test: `tests/server/test_profiles.py`

**Interfaces:**
- Produces: `GET /api/profiles`, `GET /api/profiles/{name}`, `POST /api/profiles/scan`, `POST /api/profiles`, `DELETE /api/profiles/{name}`

**Tres correcciones de la auditoría:**

1. **`POST /api/profiles` valida el `root` del body contra la allowlist.** Sin eso, el cliente guarda un perfil con `root: "C:/"` y después `/api/brief` lo usa para leer archivos arbitrarios. Era el hallazgo más grave del plan v1.
2. **`POST /api/profiles` no pisa en silencio.** La v1 dejaba que sobrescribiera con 200 mientras `scan` exigía `force` — o sea, la ruta protegida pedía confirmación y la desprotegida clobbereaba. Ahora exige que el perfil ya exista, y para crear uno nuevo está `scan`.
3. **`GET /api/profiles` devuelve un resumen**, no solo nombres, para que la pantalla de lista no haga N+1 llamadas.

- [ ] **Step 1: Escribir el test que falla**

`tests/server/test_profiles.py`, con la misma fixture `api` de la Task 6 y estos casos:

```python
def test_the_profile_list_starts_empty(api): ...
def test_scan_creates_a_profile_and_the_list_summarises_it(api, tmp_path):
    # El resumen trae name, slot_count y source_count: sin eso la pantalla de lista
    # tendría que pedir cada perfil por separado.
def test_two_profiles_both_show_up(api, tmp_path): ...          # el caso mixto de la lista
def test_a_root_outside_the_allowlist_is_rejected(api): ...     # parametrizado /etc y C:/Windows
def test_a_root_that_escapes_with_dotdot_is_rejected(api, tmp_path): ...
def test_a_root_that_does_not_exist_is_a_400_not_a_500(api, tmp_path): ...
def test_a_directory_with_no_known_sources_is_a_400(api, tmp_path): ...
def test_an_explicit_invalid_name_is_a_400(api, tmp_path): ...
def test_scanning_twice_conflicts_unless_forced(api, tmp_path): ...
def test_a_profile_round_trips_through_get(api, tmp_path): ...
def test_an_unknown_profile_is_a_404(api): ...
def test_an_invalid_profile_name_is_a_400_not_a_404(api): ...
    # Ojo: `..%2Fescape` lo desescapa el router y da 404 sin llegar a la guarda.
    # Usar `with%20space` y `CON`, que sí llegan.
def test_a_corrupt_profile_on_disk_is_a_500_not_a_400(api, tmp_path): ...
def test_an_edited_profile_can_be_saved(api, tmp_path): ...
def test_saving_a_profile_that_does_not_exist_is_a_404(api, tmp_path): ...
def test_a_malformed_profile_is_rejected_before_being_written(api, tmp_path): ...
def test_a_profile_whose_root_is_outside_the_allowlist_is_rejected(api, tmp_path): ...
    # El agujero del plan v1: sin esto, /api/brief lee cualquier archivo del disco.
def test_a_profile_with_an_absolute_source_path_is_rejected(api, tmp_path): ...
def test_an_empty_body_is_a_4xx_not_a_500(api): ...
def test_a_profile_can_be_deleted(api, tmp_path): ...
def test_deleting_an_unknown_profile_is_a_404(api): ...
```

**Escribí cada uno completo**, con sus asserts reales. Los nombres de arriba son el índice de lo que hay que cubrir, no el código.

- [ ] **Step 2: Verificar que falla** · **Step 3: Implementar** · **Step 4: Verificar** · **Step 5: Commit**

El `root` de `ScanBody` y el `root` de `ProfileIn` pasan **los dos** por `checked_root`. `POST /api/profiles` valida con `profile_from_dict` antes de `save_profile`.

```bash
git commit -m "feat: profile endpoints, allowlisted on every path they touch"
```

---

## Task 8: Sync

**Files:**
- Modify: `src/promptbrief/server/app.py`
- Test: `tests/server/test_sync.py`

**Interfaces:**
- Produces: `POST /api/profiles/{name}/sync`

Casos a cubrir, cada uno escrito completo:

- Proyecto sin cambios → todo en `unchanged`.
- Un bullet editado → `modified` con los dos lados.
- Un bullet editado **y** otro agregado bajo el mismo heading → uno en `modified` y uno en `added`. **Es el caso que la v1 no resolvía.**
- Un fence sin cerrar agregado al `CLAUDE.md` → los slots aparecen en `modified` con `needs_review: true`, no en `unchanged`.
- Sync **no escribe nada**: el perfil en disco sigue siendo el viejo.
- Perfil desconocido → 404.
- **Perfil cuyo `root` cayó fuera de la allowlist → 403.** No estaba testeado en la v1, así que la guarda no existía.
- Perfil cuyo `root` desapareció → **400** vía `RootNotFound`.

La ruta carga el perfil, pasa `profile.root` por `checked_root`, verifica que exista, re-destila y devuelve el `ProfileDiff`. **No guarda.** Para aplicar los cambios el front vuelve a llamar a `scan` con `force=true`; dejalo escrito en el docstring de la ruta.

---

## Task 9: Brief y lint

**Files:**
- Modify: `src/promptbrief/server/app.py`
- Test: `tests/server/test_brief.py`

**Interfaces:**
- Produces: `POST /api/brief`, `POST /api/lint`

**La corrección central de la auditoría:** los dos endpoints pasan `root=checked_root(profile.root, allowed)` explícito a `build_brief` / `lint`. Sin eso, `core/build.py` sigue el `root` del perfil por su cuenta y `stale_sources` hashea lo que haya ahí — un oráculo de existencia de archivos y un hasheador sin tope.

Casos a cubrir:

- Brief sin perfil → renderiza igual, con `missing_success_criteria`.
- Brief con perfil → inyecta el contexto, con la procedencia en el atributo `source`.
- La respuesta trae `selection` con las cuatro listas, **y al menos un caso con slots en más de un bucket a la vez**.
- La respuesta trae `task_type`, el resuelto server-side.
- Los hallazgos traen **`slot_name`** donde corresponde, y `null` donde no. Es lo que le permite al front armar el formulario.
- `task_type` forzado a `"debug"` → aparece `missing_repro`.
- `task_type: "inventado"` → **422** (lo da Pydantic con el enum, no un 500).
- Texto vacío → 400.
- Perfil desconocido → 404.
- **Perfil cuyo `root` está fuera de la allowlist → 403**, en `/brief` y en `/lint`.
- `lint` devuelve los mismos hallazgos que `brief`, sin el `text`.
- `lint --profile` alcanza la familia C: con una credencial en el `CLAUDE.md`, aparece `secret_redacted`.
- **Con un `budget_tokens` bajo guardado por `POST /api/profiles`, aparece `budget_exceeded`.** Es la única forma de alcanzar esa regla desde la API, así que si el arreglo de la allowlist la rompe, este test lo dice.

---

## Task 10: `pbrief serve`

**Files:**
- Modify: `src/promptbrief/cli.py`, `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `pbrief serve [--port N] [--allow PATH] [--no-browser]`

`serve` genera un `SecurityConfig` nuevo en cada arranque, arma la app con la allowlist (por defecto el directorio actual), imprime la URL con el token, abre el navegador salvo `--no-browser`, y corre uvicorn en `127.0.0.1` con `access_log=False` — el token no puede terminar en un log.

**No hay opción `--host`.** Escuchar en otra interfaz no es un default configurable.

Los tests verifican: que uvicorn reciba `127.0.0.1` y el puerto pedido; que `app.state.allowed_roots` sea lo que pasó `--allow`; que **dos invocaciones den tokens distintos**; y que `--host` no exista en el `--help`. Cuidado con la longitud de las líneas: la invocación de `runner.invoke` con todos los flags pasa los 100 caracteres si va en una sola.

Documentar en el README el comando, por qué la URL lleva un token, y por qué no se puede exponer a la red.

---

## Verificación final

- [ ] `pytest -v` en verde, con el número real reportado
- [ ] `ruff check .` sin hallazgos
- [ ] CI verde en 3.11 y 3.13
- [ ] `grep -rn "promptbrief.server\|promptbrief.cli" src/promptbrief/core/` no devuelve nada
- [ ] `pbrief serve` levanta y `/api/health` responde con el token; **sin** el token, 401
- [ ] `POST /api/profiles/scan` con un `root` fuera de la allowlist → 403
- [ ] Un perfil guardado con `root` ajeno → 403 al guardarlo, y `/api/brief` sobre él → 403
- [ ] Un body chunked de más de 1 MB → 413
- [ ] `?token=ñ` → 401, no 500
- [ ] `Host: evil.example` con token válido → 403
- [ ] Los hallazgos de `/api/lint` traen `slot_name` donde corresponde
- [ ] Ningún commit con trailer `Co-Authored-By`

---

## Después de este plan

**Plan 3 — el front Angular**: tres pantallas sobre esta API. El interrogatorio del generador se arma con el `slot_name` de cada hallazgo, así que el front no necesita saber nada de las reglas — es la pieza que la Task 2 existe para habilitar.
