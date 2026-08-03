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
