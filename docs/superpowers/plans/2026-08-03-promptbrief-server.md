# PromptBrief Server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exponer el core de PromptBrief por HTTP en localhost, con el contrato de seguridad del §10 del spec, para que el front Angular tenga qué consumir.

**Architecture:** Tres tareas cierran huecos en `core/` (política de scan, serialización pública, diff de perfiles). Las seis siguientes son la capa HTTP: middleware de seguridad primero, después los endpoints agrupados por lo que tocan. `server/` es traducción HTTP y nada más: si un endpoint necesita lógica, esa lógica va a `core/`.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, pytest (con `TestClient`), ruff.

> **Precondición:** el core está terminado y publicado en
> https://github.com/FrancoLeoneDev/promptbrief — 27 commits, 226 tests, CI verde en 3.11 y 3.13.
> Este plan lo asume funcionando y no lo reescribe.

## Global Constraints

- Python 3.11+, probado en CI contra 3.11 y 3.13.
- **`core/` sigue sin importar nada de `server/` ni de `cli.py`.** La flecha va en un solo sentido.
- **`server/` no contiene lógica de negocio.** Valida el request, llama a una primitiva de `core/`, traduce el resultado y los errores. Si un endpoint necesita decidir algo, esa decisión va a `core/`.
- **`PromptBriefError` y subclases → 4xx. Cualquier otra excepción → 500.** Una sola línea de mapeo; no enumerar subclases.
- **Toda request exige el token de sesión.** Sin excepciones, ni siquiera para los `GET`.
- `ruff check .` limpio, incluyendo `tests/`. `line-length = 100`.
- Tipado completo, con `from __future__ import annotations`.
- Los tests prueban comportamiento; el caso negativo ejercita la guarda. Si borrás la guarda y el test sigue verde, el test no sirve.
- Los commits llevan únicamente a Franco Leone. **Sin trailer `Co-Authored-By`.**

## Estándares de código

Los mismos que el core, que ya están probados en 27 commits: sin estado global mutable, datos inmutables, una sola fuente de verdad, sin código inalcanzable, sin `except` mudos, sin trucos.

Uno nuevo, propio de esta capa: **los modelos Pydantic del servidor son de borde, no de dominio.** Existen para validar y serializar JSON; no reemplazan a los dataclasses de `core/models.py` ni se filtran hacia adentro.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `src/promptbrief/core/profile/scan.py` | `scan_project()` — la política de escanear y guardar, movida desde la CLI |
| `src/promptbrief/core/profile/serialize.py` | `slot_to_dict`, `slot_from_dict`, `profile_to_dict`, `profile_from_dict` |
| `src/promptbrief/core/profile/diff.py` | `ProfileDiff`, `diff_profiles()` |
| `src/promptbrief/server/__init__.py` | Vacío |
| `src/promptbrief/server/security.py` | Token de sesión, validación de `Origin`/`Host`, límite de body |
| `src/promptbrief/server/schemas.py` | Modelos Pydantic de request y response |
| `src/promptbrief/server/errors.py` | Mapeo `PromptBriefError` → 4xx |
| `src/promptbrief/server/app.py` | `create_app()` y las rutas |
| `src/promptbrief/cli.py` | Se le agrega `pbrief serve` |
| `tests/server/` | Un archivo por grupo de endpoints |

---

## Task 1: `scan_project` en el core

**Files:**
- Create: `src/promptbrief/core/profile/scan.py`
- Modify: `src/promptbrief/cli.py` (que `scan` lo use)
- Test: `tests/profile/test_scan.py`

**Interfaces:**
- Consumes: `distill_project`, `list_profiles`, `save_profile`, `Profile`, `PromptBriefError`
- Produces: `NoKnownSources`, `ProfileAlreadyExists`, `scan_project(root: Path, name: str | None = None, force: bool = False) -> tuple[Profile, Path]`

Hoy la política vive en `cli.py`: "el directorio no existe" → error, "no hay fuentes conocidas" → error, "ya existe el perfil y no pasaste `--force`" → error. Eso es política, no presentación, y el servidor la necesita igual. Moverla evita que se duplique con reglas ligeramente distintas.

- [ ] **Step 1: Escribir el test que falla**

`tests/profile/test_scan.py`:

```python
import pytest

from promptbrief.core.errors import (
    InvalidProfileName,
    NoKnownSources,
    ProfileAlreadyExists,
    PromptBriefError,
)
from promptbrief.core.profile.scan import scan_project


def write_project(tmp_path, folder="proj"):
    project = tmp_path / folder
    project.mkdir()
    (project / "CLAUDE.md").write_text(
        "# Proj\n\n## Convenciones\n\n- Static export is enabled in next.config.ts\n",
        encoding="utf-8",
    )
    return project


def test_scan_distills_and_saves(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    project = write_project(tmp_path)

    profile, path = scan_project(project)

    assert profile.name == "proj"
    assert profile.slots
    assert path.is_file()


def test_a_directory_that_does_not_exist_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    with pytest.raises(NotADirectoryError):
        scan_project(tmp_path / "nope")


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

    profile, _ = scan_project(project, force=True)
    assert profile.name == "proj"


def test_an_explicit_name_overrides_the_folder_name(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    project = write_project(tmp_path, folder="Personal Page")
    profile, _ = scan_project(project, name="personal-page")
    assert profile.name == "personal-page"


def test_a_folder_name_that_is_not_a_valid_profile_name_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    project = write_project(tmp_path, folder="Personal Page")
    with pytest.raises(InvalidProfileName):
        scan_project(project)


def test_every_rejection_is_a_promptbrief_error_except_the_missing_directory(tmp_path, monkeypatch):
    # NotADirectoryError es de la stdlib y significa "el llamador pasó algo que no existe",
    # no "el input del usuario está mal". Las otras tres sí son culpa del input.
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    assert issubclass(NoKnownSources, PromptBriefError)
    assert issubclass(ProfileAlreadyExists, PromptBriefError)
    assert issubclass(InvalidProfileName, PromptBriefError)
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/profile/test_scan.py -v`
Expected: FAIL con `ImportError: cannot import name 'NoKnownSources'`

- [ ] **Step 3: Agregar las excepciones**

En `src/promptbrief/core/errors.py`:

```python
class NoKnownSources(PromptBriefError):
    """El directorio no tiene ninguna de las fuentes que PromptBrief sabe leer."""


class ProfileAlreadyExists(PromptBriefError):
    """Ya hay un perfil con ese nombre y no se pidió sobrescribirlo."""
```

- [ ] **Step 4: Implementar**

`src/promptbrief/core/profile/scan.py`:

```python
from __future__ import annotations

from pathlib import Path

from promptbrief.core.errors import NoKnownSources, ProfileAlreadyExists
from promptbrief.core.models import Profile
from promptbrief.core.profile.distill import distill_project
from promptbrief.core.profile.store import list_profiles, save_profile


def scan_project(
    root: Path,
    name: str | None = None,
    force: bool = False,
) -> tuple[Profile, Path]:
    """Destila un directorio y guarda el perfil. Devuelve (perfil, ruta escrita).

    La política vive acá y no en la CLI porque el servidor la necesita igual: si
    estuviera en la capa de presentación, se duplicaría con reglas apenas distintas.
    """
    if not root.is_dir():
        raise NotADirectoryError(f"No existe el directorio {root}")

    profile = distill_project(root, name=name)
    if not profile.sources:
        raise NoKnownSources(
            f"No encontré CLAUDE.md, AGENTS.md, README.md ni package.json en {root}"
        )
    if profile.name in list_profiles() and not force:
        raise ProfileAlreadyExists(
            f"Ya existe el perfil '{profile.name}'. Sobrescribirlo pierde las ediciones "
            "manuales del YAML."
        )

    return profile, save_profile(profile)
```

- [ ] **Step 5: Que la CLI lo use**

Reescribir `scan` en `cli.py` para que llame a `scan_project` y solo traduzca los errores a mensajes y exit codes. La CLI **no** puede quedarse con ninguna de las tres decisiones. Los tests de `tests/test_cli.py` que cubren esos casos tienen que seguir pasando **sin tocarlos** — si alguno necesita cambiar, es señal de que se movió comportamiento y no solo su ubicación.

- [ ] **Step 6: Verificar**

Run: `python -m pytest -v` y `python -m ruff check .`
Expected: toda la suite en verde, incluidos los tests de CLI sin modificar

- [ ] **Step 7: Commit**

```bash
git add src/promptbrief/core/errors.py src/promptbrief/core/profile/scan.py src/promptbrief/cli.py tests/profile/test_scan.py
git commit -m "refactor: move the scan-and-save policy from the CLI into core"
```

---

## Task 2: Serialización pública

**Files:**
- Create: `src/promptbrief/core/profile/serialize.py`
- Modify: `src/promptbrief/core/profile/store.py` (que use las funciones públicas)
- Test: `tests/profile/test_serialize.py`

**Interfaces:**
- Produces: `slot_to_dict(slot) -> dict`, `slot_from_dict(data) -> Slot`, `profile_to_dict(profile) -> dict`, `profile_from_dict(data) -> Profile`

`store.py` ya tiene `_slot_to_dict` y `_slot_from_dict` con la validación de esquema que se peleó en la Task 9 del core. El servidor necesita exactamente eso para serializar respuestas y aceptar el perfil editado. Moverlas a un módulo propio y hacerlas públicas evita que el servidor reimplemente el mapeo — que sería una segunda fuente de verdad sobre la forma del perfil.

- [ ] **Step 1: Escribir el test que falla**

`tests/profile/test_serialize.py`:

```python
import json

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
    # El servidor lo devuelve tal cual: si hiciera falta un encoder, el mapeo estaría
    # a medias y cada endpoint tendría que acordarse de aplicarlo.
    payload = json.dumps(profile_to_dict(sample()))
    assert json.loads(payload)["slots"][0]["kind"] == "convention"
    assert json.loads(payload)["slots"][0]["applies_to"] == ["code_change", "debug"]


def test_a_slot_round_trips_on_its_own():
    slot = sample().slots[0]
    assert slot_from_dict(slot_to_dict(slot)) == slot


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
    ],
)
def test_a_malformed_payload_raises_profile_corrupt(payload):
    with pytest.raises(ProfileCorrupt):
        profile_from_dict(payload)


def test_the_same_validation_protects_the_yaml_path(tmp_path):
    # store.load_profile tiene que apoyarse en profile_from_dict, no en una copia:
    # una sola fuente de verdad sobre la forma del perfil.
    from promptbrief.core.profile.store import load_profile

    (tmp_path / "roto.yml").write_text(
        "name: x\nroot: /tmp\nslots:\n  - solo_una_cadena\n", encoding="utf-8"
    )
    with pytest.raises(ProfileCorrupt):
        load_profile("roto", tmp_path)
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/profile/test_serialize.py -v`
Expected: FAIL con `ModuleNotFoundError: ... profile.serialize`

- [ ] **Step 3: Implementar**

Mover el cuerpo de `_slot_to_dict` y `_slot_from_dict` desde `store.py` a `serialize.py` sin el prefijo `_`, y agregar `profile_to_dict` / `profile_from_dict` con la validación de esquema que hoy está inline en `load_profile` (los chequeos `isinstance(..., list)`, el `isinstance(item, dict)` por elemento, y la validación de `budget_tokens` como entero positivo excluyendo `bool`).

`store.py` pasa a importarlas: `save_profile` usa `profile_to_dict` antes de volcar el YAML, y `load_profile` usa `profile_from_dict` después de `yaml.safe_load`. **No dejes copias de la lógica en `store.py`.**

El `except` de `load_profile` conserva su tuple `(KeyError, TypeError, ValueError)` **sin `AttributeError`**, con el comentario que explica por qué: los guards ya cubren el input y capturarlo taparía bugs internos.

- [ ] **Step 4: Verificar**

Run: `python -m pytest -v` y `python -m ruff check .`
Expected: verde, y **todos los tests de `tests/profile/test_store.py` pasando sin modificar** — si alguno falla, se movió comportamiento y no solo código

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/core/profile/serialize.py src/promptbrief/core/profile/store.py tests/profile/test_serialize.py
git commit -m "refactor: extract profile serialization so the server can reuse it"
```

---

## Task 3: `diff_profiles`

**Files:**
- Create: `src/promptbrief/core/profile/diff.py`
- Test: `tests/profile/test_diff.py`

**Interfaces:**
- Produces: `ProfileDiff` (frozen dataclass con `added`, `removed`, `modified`, `unchanged`), `diff_profiles(old: Profile, new: Profile) -> ProfileDiff`

El endpoint de sync tiene que decir **qué cambió**, y `stale_sources` solo dice qué archivo cambió. El problema: como los ids derivan del contenido, un bullet editado no es "mismo id, contenido nuevo" sino un id nuevo que reemplaza a uno viejo. Un diff por id reportaría todo como agregado y borrado, y el usuario no podría distinguir una edición de un reemplazo.

- [ ] **Step 1: Escribir el test que falla**

`tests/profile/test_diff.py`:

```python
from promptbrief.core.models import Profile, Provenance, Slot, SlotKind
from promptbrief.core.profile.diff import diff_profiles


def slot(id_: str, content: str, *, file: str = "CLAUDE.md", line: int = 1,
         kind: SlotKind = SlotKind.CONVENTION) -> Slot:
    return Slot(
        id=id_,
        kind=kind,
        content=content,
        applies_to=(),
        source=Provenance(file=file, line=line),
    )


def profile(*slots: Slot) -> Profile:
    return Profile(name="demo", root="/tmp", slots=slots, sources=())


def test_identical_profiles_have_no_changes():
    result = diff_profiles(profile(slot("a", "uno")), profile(slot("a", "uno")))
    assert result.added == ()
    assert result.removed == ()
    assert result.modified == ()
    assert [s.id for s in result.unchanged] == ["a"]


def test_a_new_slot_is_reported_as_added():
    result = diff_profiles(profile(slot("a", "uno")), profile(slot("a", "uno"), slot("b", "dos")))
    assert [s.id for s in result.added] == ["b"]
    assert result.removed == ()


def test_a_deleted_slot_is_reported_as_removed():
    result = diff_profiles(profile(slot("a", "uno"), slot("b", "dos")), profile(slot("a", "uno")))
    assert [s.id for s in result.removed] == ["b"]
    assert result.added == ()


def test_an_edited_slot_is_reported_as_modified_not_as_add_plus_remove():
    # El caso que motiva la función: el id cambia porque deriva del contenido.
    old = profile(slot("claude-convention-aaaa", "usar pnpm", line=4))
    new = profile(slot("claude-convention-bbbb", "usar pnpm, nunca npm", line=4))
    result = diff_profiles(old, new)

    assert result.added == ()
    assert result.removed == ()
    assert len(result.modified) == 1
    before, after = result.modified[0]
    assert before.content == "usar pnpm"
    assert after.content == "usar pnpm, nunca npm"


def test_edits_in_different_files_do_not_get_paired():
    old = profile(slot("a", "uno", file="CLAUDE.md"))
    new = profile(slot("b", "dos", file="README.md"))
    result = diff_profiles(old, new)
    assert result.modified == ()
    assert [s.id for s in result.added] == ["b"]
    assert [s.id for s in result.removed] == ["a"]


def test_edits_of_different_kinds_do_not_get_paired():
    old = profile(slot("a", "uno", kind=SlotKind.CONVENTION))
    new = profile(slot("b", "dos", kind=SlotKind.CONSTRAINT))
    result = diff_profiles(old, new)
    assert result.modified == ()


def test_two_edits_under_the_same_file_and_kind_are_ambiguous_and_stay_unpaired():
    # La heurística empareja solo cuando hay exactamente uno de cada lado. Con dos,
    # cualquier emparejamiento sería inventado, así que se reporta lo conservador.
    old = profile(slot("a1", "uno", line=4), slot("a2", "dos", line=5))
    new = profile(slot("b1", "UNO", line=4), slot("b2", "DOS", line=5))
    result = diff_profiles(old, new)

    assert result.modified == ()
    assert sorted(s.id for s in result.added) == ["b1", "b2"]
    assert sorted(s.id for s in result.removed) == ["a1", "a2"]


def test_a_slot_without_provenance_can_still_be_paired_by_kind():
    old = Profile(
        name="d", root="/tmp", sources=(),
        slots=(Slot(id="a", kind=SlotKind.STACK, content="Next 14", applies_to=(), source=None),),
    )
    new = Profile(
        name="d", root="/tmp", sources=(),
        slots=(Slot(id="b", kind=SlotKind.STACK, content="Next 15", applies_to=(), source=None),),
    )
    result = diff_profiles(old, new)
    assert len(result.modified) == 1
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


def diff_profiles(old: Profile, new: Profile) -> ProfileDiff:
    """Reconcilia dos perfiles del mismo proyecto.

    Los ids derivan del contenido, así que un bullet editado aparece como un id nuevo
    que reemplaza a uno viejo. Sin reconciliación, toda edición se vería como un
    agregado más un borrado y el usuario no podría distinguirla de un reemplazo real.

    Tres pasos: los ids compartidos son iguales; de lo que queda, se emparejan los que
    comparten archivo y kind **cuando hay exactamente uno de cada lado**; el resto es
    agregado o eliminado. El emparejamiento es una heurística: con dos candidatos de
    cada lado, cualquier par sería inventado, así que se cae al resultado conservador.
    """
    old_by_id = {slot.id: slot for slot in old.slots}
    new_by_id = {slot.id: slot for slot in new.slots}

    shared_ids = old_by_id.keys() & new_by_id.keys()
    unchanged = tuple(new_by_id[slot_id] for slot_id in new_by_id if slot_id in shared_ids)

    pending_old: dict[tuple[str, str], list[Slot]] = defaultdict(list)
    pending_new: dict[tuple[str, str], list[Slot]] = defaultdict(list)
    for slot in old.slots:
        if slot.id not in shared_ids:
            pending_old[_pair_key(slot)].append(slot)
    for slot in new.slots:
        if slot.id not in shared_ids:
            pending_new[_pair_key(slot)].append(slot)

    modified: list[tuple[Slot, Slot]] = []
    added: list[Slot] = []
    removed: list[Slot] = []

    for key in pending_old.keys() | pending_new.keys():
        before, after = pending_old.get(key, []), pending_new.get(key, [])
        if len(before) == 1 and len(after) == 1:
            modified.append((before[0], after[0]))
        else:
            removed.extend(before)
            added.extend(after)

    return ProfileDiff(
        added=tuple(added),
        removed=tuple(removed),
        modified=tuple(modified),
        unchanged=unchanged,
    )
```

- [ ] **Step 4: Verificar**

Run: `python -m pytest tests/profile/test_diff.py -v` y después la suite completa
Expected: 8 passed en el archivo nuevo, suite completa verde

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/core/profile/diff.py tests/profile/test_diff.py
git commit -m "feat: reconcile two distillations so edits read as edits, not churn"
```

---

## Task 4: Seguridad del servidor

**Files:**
- Create: `src/promptbrief/server/__init__.py`, `src/promptbrief/server/security.py`, `src/promptbrief/server/errors.py`
- Modify: `pyproject.toml` (dependencias `fastapi`, `uvicorn[standard]`; `httpx` en `dev` para `TestClient`)
- Test: `tests/server/__init__.py`, `tests/server/test_security.py`

**Interfaces:**
- Produces: `SessionToken` (con `value` y `check(request)`), `SecurityConfig`, `install_security(app, config)`, `to_http_exception(error)`

**Escuchar en loopback no alcanza y ésta es la tarea donde eso se resuelve.** Cualquier página abierta en el navegador del usuario puede hacer `fetch("http://127.0.0.1:PUERTO/api/...")`: el origen es el navegador de la víctima, así que ni el firewall ni el bind a `127.0.0.1` lo detienen. La defensa principal es un **token de sesión** que la página atacante no puede adivinar.

- [ ] **Step 1: Agregar las dependencias**

En `pyproject.toml`: `fastapi>=0.115` y `uvicorn[standard]>=0.30` en `dependencies`; `httpx>=0.27` en `optional-dependencies.dev` (lo necesita `TestClient`).

- [ ] **Step 2: Escribir el test que falla**

`tests/server/test_security.py`:

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from promptbrief.core.errors import ProfileNotFound, PromptBriefError
from promptbrief.server.errors import to_http_exception
from promptbrief.server.security import MAX_BODY_BYTES, SecurityConfig, install_security


@pytest.fixture
def client():
    app = FastAPI()

    @app.get("/api/ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/api/echo")
    def echo(payload: dict) -> dict:
        return payload

    config = SecurityConfig(token="s3cr3t-token", origin="http://127.0.0.1:8765")
    install_security(app, config)
    return TestClient(app), config


def test_a_request_without_a_token_is_rejected(client):
    api, _ = client
    assert api.get("/api/ping").status_code == 401


def test_a_request_with_the_wrong_token_is_rejected(client):
    api, _ = client
    response = api.get("/api/ping", headers={"X-PromptBrief-Token": "adivinado"})
    assert response.status_code == 401


def test_a_request_with_the_right_token_passes(client):
    api, config = client
    response = api.get("/api/ping", headers={"X-PromptBrief-Token": config.token})
    assert response.status_code == 200


def test_the_token_can_also_travel_as_a_query_parameter(client):
    # Es como llega la primera carga cuando `pbrief serve` abre el navegador.
    api, config = client
    assert api.get(f"/api/ping?token={config.token}").status_code == 200


def test_a_foreign_origin_is_rejected_even_with_a_valid_token(client):
    # DNS rebinding: la IP es 127.0.0.1 pero el Origin no es el propio.
    api, config = client
    response = api.get(
        "/api/ping",
        headers={"X-PromptBrief-Token": config.token, "Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_the_own_origin_is_accepted(client):
    api, config = client
    response = api.get(
        "/api/ping",
        headers={"X-PromptBrief-Token": config.token, "Origin": config.origin},
    )
    assert response.status_code == 200


def test_a_request_with_no_origin_header_passes(client):
    # curl y los tests no mandan Origin; el token sigue siendo la defensa principal.
    api, config = client
    assert api.get("/api/ping", headers={"X-PromptBrief-Token": config.token}).status_code == 200


def test_an_oversized_body_is_rejected_before_being_parsed(client):
    api, config = client
    response = api.post(
        "/api/echo",
        headers={"X-PromptBrief-Token": config.token},
        content=b'{"x": "' + b"a" * (MAX_BODY_BYTES + 10) + b'"}',
    )
    assert response.status_code == 413


def test_a_normal_body_passes(client):
    api, config = client
    response = api.post(
        "/api/echo", headers={"X-PromptBrief-Token": config.token}, json={"x": "corto"}
    )
    assert response.status_code == 200


def test_the_generated_token_is_long_enough_to_be_unguessable():
    config = SecurityConfig.generate(port=8765)
    assert len(config.token) >= 32
    assert config.origin == "http://127.0.0.1:8765"
    assert SecurityConfig.generate(port=8765).token != config.token


def test_promptbrief_errors_map_to_4xx_and_the_rest_do_not():
    assert to_http_exception(ProfileNotFound("no existe")).status_code == 404
    assert to_http_exception(PromptBriefError("input feo")).status_code == 400
    with pytest.raises(TypeError):
        to_http_exception(RuntimeError("bug interno"))
```

- [ ] **Step 3: Verificar que falla**

Run: `python -m pytest tests/server/test_security.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'promptbrief.server'`

- [ ] **Step 4: Implementar**

`src/promptbrief/server/errors.py`:

```python
from __future__ import annotations

from fastapi import HTTPException

from promptbrief.core.errors import (
    InvalidProfileName,
    NoKnownSources,
    ProfileAlreadyExists,
    ProfileCorrupt,
    ProfileNotFound,
    PromptBriefError,
)

_STATUS: dict[type[PromptBriefError], int] = {
    ProfileNotFound: 404,
    ProfileAlreadyExists: 409,
    InvalidProfileName: 400,
    ProfileCorrupt: 400,
    NoKnownSources: 400,
}


def to_http_exception(error: PromptBriefError) -> HTTPException:
    """Traduce un error de input a su 4xx.

    Solo acepta PromptBriefError: cualquier otra excepción es un bug interno y tiene
    que llegar al manejador por defecto como 500, no disfrazarse de culpa del usuario.
    """
    if not isinstance(error, PromptBriefError):
        raise TypeError(f"{type(error).__name__} no es un error de input")
    return HTTPException(status_code=_STATUS.get(type(error), 400), detail=str(error))
```

`src/promptbrief/server/security.py`:

```python
from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

TOKEN_HEADER = "X-PromptBrief-Token"
TOKEN_QUERY = "token"
# El `text` de un lint corre las reglas sobre el string completo; sin cota, el costo
# crece con el tamaño del body. 1 MB es holgado para un pedido escrito a mano.
MAX_BODY_BYTES = 1_000_000


@dataclass(frozen=True)
class SecurityConfig:
    token: str
    origin: str

    @classmethod
    def generate(cls, port: int) -> SecurityConfig:
        return cls(token=secrets.token_urlsafe(32), origin=f"http://127.0.0.1:{port}")


def install_security(app: FastAPI, config: SecurityConfig) -> None:
    """Exige el token en toda request y rechaza orígenes ajenos y bodies enormes.

    El token es la defensa principal, no el bind a loopback: cualquier página abierta
    en el navegador del usuario puede hacer fetch a 127.0.0.1, pero no puede adivinar
    un token de 32 bytes. La validación de Origin cubre el DNS rebinding, que es el
    ataque que sortea el chequeo de IP.
    """

    @app.middleware("http")
    async def guard(request: Request, call_next):
        supplied = request.headers.get(TOKEN_HEADER) or request.query_params.get(TOKEN_QUERY, "")
        if not hmac.compare_digest(supplied, config.token):
            return JSONResponse({"detail": "Token inválido o ausente."}, status_code=401)

        origin = request.headers.get("Origin")
        if origin is not None and origin != config.origin:
            return JSONResponse({"detail": f"Origen no permitido: {origin}"}, status_code=403)

        declared = request.headers.get("Content-Length")
        if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "El cuerpo del pedido es demasiado grande."},
                                status_code=413)

        return await call_next(request)
```

Crear `src/promptbrief/server/__init__.py` y `tests/server/__init__.py` vacíos.

- [ ] **Step 5: Verificar**

Run: `python -m pytest tests/server/ -v` y después la suite completa y `ruff check .`
Expected: 12 passed en el archivo nuevo, suite completa verde

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/promptbrief/server tests/server
git commit -m "feat: session token, origin check and body cap for the local server"
```

---

## Task 5: Esquemas y app

**Files:**
- Create: `src/promptbrief/server/schemas.py`, `src/promptbrief/server/app.py`
- Test: `tests/server/test_app.py`

**Interfaces:**
- Produces: `create_app(config: SecurityConfig, allowed_roots: tuple[Path, ...]) -> FastAPI`; los modelos Pydantic de request y response

Los modelos Pydantic son **de borde**: validan y serializan JSON, no reemplazan a los dataclasses de `core/models.py` ni se filtran hacia adentro. La conversión pasa por `profile_to_dict` / `profile_from_dict`, que ya son la única fuente de verdad sobre la forma del perfil.

- [ ] **Step 1: Escribir el test que falla**

`tests/server/test_app.py`:

```python
import pytest
from fastapi.testclient import TestClient

from promptbrief.server.app import create_app
from promptbrief.server.security import SecurityConfig


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    config = SecurityConfig(token="t0ken-de-prueba", origin="http://127.0.0.1:8765")
    app = create_app(config, allowed_roots=(tmp_path,))
    client = TestClient(app)
    client.headers.update({"X-PromptBrief-Token": config.token})
    return client


def test_health_answers_without_touching_the_disk(api):
    response = api.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_still_needs_the_token(api):
    bare = TestClient(api.app)
    assert bare.get("/api/health").status_code == 401


def test_an_unknown_route_is_a_404_not_a_500(api):
    assert api.get("/api/nope").status_code == 404


def test_an_internal_bug_surfaces_as_500_not_as_a_4xx(api):
    # La jerarquía de errores existe para que esto no se confunda con culpa del input.
    @api.app.get("/api/boom")
    def boom() -> None:
        raise RuntimeError("bug interno")

    with pytest.raises(RuntimeError):
        api.get("/api/boom")
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/server/test_app.py -v`
Expected: FAIL con `ModuleNotFoundError: ... server.app`

- [ ] **Step 3: Implementar**

`src/promptbrief/server/schemas.py` — modelos Pydantic:

- `BriefRequestBody`: `text: str`, `task_type: str | None = None`, `profile: str | None = None`, `success_criteria: str | None = None`, `output_format: str | None = None`, `file_scope: list[str] = []`, `constraints: list[str] = []`, `examples: list[str] = []`, `repro_steps: str | None = None`, `expected_vs_actual: str | None = None`.
- `ScanBody`: `root: str`, `name: str | None = None`, `force: bool = False`.
- `FindingOut`: `rule_id`, `family`, `severity`, `message`, `suggestion`.
- `BriefOut`: `text: str`, `findings: list[FindingOut]`, `selection: SelectionOut`.
- `SelectionOut`: las cuatro listas de slots, cada una como `list[dict]` vía `slot_to_dict`.
- `DiffOut`: `added`, `removed`, `modified` (pares), `unchanged`.

`src/promptbrief/server/app.py` — `create_app(config, allowed_roots)` que arma el `FastAPI`, llama a `install_security`, registra un manejador de `PromptBriefError` que usa `to_http_exception`, y expone `GET /api/health`. Las rutas de datos llegan en las Tasks 6, 7 y 8.

`allowed_roots` se guarda en el estado de la app: es la allowlist que la Task 6 va a usar para validar el `root` de scan.

- [ ] **Step 4: Verificar**

Run: `python -m pytest tests/server/ -v` y la suite completa
Expected: verde

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/server/schemas.py src/promptbrief/server/app.py tests/server/test_app.py
git commit -m "feat: FastAPI app factory with edge schemas and error mapping"
```

---

## Task 6: Endpoints de perfil

**Files:**
- Modify: `src/promptbrief/server/app.py`
- Test: `tests/server/test_profiles.py`

**Interfaces:**
- Produces: `GET /api/profiles`, `GET /api/profiles/{name}`, `POST /api/profiles/scan`, `POST /api/profiles`

**La allowlist de directorios es obligatoria en esta tarea.** `core/` valida los nombres de perfil pero trata `root` como confiable por diseño. Sin allowlist, `POST /api/profiles/scan` es un lector de archivos arbitrario del sistema.

- [ ] **Step 1: Escribir el test que falla**

`tests/server/test_profiles.py`:

```python
import pytest
from fastapi.testclient import TestClient

from promptbrief.server.app import create_app
from promptbrief.server.security import SecurityConfig


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    config = SecurityConfig(token="t0ken", origin="http://127.0.0.1:8765")
    client = TestClient(create_app(config, allowed_roots=(tmp_path,)))
    client.headers.update({"X-PromptBrief-Token": config.token})
    return client


def write_project(tmp_path, folder="proj"):
    project = tmp_path / folder
    project.mkdir()
    (project / "CLAUDE.md").write_text(
        "# Proj\n\n## Convenciones\n\n- Static export is enabled\n\n"
        "## Prohibiciones\n\n- No modificar next.config.ts\n",
        encoding="utf-8",
    )
    return project


def test_the_profile_list_starts_empty(api):
    assert api.get("/api/profiles").json() == []


def test_scan_creates_a_profile_and_it_shows_up_in_the_list(api, tmp_path):
    project = write_project(tmp_path)
    response = api.post("/api/profiles/scan", json={"root": str(project)})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "proj"
    assert any(slot["kind"] == "constraint" for slot in body["slots"])
    assert api.get("/api/profiles").json() == ["proj"]


def test_a_root_outside_the_allowlist_is_rejected(api):
    # core/ valida los nombres de perfil, no las rutas. Sin esta guarda el endpoint
    # lee cualquier archivo del sistema.
    response = api.post("/api/profiles/scan", json={"root": "C:/Windows" })
    assert response.status_code == 403


def test_a_root_that_escapes_the_allowlist_with_dotdot_is_rejected(api, tmp_path):
    response = api.post("/api/profiles/scan", json={"root": str(tmp_path / ".." / "otro")})
    assert response.status_code == 403


def test_scanning_twice_conflicts_unless_forced(api, tmp_path):
    project = write_project(tmp_path)
    api.post("/api/profiles/scan", json={"root": str(project)})

    assert api.post("/api/profiles/scan", json={"root": str(project)}).status_code == 409
    forced = api.post("/api/profiles/scan", json={"root": str(project), "force": True})
    assert forced.status_code == 200


def test_a_directory_with_no_known_sources_is_a_400(api, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert api.post("/api/profiles/scan", json={"root": str(empty)}).status_code == 400


def test_a_profile_can_be_read_back_and_round_trips(api, tmp_path):
    project = write_project(tmp_path)
    scanned = api.post("/api/profiles/scan", json={"root": str(project)}).json()
    fetched = api.get("/api/profiles/proj").json()
    assert fetched == scanned


def test_an_unknown_profile_is_a_404(api):
    assert api.get("/api/profiles/nope").status_code == 404


def test_an_invalid_profile_name_is_a_400_not_a_404(api):
    assert api.get("/api/profiles/..%2Fescape").status_code == 400


def test_an_edited_profile_can_be_saved(api, tmp_path):
    project = write_project(tmp_path)
    profile = api.post("/api/profiles/scan", json={"root": str(project)}).json()
    profile["budget_tokens"] = 900

    assert api.post("/api/profiles", json=profile).status_code == 200
    assert api.get("/api/profiles/proj").json()["budget_tokens"] == 900


def test_a_malformed_profile_is_rejected_before_being_written(api, tmp_path):
    project = write_project(tmp_path)
    profile = api.post("/api/profiles/scan", json={"root": str(project)}).json()
    good = api.get("/api/profiles/proj").json()

    profile["slots"] = ["no soy un mapeo"]
    assert api.post("/api/profiles", json=profile).status_code == 400
    # Y lo que había en disco quedó intacto.
    assert api.get("/api/profiles/proj").json() == good
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/server/test_profiles.py -v`
Expected: FAIL con 404 en las rutas nuevas

- [ ] **Step 3: Implementar**

Agregar a `app.py` las cuatro rutas. La validación de la allowlist va en un helper propio:

```python
def _checked_root(raw: str, allowed: Sequence[Path]) -> Path:
    """Resuelve la ruta y exige que caiga dentro de un directorio permitido.

    core/ trata `root` como confiable por diseño: la responsabilidad de acotarlo es
    de la capa que lo recibe de afuera, y esa capa es ésta.
    """
    root = Path(raw).resolve()
    if not any(root.is_relative_to(base.resolve()) for base in allowed):
        raise HTTPException(status_code=403, detail=f"Ruta no permitida: {root}")
    return root
```

`POST /api/profiles` valida con `profile_from_dict` **antes** de llamar a `save_profile`: un perfil malformado persistido una vez rompe todas las lecturas posteriores.

- [ ] **Step 4: Verificar**

Run: `python -m pytest tests/server/ -v` y la suite completa
Expected: verde

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/server/app.py tests/server/test_profiles.py
git commit -m "feat: profile endpoints with a directory allowlist for scanning"
```

---

## Task 7: Sync

**Files:**
- Modify: `src/promptbrief/server/app.py`
- Test: `tests/server/test_sync.py`

**Interfaces:**
- Produces: `POST /api/profiles/{name}/sync`

- [ ] **Step 1: Escribir el test que falla**

`tests/server/test_sync.py`:

```python
import pytest
from fastapi.testclient import TestClient

from promptbrief.server.app import create_app
from promptbrief.server.security import SecurityConfig


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    config = SecurityConfig(token="t0ken", origin="http://127.0.0.1:8765")
    client = TestClient(create_app(config, allowed_roots=(tmp_path,)))
    client.headers.update({"X-PromptBrief-Token": config.token})
    return client


def write_project(tmp_path, body):
    project = tmp_path / "proj"
    project.mkdir(exist_ok=True)
    (project / "CLAUDE.md").write_text(body, encoding="utf-8")
    return project


def test_sync_on_an_unchanged_project_reports_nothing(api, tmp_path):
    project = write_project(tmp_path, "## Convenciones\n\n- usar pnpm\n")
    api.post("/api/profiles/scan", json={"root": str(project)})

    body = api.post("/api/profiles/proj/sync").json()
    assert body["added"] == []
    assert body["removed"] == []
    assert body["modified"] == []
    assert len(body["unchanged"]) == 1


def test_an_edited_bullet_reports_as_modified_with_both_sides(api, tmp_path):
    project = write_project(tmp_path, "## Convenciones\n\n- usar pnpm\n")
    api.post("/api/profiles/scan", json={"root": str(project)})
    write_project(tmp_path, "## Convenciones\n\n- usar pnpm, nunca npm\n")

    body = api.post("/api/profiles/proj/sync").json()
    assert body["added"] == []
    assert body["removed"] == []
    assert len(body["modified"]) == 1
    before, after = body["modified"][0]
    assert before["content"] == "usar pnpm"
    assert after["content"] == "usar pnpm, nunca npm"


def test_a_new_bullet_reports_as_added(api, tmp_path):
    project = write_project(tmp_path, "## Convenciones\n\n- usar pnpm\n")
    api.post("/api/profiles/scan", json={"root": str(project)})
    write_project(tmp_path, "## Convenciones\n\n- usar pnpm\n- usar vitest\n")

    body = api.post("/api/profiles/proj/sync").json()
    assert len(body["added"]) == 1
    assert body["added"][0]["content"] == "usar vitest"


def test_sync_does_not_write_anything_by_itself(api, tmp_path):
    # Es un preview: el usuario decide si guarda. Confirmar que el perfil en disco
    # sigue siendo el viejo después de sincronizar.
    project = write_project(tmp_path, "## Convenciones\n\n- usar pnpm\n")
    api.post("/api/profiles/scan", json={"root": str(project)})
    write_project(tmp_path, "## Convenciones\n\n- usar pnpm, nunca npm\n")

    api.post("/api/profiles/proj/sync")
    stored = api.get("/api/profiles/proj").json()
    assert stored["slots"][0]["content"] == "usar pnpm"


def test_sync_on_an_unknown_profile_is_a_404(api):
    assert api.post("/api/profiles/nope/sync").status_code == 404


def test_sync_on_a_profile_whose_root_disappeared_is_a_400(api, tmp_path):
    import shutil

    project = write_project(tmp_path, "## Convenciones\n\n- usar pnpm\n")
    api.post("/api/profiles/scan", json={"root": str(project)})
    shutil.rmtree(project)

    assert api.post("/api/profiles/proj/sync").status_code == 400
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/server/test_sync.py -v`
Expected: FAIL con 404 en la ruta nueva

- [ ] **Step 3: Implementar**

La ruta carga el perfil guardado, vuelve a destilar desde `profile.root` (pasándolo por la misma allowlist), y devuelve el `ProfileDiff` serializado. **No guarda nada**: es un preview, y el usuario decide.

- [ ] **Step 4: Verificar**

Run: `python -m pytest tests/server/ -v` y la suite completa
Expected: verde

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/server/app.py tests/server/test_sync.py
git commit -m "feat: sync endpoint previewing what changed since the last scan"
```

---

## Task 8: Brief y lint

**Files:**
- Modify: `src/promptbrief/server/app.py`
- Test: `tests/server/test_brief.py`

**Interfaces:**
- Produces: `POST /api/brief`, `POST /api/lint`

- [ ] **Step 1: Escribir el test que falla**

`tests/server/test_brief.py`:

```python
import pytest
from fastapi.testclient import TestClient

from promptbrief.server.app import create_app
from promptbrief.server.security import SecurityConfig


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    config = SecurityConfig(token="t0ken", origin="http://127.0.0.1:8765")
    client = TestClient(create_app(config, allowed_roots=(tmp_path,)))
    client.headers.update({"X-PromptBrief-Token": config.token})
    return client


def scanned_project(api, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "CLAUDE.md").write_text(
        "# Proj\n\n## Convenciones\n\n- Static export is enabled\n\n"
        "## Prohibiciones\n\n- No modificar next.config.ts\n",
        encoding="utf-8",
    )
    api.post("/api/profiles/scan", json={"root": str(project)})
    return project


def test_a_brief_without_a_profile_still_renders(api):
    response = api.post("/api/brief", json={"text": "agregar una seccion de python"})
    assert response.status_code == 200
    body = response.json()
    assert "<task>" in body["text"]
    assert any(f["rule_id"] == "missing_success_criteria" for f in body["findings"])


def test_a_brief_with_a_profile_injects_its_context(api, tmp_path):
    scanned_project(api, tmp_path)
    response = api.post(
        "/api/brief",
        json={
            "text": "agregar una seccion de python",
            "profile": "proj",
            "success_criteria": "se ve como game dev",
            "output_format": "code",
            "file_scope": ["src/data/portfolio.ts"],
        },
    )
    body = response.json()
    assert "Static export is enabled" in body["text"]
    assert "Mantener next.config.ts sin cambios." in body["text"]
    assert 'source="CLAUDE.md:5"' in body["text"]


def test_the_response_exposes_the_full_selection_with_its_reasons(api, tmp_path):
    # El front tiene que poder mostrar qué se inyectó y qué no, con el motivo.
    scanned_project(api, tmp_path)
    body = api.post("/api/brief", json={"text": "escribir un post", "profile": "proj"}).json()
    assert set(body["selection"]) == {
        "selected", "over_budget", "not_applicable", "skipped_for_review"
    }


def test_the_task_type_can_be_forced_instead_of_classified(api):
    body = api.post(
        "/api/brief", json={"text": "hacer la cosa", "task_type": "debug"}
    ).json()
    assert any(f["rule_id"] == "missing_repro" for f in body["findings"])


def test_an_unknown_task_type_is_a_422(api):
    assert api.post(
        "/api/brief", json={"text": "hacer la cosa", "task_type": "inventado"}
    ).status_code == 422


def test_an_empty_text_is_a_400_not_a_500(api):
    assert api.post("/api/brief", json={"text": "   "}).status_code == 400


def test_an_unknown_profile_is_a_404(api):
    assert api.post(
        "/api/brief", json={"text": "hacer la cosa", "profile": "nope"}
    ).status_code == 404


def test_lint_returns_the_same_findings_without_the_brief(api):
    payload = {"text": "arreglalo"}
    brief = api.post("/api/brief", json=payload).json()
    lint = api.post("/api/lint", json=payload).json()
    assert lint["findings"] == brief["findings"]
    assert "text" not in lint


def test_lint_reaches_the_context_family_when_a_profile_is_given(api, tmp_path):
    # Sin perfil, cinco de las diecisiete reglas no pueden dispararse nunca.
    project = tmp_path / "proj"
    project.mkdir()
    (project / "CLAUDE.md").write_text(
        "# Proj\n\n## Notas\n\n- AWS_KEY=AKIAIOSFODNN7EXAMPLE\n", encoding="utf-8"
    )
    api.post("/api/profiles/scan", json={"root": str(project)})

    body = api.post("/api/lint", json={"text": "hacer la cosa", "profile": "proj"}).json()
    assert any(f["rule_id"] == "secret_redacted" for f in body["findings"])
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/server/test_brief.py -v`
Expected: FAIL con 404 en las rutas nuevas

- [ ] **Step 3: Implementar**

Las dos rutas construyen un `BriefRequest` desde el body, resuelven el perfil con `resolve_profile` si vino uno, y llaman a `build_brief` o `lint`. El `task_type` se clasifica con `classify()` cuando el body no lo trae.

- [ ] **Step 4: Verificar**

Run: `python -m pytest -v` y `python -m ruff check .`
Expected: toda la suite verde

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/server/app.py tests/server/test_brief.py
git commit -m "feat: brief and lint endpoints over the local API"
```

---

## Task 9: `pbrief serve`

**Files:**
- Modify: `src/promptbrief/cli.py`, `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `pbrief serve [--port N] [--allow PATH] [--no-browser]`

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_cli.py`:

```python
def test_serve_builds_an_app_with_a_fresh_token_and_the_allowlist(tmp_path, monkeypatch):
    # No levantamos uvicorn en el test: verificamos que la app quede armada bien.
    captured = {}

    def fake_run(app, host, port, **kwargs):
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("uvicorn.run", fake_run)
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))

    result = runner.invoke(app, ["serve", "--port", "8899", "--allow", str(tmp_path), "--no-browser"])

    assert result.exit_code == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8899
    assert "127.0.0.1:8899" in result.stdout
    assert "token=" in result.stdout


def test_serve_refuses_a_host_other_than_loopback(tmp_path, monkeypatch):
    # No hay opción para cambiarlo: es una decisión, no un default.
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    result = runner.invoke(app, ["serve", "--help"])
    assert "--host" not in result.stdout
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/test_cli.py -k serve -v`
Expected: FAIL, el comando no existe

- [ ] **Step 3: Implementar**

`serve` genera un `SecurityConfig` nuevo en cada arranque, arma la app con la allowlist (por defecto, el directorio actual), imprime la URL **con el token incluido**, abre el navegador salvo `--no-browser`, y corre uvicorn en `127.0.0.1`. **No hay opción `--host`**: escuchar en otra interfaz no es un default configurable, es una decisión del diseño.

Documentar el comando en el README, junto con por qué la URL lleva un token y por qué no se puede exponer a la red.

- [ ] **Step 4: Verificar**

Run: `python -m pytest -v` y `python -m ruff check .`
Expected: toda la suite verde

- [ ] **Step 5: Commit**

```bash
git add src/promptbrief/cli.py tests/test_cli.py README.md
git commit -m "feat: pbrief serve, token in the URL and loopback only"
```

---

## Verificación final

- [ ] `pytest -v` en verde, y el número real reportado (no forzado)
- [ ] `ruff check .` sin hallazgos
- [ ] CI verde en GitHub, en 3.11 y 3.13
- [ ] `grep -rn "promptbrief.server\|promptbrief.cli" src/promptbrief/core/` no devuelve nada
- [ ] `pbrief serve` levanta, abre el navegador y `GET /api/health` responde con el token
- [ ] La misma URL **sin** el token devuelve 401
- [ ] `POST /api/profiles/scan` con un `root` fuera de la allowlist devuelve 403
- [ ] Ningún commit contiene el trailer `Co-Authored-By`

---

## Después de este plan

**Plan 3 — el front Angular**: componentes standalone y signals, tres pantallas (lista de perfiles, editor con la procedencia visible, generador), servido como estático desde FastAPI. Se escribe cuando la API esté verde, para diseñar los componentes contra endpoints reales y no contra endpoints imaginados.
