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
