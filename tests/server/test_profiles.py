import pytest

from .conftest import scan, write_project


def test_the_profile_list_starts_empty(api):
    response = api.get("/api/profiles")
    assert response.status_code == 200
    assert response.json() == []


def test_scan_creates_a_profile_and_the_list_summarises_it(api, tmp_path):
    # El resumen trae name, slot_count y source_count: sin eso la pantalla de lista
    # tendría que pedir cada perfil por separado.
    created = scan(api, write_project(tmp_path))
    assert created.status_code == 200
    assert created.json()["name"] == "proj"

    assert api.get("/api/profiles").json() == [
        {"name": "proj", "slot_count": 1, "source_count": 1}
    ]


def test_two_profiles_both_show_up(api, tmp_path):
    scan(api, write_project(tmp_path, "uno"))
    scan(api, write_project(tmp_path, "dos", body="# Dos\n\n## Convenciones\n\n- Una\n- Otra\n"))

    listed = api.get("/api/profiles").json()
    assert [item["name"] for item in listed] == ["dos", "uno"]
    assert [item["slot_count"] for item in listed] == [2, 1]


@pytest.mark.parametrize("root", ["/etc", "C:/Windows"])
def test_a_root_outside_the_allowlist_is_rejected(api, root):
    response = api.post("/api/profiles/scan", json={"root": root, "name": "ajeno"})
    assert response.status_code == 403
    assert api.get("/api/profiles").json() == []


def test_a_root_that_escapes_with_dotdot_is_rejected(api, tmp_path):
    # tmp_path es la allowlist entera, así que subir un nivel ya está afuera.
    escaping = str(tmp_path / ".." / "afuera")
    response = api.post("/api/profiles/scan", json={"root": escaping, "name": "afuera"})
    assert response.status_code == 403


def test_a_root_that_does_not_exist_is_a_400_not_a_500(api, tmp_path):
    # Está dentro de la allowlist: la guarda de rutas no exige existencia, así que
    # este camino lo tiene que cortar RootNotFound, y eso es culpa del pedido.
    response = api.post("/api/profiles/scan", json={"root": str(tmp_path / "nope")})
    assert response.status_code == 400


def test_a_directory_with_no_known_sources_is_a_400(api, tmp_path):
    empty = tmp_path / "vacio"
    empty.mkdir()
    response = api.post("/api/profiles/scan", json={"root": str(empty)})
    assert response.status_code == 400
    assert api.get("/api/profiles").json() == []


def test_an_explicit_invalid_name_is_a_400(api, tmp_path):
    project = write_project(tmp_path)
    assert scan(api, project, name="with space").status_code == 400
    # Y el mismo 400 cuando el nombre inválido lo aporta la carpeta, sin `name`.
    assert scan(api, write_project(tmp_path, "Personal Page")).status_code == 400


def test_scanning_twice_conflicts_unless_forced(api, tmp_path):
    project = write_project(tmp_path)
    assert scan(api, project).status_code == 200
    assert scan(api, project).status_code == 409
    assert scan(api, project, force=True).status_code == 200


def test_a_profile_round_trips_through_get(api, tmp_path):
    created = scan(api, write_project(tmp_path)).json()

    fetched = api.get("/api/profiles/proj")
    assert fetched.status_code == 200
    assert fetched.json() == created

    slot = fetched.json()["slots"][0]
    assert slot["content"] == "Static export is enabled in next.config.ts"
    assert slot["source"] == {"file": "CLAUDE.md", "line": 5}
    assert fetched.json()["sources"][0]["path"] == "CLAUDE.md"

    # Lo que devuelve GET vuelve a entrar por POST sin traducir nada: es lo que hace
    # la pantalla de edición, y si los dos esquemas se separan, se rompe ahí.
    assert api.post("/api/profiles", json=fetched.json()).status_code == 200


def test_an_unknown_profile_is_a_404(api):
    assert api.get("/api/profiles/nope").status_code == 404


@pytest.mark.parametrize("name", ["with%20space", "CON"])
def test_an_invalid_profile_name_is_a_400_not_a_404(api, name):
    # `..%2Fescape` lo desescapa el router y da 404 sin llegar a la guarda; estos dos
    # sí llegan, así que son los que prueban que el nombre se valida y no se adivina.
    assert api.get(f"/api/profiles/{name}").status_code == 400


def test_a_corrupt_profile_on_disk_is_a_500_not_a_400(lenient, tmp_path):
    # El YAML podrido está en el disco del servidor: el cliente no lo mandó y no lo
    # arregla reenviando otra cosa.
    projects = tmp_path / "home" / "projects"
    projects.mkdir(parents=True)
    (projects / "roto.yml").write_text("- soy una lista", encoding="utf-8")

    assert lenient.get("/api/profiles/roto").status_code == 500


def test_an_edited_profile_can_be_saved(api, tmp_path):
    scan(api, write_project(tmp_path))
    edited = api.get("/api/profiles/proj").json()
    edited["budget_tokens"] = 900
    edited["slots"][0]["content"] = "Editado a mano"

    saved = api.post("/api/profiles", json=edited)
    assert saved.status_code == 200
    assert saved.json()["budget_tokens"] == 900

    stored = api.get("/api/profiles/proj").json()
    assert stored["budget_tokens"] == 900
    assert stored["slots"][0]["content"] == "Editado a mano"


def test_saving_a_profile_that_does_not_exist_is_a_404(api, tmp_path):
    body = {"name": "fantasma", "root": str(tmp_path), "sources": [], "slots": []}
    response = api.post("/api/profiles", json=body)

    # Crear es trabajo de scan: si este endpoint creara, la ruta sin confirmación
    # sería la más destructiva de las dos.
    assert response.status_code == 404
    assert api.get("/api/profiles").json() == []


def test_a_malformed_profile_is_rejected_before_being_written(api, tmp_path):
    scan(api, write_project(tmp_path))
    before = api.get("/api/profiles/proj").json()

    broken = {**before, "slots": [{"id": "x", "kind": "banana", "content": "c"}]}
    assert api.post("/api/profiles", json=broken).status_code == 400
    assert api.get("/api/profiles/proj").json() == before


@pytest.mark.parametrize("root", ["C:/", "/etc"])
def test_a_profile_whose_root_is_outside_the_allowlist_is_rejected(api, tmp_path, root):
    # El agujero del plan v1: sin esta guarda, el cliente guarda un perfil apuntando a
    # cualquier lado y después /api/brief lee y hashea lo que haya ahí.
    scan(api, write_project(tmp_path))
    before = api.get("/api/profiles/proj").json()

    assert api.post("/api/profiles", json={**before, "root": root}).status_code == 403
    assert api.get("/api/profiles/proj").json()["root"] == before["root"]


def test_a_profile_with_an_absolute_source_path_is_rejected(api, tmp_path):
    scan(api, write_project(tmp_path))
    before = api.get("/api/profiles/proj").json()

    poisoned = {**before, "sources": [{"path": "C:/Windows/win.ini", "sha256": "a" * 64}]}
    assert api.post("/api/profiles", json=poisoned).status_code == 400
    assert api.get("/api/profiles/proj").json() == before


@pytest.mark.parametrize("body", [{}, [1, 2], "solo texto"])
def test_an_empty_body_is_a_4xx_not_a_500(api, body):
    for path in ("/api/profiles", "/api/profiles/scan"):
        response = api.post(path, json=body)
        assert 400 <= response.status_code < 500, (path, response.status_code)


def test_a_profile_can_be_deleted(api, tmp_path):
    scan(api, write_project(tmp_path))

    assert api.delete("/api/profiles/proj").status_code == 204
    assert api.get("/api/profiles").json() == []
    assert api.get("/api/profiles/proj").status_code == 404


def test_deleting_an_unknown_profile_is_a_404(api):
    assert api.delete("/api/profiles/nope").status_code == 404


def test_deleting_with_an_invalid_name_is_a_400_not_a_404(api):
    assert api.delete("/api/profiles/CON").status_code == 400
