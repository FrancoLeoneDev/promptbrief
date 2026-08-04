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


@pytest.mark.parametrize(
    "path",
    [
        "C:/Windows/win.ini",
        "/etc/passwd",
        "../fuera.md",
        "a/../../b",
        # `PureWindowsPath("\\Windows\\win.ini").is_absolute()` da False: tiene raíz
        # pero no unidad. Sin chequear `.root` además de `is_absolute()`, este path
        # se aceptaba y `root / path` seguía descartando la base.
        "\\Windows\\win.ini",
        # `C:foo` tiene unidad pero no raíz (relativo a la unidad actual). No escapa
        # la base, pero tampoco hay motivo para aceptarlo; lo cubre `.drive`.
        "C:foo",
    ],
)
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


@pytest.mark.parametrize("payload", [[1, 2], None, "una cadena", 5])
def test_profile_from_dict_rejects_a_non_mapping_without_an_attribute_error(payload):
    # La API HTTP que viene en las próximas tareas le pasa a esta función un body JSON
    # directamente. Un array o `null` como body no puede terminar en un 500.
    with pytest.raises(ProfileCorrupt):
        profile_from_dict(payload)


@pytest.mark.parametrize("payload", [[1, 2], None, "una cadena", 5])
def test_slot_from_dict_rejects_a_non_mapping_without_an_attribute_error(payload):
    with pytest.raises(ProfileCorrupt):
        slot_from_dict(payload)


def test_a_provenance_with_a_non_string_file_raises_profile_corrupt():
    payload = {
        "name": "x",
        "root": "/tmp",
        "slots": [
            {
                "id": "a",
                "kind": "stack",
                "content": "c",
                "source": {"file": 5, "line": 12},
            }
        ],
    }
    with pytest.raises(ProfileCorrupt):
        profile_from_dict(payload)


def test_a_provenance_with_a_non_integer_line_raises_profile_corrupt():
    payload = {
        "name": "x",
        "root": "/tmp",
        "slots": [
            {
                "id": "a",
                "kind": "stack",
                "content": "c",
                "source": {"file": "CLAUDE.md", "line": "doce"},
            }
        ],
    }
    with pytest.raises(ProfileCorrupt):
        profile_from_dict(payload)


def test_the_same_validation_protects_the_yaml_path(tmp_path):
    from promptbrief.core.profile.store import load_profile

    (tmp_path / "roto.yml").write_text(
        "name: x\nroot: /tmp\nslots:\n  - solo_una_cadena\n", encoding="utf-8"
    )
    with pytest.raises(ProfileCorrupt):
        load_profile("roto", tmp_path)


def test_a_failed_replace_does_not_leave_an_orphaned_temp_file(tmp_path, monkeypatch):
    # `list_profiles` globea solo `*.yml`, así que un `.tmp` que sobrevive a un
    # `os.replace` fallido queda invisible y solo crece con cada intento fallido.
    import os

    from promptbrief.core.profile.store import save_profile

    def always_fails(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("acceso denegado, simulado")

    monkeypatch.setattr(os, "replace", always_fails)

    profile = Profile(name="demo", root="/tmp", slots=(), sources=())
    with pytest.raises(PermissionError):
        save_profile(profile, tmp_path)

    assert list(tmp_path.glob("*.tmp")) == []


def test_concurrent_writes_never_leave_a_truncated_file(tmp_path):
    # Los endpoints con `def` corren en un threadpool: la concurrencia es real.
    #
    # El tamaño de acá no es arbitrario. Con el tamaño original de este test (200 slots
    # de 500 caracteres, 4 hilos, 20 iteraciones) sabotear `save_profile` a un
    # `write_text` puro (sin temporal ni `os.replace`) solo se ponía rojo 2 de cada 3
    # corridas: la ventana en la que un lector puede abrir el archivo a mitad de una
    # escritura no atómica es demasiado corta para que la contención la encuentre de
    # forma confiable. Medido en esta máquina (Windows, disco local): con un solo slot
    # de 1 500 000 caracteres (~1.5 MB), 4 hilos y 12 iteraciones, el sabotaje se puso
    # rojo 5 de 5 corridas (1-2 errores por corrida, medido con `pytest.raises`
    # reemplazado por un harness que corre el cuerpo del test 5 veces seguidas) y la
    # versión atómica real se mantuvo en 0 errores en 2 corridas de `pytest` seguidas.
    # El costo es real: cada corrida de este test tarda ~50-70s en esta máquina (contra
    # <1s del resto de la suite). Se prefiere una suite más lenta a un guard que no
    # guarda.
    from promptbrief.core.profile.store import load_profile, save_profile

    big = Profile(
        name="demo",
        root="/tmp",
        sources=(),
        slots=(
            Slot(
                id="s0",
                kind=SlotKind.CONVENTION,
                content="x" * 1_500_000,
                applies_to=(),
                source=None,
            ),
        ),
    )
    errors: list[Exception] = []

    def writer() -> None:
        try:
            for _ in range(12):
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
