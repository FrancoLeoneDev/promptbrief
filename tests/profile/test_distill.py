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
    bullets = "".join(f"- regla {i}\n" for i in range(MAX_SLOTS_PER_SOURCE + 50))
    text = "## Convenciones\n\n" + bullets
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
