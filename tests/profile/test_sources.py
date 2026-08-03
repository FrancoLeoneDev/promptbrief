import hashlib
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


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin on Windows")
def test_read_source_refuses_to_follow_a_symlink(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("id_rsa contents", encoding="utf-8")
    link = tmp_path / "CLAUDE.md"
    link.symlink_to(secret)
    assert read_source(link) is None


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


def test_hash_file_chunking_matches_a_whole_file_digest(tmp_path):
    path = tmp_path / "CLAUDE.md"
    # Más grande que el tamaño de chunk (64 KB) para forzar varias vueltas del loop.
    content = b"abcdefgh" * 20_000
    path.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert hash_file(path) == expected


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
