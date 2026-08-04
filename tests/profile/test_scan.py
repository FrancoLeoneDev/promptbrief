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
