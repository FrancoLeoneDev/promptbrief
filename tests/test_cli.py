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


def test_lint_with_a_profile_reaches_the_context_rules(tmp_path, monkeypatch):
    """Sin --profile, la familia C entera era inalcanzable desde lint."""
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    project = tmp_path / "ctx"
    project.mkdir()
    claude = project / "CLAUDE.md"
    claude.write_text(
        "# Ctx\n\n## Convenciones\n\n- El deploy usa AKIAIOSFODNN7EXAMPLE en CI\n",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["scan", str(project)]).exit_code == 0
    claude.write_text("# Ctx\n\n## Convenciones\n\n- El deploy corre en CI\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "lint", "Agregar una sección de Python",
            "--profile", "ctx",
            "--success", "las cards renderizan",
            "--format", "diff",
            "--file", "src/data/portfolio.ts",
            "--constraint", "Resolver sin agregar dependencias.",
        ],
    )
    assert result.exit_code == 0
    assert "secret_redacted" in result.stdout
    assert "stale_profile" in result.stdout


def test_brief_of_a_debug_task_emits_reproduction_and_expected_vs_actual():
    result = runner.invoke(
        app,
        [
            "brief", "El checkout falla al enviar el pedido",
            "--success", "el pedido se envía",
            "--format", "diff",
            "--file", "src/checkout.ts",
            "--repro", "1. Cargar el carrito. 2. Tocar enviar.",
            "--expected", "Esperaba la confirmación; sale un 500.",
        ],
    )
    assert result.exit_code == 0
    assert "<reproduction>" in result.stdout
    assert "1. Cargar el carrito" in result.stdout
    assert "<expected_vs_actual>" in result.stdout
    assert "sale un 500" in result.stdout


def test_brief_of_a_writing_task_emits_every_repeated_example():
    result = runner.invoke(
        app,
        [
            "brief", "Escribir un post para LinkedIn",
            "--success", "suena como yo",
            "--format", "texto plano",
            "--example", "Primer texto de referencia.",
            "--example", "Segundo texto de referencia.",
        ],
    )
    assert result.exit_code == 0
    assert "<examples>" in result.stdout
    assert "Primer texto de referencia." in result.stdout
    assert "Segundo texto de referencia." in result.stdout


def test_repeated_constraints_reach_the_constraints_section():
    result = runner.invoke(
        app,
        [
            "brief", "Agregar una sección de Python",
            "--success", "las cards renderizan",
            "--format", "diff",
            "--file", "src/data/portfolio.ts",
            "--constraint", "Mantener next.config.ts sin cambios.",
            "--constraint", "Resolver sin agregar dependencias.",
        ],
    )
    assert result.exit_code == 0
    assert "<constraints>" in result.stdout
    assert "Mantener next.config.ts sin cambios." in result.stdout
    assert "Resolver sin agregar dependencias." in result.stdout


def test_lint_of_a_debug_task_passes_once_repro_and_expected_are_given():
    """Antes de --repro/--expected, ningún pedido de debug podía salir con 0."""
    result = runner.invoke(
        app,
        [
            "lint", "El checkout falla al enviar el pedido",
            "--success", "el pedido se envía",
            "--format", "diff",
            "--file", "src/checkout.ts",
            "--repro", "1. Cargar el carrito. 2. Tocar enviar.",
            "--expected", "Esperaba la confirmación; sale un 500.",
        ],
    )
    assert result.exit_code == 0
    assert "missing_repro" not in result.stdout
    assert "missing_expected_vs_actual" not in result.stdout


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
