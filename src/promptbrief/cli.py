from __future__ import annotations

import webbrowser
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

import typer

from promptbrief.core.build import build_brief, lint, resolve_profile
from promptbrief.core.classify import classify
from promptbrief.core.errors import (
    InvalidProfileName,
    NoKnownSources,
    ProfileAlreadyExists,
    PromptBriefError,
    RootNotFound,
)
from promptbrief.core.models import BriefRequest, Finding, Severity
from promptbrief.core.profile.scan import scan_project
from promptbrief.core.profile.store import list_profiles

app = typer.Typer(
    help="Convierte descripciones informales en briefs estructurados para agentes de código."
)

_MARK = {Severity.ERROR: "[error]", Severity.WARNING: "[warn ]", Severity.INFO: "[info ]"}


def _fail(message: str) -> NoReturn:
    """Imprime el error y termina con código 1. Es terminal: se llama sin `raise`."""
    typer.echo(message)
    raise typer.Exit(code=1)


def _build_request(
    text: str,
    profile_name: str | None,
    success: str | None,
    output_format: str | None,
    files: list[str],
    repro: str | None = None,
    expected: str | None = None,
    constraints: list[str] | None = None,
    examples: list[str] | None = None,
) -> BriefRequest:
    profile = None
    if profile_name:
        try:
            profile = resolve_profile(profile_name)
        except PromptBriefError as error:
            _fail(f"{error} Corré 'pbrief profiles' para ver los perfiles disponibles.")
    return BriefRequest(
        text=text,
        task_type=classify(text),
        profile=profile,
        success_criteria=success,
        output_format=output_format,
        file_scope=tuple(files),
        constraints=tuple(constraints or ()),
        examples=tuple(examples or ()),
        repro_steps=repro,
        expected_vs_actual=expected,
    )


def _print_findings(findings: Sequence[Finding]) -> bool:
    """Imprime los hallazgos. Devuelve True si alguno es un error."""
    for finding in findings:
        typer.echo(f"{_MARK[finding.severity]} {finding.rule_id}: {finding.message}")
        typer.echo(f"         -> {finding.suggestion}")
    return any(finding.severity is Severity.ERROR for finding in findings)


@app.command()
def scan(
    path: str = typer.Argument(".", help="Directorio del proyecto"),
    name: str = typer.Option(None, "--name", help="Nombre del perfil (por defecto, la carpeta)"),
    force: bool = typer.Option(False, "--force", help="Sobrescribir un perfil existente"),
) -> None:
    """Destila CLAUDE.md, AGENTS.md, README.md y package.json en un perfil."""
    root = Path(path).resolve()
    try:
        profile, saved = scan_project(root, name=name, force=force)
    except ProfileAlreadyExists as error:
        _fail(
            f"{error} Usá --force para sobrescribirlo "
            "(vas a perder las ediciones manuales del YAML)."
        )
    except InvalidProfileName as error:
        _fail(f"{error} Usá --name para elegir un nombre de perfil válido.")
    except (RootNotFound, NoKnownSources) as error:
        _fail(str(error))

    typer.echo(f"Perfil '{profile.name}' guardado en {saved}")
    typer.echo(f"  {len(profile.slots)} datos desde {len(profile.sources)} archivos")

    needs_review = [slot.label() for slot in profile.slots if slot.needs_review]
    if needs_review:
        typer.echo(
            f"  {len(needs_review)} sin clasificar: no se inyectan. Para que entren hay "
            "que corregirles 'kind' y poner 'needs_review: false' en el YAML del perfil; "
            "con needs_review solo, el dato entra como <unclassified> y aplica a todos "
            "los tipos de tarea."
        )
    redacted = [slot.label() for slot in profile.slots if slot.redacted]
    if redacted:
        typer.echo(f"  credenciales tapadas en: {', '.join(redacted)}")


@app.command()
def profiles() -> None:
    """Lista los perfiles guardados."""
    names = list_profiles()
    if not names:
        typer.echo("No hay perfiles todavía. Corré 'pbrief scan' dentro de un proyecto.")
        return
    for profile_name in names:
        typer.echo(profile_name)


@app.command(
    # El help corto va acá y no sale del docstring: typer imprime el docstring entero
    # en `serve --help`, y el de abajo explica decisiones de diseño que le importan a
    # quien lee el código, no a quien quiere levantar el servidor.
    help="Levanta la API local para el front. Escucha solo en 127.0.0.1."
)
def serve(
    port: int = typer.Option(8765, "--port", help="Puerto local"),
    allow: list[str] = typer.Option(
        [], "--allow", help="Directorio de proyecto permitido (repetible; por defecto, el actual)"
    ),
    no_browser: bool = typer.Option(False, "--no-browser", help="No abrir el navegador"),
) -> None:
    """Levanta la API local que consume el front, con un token nuevo por arranque.

    Escucha únicamente en 127.0.0.1 y **no hay opción `--host`**: el servidor expone el
    disco de la máquina acotado a `--allow`, así que escuchar en otra interfaz no es un
    default configurable, es otro producto. Quien lo necesite, que ponga un túnel
    adelante y decida ahí su propia autenticación.

    El token va en la URL que se imprime porque es la única forma de que el navegador
    lo reciba en la carga inicial del documento; de ahí en más viaja por header. Por
    eso uvicorn corre con `access_log=False`: su log escribe la query string entera, y
    un token en un archivo de log sobrevive a la sesión que lo generó.
    """
    # Importes diferidos: fastapi y uvicorn tardan bastante más en cargar que el resto
    # de la CLI, y ningún otro comando los necesita.
    import uvicorn

    from promptbrief.server.app import create_app
    from promptbrief.server.security import SecurityConfig

    roots = tuple(Path(path).resolve() for path in allow) or (Path.cwd().resolve(),)
    config = SecurityConfig.generate(port)
    url = f"{config.origin}/?token={config.token}"

    typer.echo(f"PromptBrief escuchando en {config.origin}")
    for root in roots:
        typer.echo(f"  proyectos permitidos: {root}")
    typer.echo(f"Abrí esta URL, que lleva el token de la sesión:\n  {url}")
    if not no_browser:
        webbrowser.open(url)

    uvicorn.run(
        create_app(config, allowed_roots=roots),
        host="127.0.0.1",
        port=port,
        access_log=False,
    )


@app.command(name="lint")
def lint_command(
    text: str,
    profile: str = typer.Option(None, "--profile", help="Perfil del proyecto a inyectar"),
    success: str = typer.Option(None, "--success", help="Cuándo la tarea está terminada"),
    output_format: str = typer.Option(None, "--format", help="Qué forma tiene que tener la salida"),
    file: list[str] = typer.Option([], "--file", help="Archivo en el alcance (repetible)"),
    repro: str = typer.Option(None, "--repro", help="Pasos para reproducir el problema"),
    expected: str = typer.Option(None, "--expected", help="Qué esperabas y qué pasa en realidad"),
    constraint: list[str] = typer.Option([], "--constraint", help="Restricción (repetible)"),
    example: list[str] = typer.Option([], "--example", help="Ejemplo de la salida (repetible)"),
) -> None:
    """Analiza un prompt sin generar el brief."""
    request = _build_request(
        text, profile, success, output_format, file, repro, expected, constraint, example
    )
    try:
        findings = lint(request)
    except PromptBriefError as error:
        _fail(str(error))

    if not findings:
        typer.echo("Sin hallazgos.")
        return
    if _print_findings(findings):
        raise typer.Exit(code=1)


@app.command()
def brief(
    text: str,
    profile: str = typer.Option(None, "--profile", help="Perfil del proyecto a inyectar"),
    success: str = typer.Option(None, "--success", help="Cuándo la tarea está terminada"),
    output_format: str = typer.Option(None, "--format", help="Qué forma tiene que tener la salida"),
    file: list[str] = typer.Option([], "--file", help="Archivo en el alcance (repetible)"),
    repro: str = typer.Option(None, "--repro", help="Pasos para reproducir el problema"),
    expected: str = typer.Option(None, "--expected", help="Qué esperabas y qué pasa en realidad"),
    constraint: list[str] = typer.Option([], "--constraint", help="Restricción (repetible)"),
    example: list[str] = typer.Option([], "--example", help="Ejemplo de la salida (repetible)"),
) -> None:
    """Genera el brief y lo imprime."""
    request = _build_request(
        text, profile, success, output_format, file, repro, expected, constraint, example
    )
    try:
        result = build_brief(request)
    except PromptBriefError as error:
        _fail(str(error))

    typer.echo(result.text)
    if result.findings:
        typer.echo("\n---")
        _print_findings(result.findings)


if __name__ == "__main__":
    app()
