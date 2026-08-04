import sys
from pathlib import Path

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

    def spy(self, *args, **kwargs):
        resolved.append(self)
        return original(self)

    monkeypatch.setattr(Path, "resolve", spy)

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
