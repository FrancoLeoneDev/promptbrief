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
