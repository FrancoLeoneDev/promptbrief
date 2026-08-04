import pytest

from .conftest import scan, write_project

# Cuatro slots elegidos para que cada uno caiga en un bucket distinto de la selección:
# uno entra, uno no aplica al tipo de tarea, uno está sin clasificar y el cuarto no
# entra en el presupuesto. Con `budget_tokens: 22` el primero cuesta exactamente 22 y
# el último ya no tiene lugar.
BUCKET_SLOTS = [
    {
        "id": "selected-one",
        "kind": "convention",
        "content": "Los datos del proyecto viven en src/data/",
        "applies_to": ["code_change"],
    },
    {
        "id": "writing-only",
        "kind": "convention",
        "content": "El tono del blog es informal",
        "applies_to": ["writing"],
    },
    {
        "id": "needs-review",
        "kind": "unclassified",
        "content": "Algo que quedo sin clasificar",
        "needs_review": True,
    },
    {
        "id": "too-big",
        "kind": "convention",
        "content": "Otra convencion larga que no entra en el presupuesto",
        "applies_to": ["code_change"],
    },
]


def edited_profile(api, tmp_path, **changes):
    """Un perfil escaneado y después editado por `POST /api/profiles`."""
    scan(api, write_project(tmp_path))
    profile = api.get("/api/profiles/proj").json()
    profile.update(changes)
    assert api.post("/api/profiles", json=profile).status_code == 200
    return profile


def foreign_profile(tmp_path, name="ajeno"):
    """Un perfil escrito a mano cuyo root apunta fuera de la allowlist."""
    projects = tmp_path / "home" / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    (projects / f"{name}.yml").write_text(
        f"name: {name}\nroot: C:/\nbudget_tokens: 1500\nsources: []\nslots: []\n",
        encoding="utf-8",
    )
    return name


def rule_ids(payload):
    return [finding["rule_id"] for finding in payload["findings"]]


def test_a_brief_without_a_profile_still_renders(api):
    response = api.post("/api/brief", json={"text": "Agregar una seccion de Python"})
    assert response.status_code == 200

    body = response.json()
    assert "<task>" in body["text"]
    assert "Agregar una seccion de Python" in body["text"]
    assert "missing_success_criteria" in rule_ids(body)
    assert body["selection"]["selected"] == []


def test_a_brief_with_a_profile_injects_the_context_with_its_provenance(api, tmp_path):
    scan(api, write_project(tmp_path))
    body = api.post(
        "/api/brief",
        json={
            "text": "Agregar una seccion de Python",
            "profile_name": "proj",
            "success_criteria": "las cards renderizan",
            "output_format": "diff",
            "file_scope": ["src/data/portfolio.ts"],
            "constraints": ["Resolver sin agregar dependencias."],
        },
    ).json()

    assert (
        '<convention source="CLAUDE.md:5">Static export is enabled in '
        "next.config.ts</convention>"
    ) in body["text"]
    assert [slot["content"] for slot in body["selection"]["selected"]] == [
        "Static export is enabled in next.config.ts"
    ]
    assert body["selection"]["selected"][0]["source"] == {"file": "CLAUDE.md", "line": 5}


def test_the_selection_reports_every_bucket_at_once(api, tmp_path):
    # El caso mixto: cuatro slots, cuatro destinos distintos en la misma respuesta.
    # Probar solo "todo entra" y "no entra nada" deja sin cubrir el medio.
    edited_profile(api, tmp_path, budget_tokens=22, slots=BUCKET_SLOTS)
    body = api.post(
        "/api/brief",
        json={
            "text": "Agregar los datos del portfolio",
            "profile_name": "proj",
            "success_criteria": "las cards renderizan",
            "output_format": "diff",
            "file_scope": ["src/data/portfolio.ts"],
        },
    ).json()

    selection = body["selection"]
    assert [slot["id"] for slot in selection["selected"]] == ["selected-one"]
    assert [slot["id"] for slot in selection["over_budget"]] == ["too-big"]
    assert [slot["id"] for slot in selection["not_applicable"]] == ["writing-only"]
    assert [slot["id"] for slot in selection["skipped_for_review"]] == ["needs-review"]
    assert body["dropped_slots"] == ["too-big"]


def test_a_low_budget_saved_by_the_profile_endpoint_reaches_budget_exceeded(api, tmp_path):
    # Es la única forma de alcanzar esta regla desde la API: si el arreglo de la
    # allowlist rompiera el guardado de perfiles editados, este test lo dice.
    edited_profile(api, tmp_path, budget_tokens=22, slots=BUCKET_SLOTS)
    body = api.post(
        "/api/brief",
        json={
            "text": "Agregar los datos del portfolio",
            "profile_name": "proj",
            "success_criteria": "las cards renderizan",
            "output_format": "diff",
            "file_scope": ["src/data/portfolio.ts"],
        },
    ).json()

    assert "budget_exceeded" in rule_ids(body)


def test_the_response_carries_the_task_type_resolved_by_the_server(api):
    body = api.post("/api/brief", json={"text": "El checkout falla al enviar el pedido"}).json()
    # El front no reimplementa el clasificador: lo lee de acá.
    assert body["task_type"] == "debug"


def test_findings_name_the_field_they_guard_and_leave_the_rest_null(api):
    body = api.post("/api/brief", json={"text": "arreglalo"}).json()
    by_rule = {finding["rule_id"]: finding["slot_name"] for finding in body["findings"]}

    assert by_rule["missing_success_criteria"] == "success_criteria"
    assert by_rule["missing_output_format"] == "output_format"
    # dangling_reference habla del texto entero, no de un campo del formulario.
    assert by_rule["dangling_reference"] is None


def test_forcing_the_task_type_changes_which_rules_apply(api):
    body = api.post(
        "/api/brief",
        json={"text": "Agregar una seccion de Python", "task_type": "debug"},
    ).json()

    assert body["task_type"] == "debug"
    assert "missing_repro" in rule_ids(body)


def test_an_invalid_task_type_is_a_422_not_a_500(api):
    response = api.post("/api/brief", json={"text": "hacer la cosa", "task_type": "inventado"})
    assert response.status_code == 422


def test_an_empty_text_is_a_400(api):
    assert api.post("/api/brief", json={"text": "   "}).status_code == 400
    assert api.post("/api/lint", json={"text": "   "}).status_code == 400


def test_an_unknown_profile_is_a_404(api):
    response = api.post("/api/brief", json={"text": "hacer la cosa", "profile_name": "nope"})
    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/api/brief", "/api/lint"])
def test_a_stored_profile_pointing_outside_the_allowlist_is_a_403(api, tmp_path, path):
    # Sin esto, build_brief sigue el root del perfil por su cuenta y stale_sources
    # hashea lo que haya ahí: un oráculo de existencia de archivos, y sin tope.
    name = foreign_profile(tmp_path)
    response = api.post(path, json={"text": "hacer la cosa", "profile_name": name})
    assert response.status_code == 403


@pytest.mark.parametrize("path", ["/api/brief", "/api/lint"])
def test_an_inline_profile_pointing_outside_the_allowlist_is_a_403(api, path):
    # La misma puerta, sin pasar por el disco: el perfil viaja en el body.
    response = api.post(
        path,
        json={
            "text": "hacer la cosa",
            "profile": {"name": "ajeno", "root": "C:/", "sources": [], "slots": []},
        },
    )
    assert response.status_code == 403


def test_lint_returns_the_same_findings_as_brief_without_the_text(api, tmp_path):
    scan(api, write_project(tmp_path))
    payload = {
        "text": "Agregar una seccion de Python",
        "profile_name": "proj",
        "success_criteria": "las cards renderizan",
        "file_scope": ["src/data/portfolio.ts"],
    }

    brief = api.post("/api/brief", json=payload).json()
    linted = api.post("/api/lint", json=payload).json()

    assert "text" not in linted
    assert linted["task_type"] == brief["task_type"]
    assert linted["findings"] == brief["findings"]
    assert "missing_output_format" in rule_ids(linted)


def test_lint_with_a_profile_reaches_the_context_rules(api, tmp_path):
    # Sin perfil, la familia C entera es inalcanzable desde lint.
    project = write_project(
        tmp_path,
        body="# Ctx\n\n## Convenciones\n\n- El deploy usa AKIAIOSFODNN7EXAMPLE en CI\n",
    )
    scan(api, project)

    linted = api.post(
        "/api/lint",
        json={
            "text": "Agregar una seccion de Python",
            "profile_name": "proj",
            "success_criteria": "las cards renderizan",
            "output_format": "diff",
            "file_scope": ["src/data/portfolio.ts"],
            "constraints": ["Resolver sin agregar dependencias."],
        },
    ).json()

    assert "secret_redacted" in rule_ids(linted)
