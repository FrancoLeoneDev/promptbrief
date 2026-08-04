import shutil

from .conftest import CLAUDE, scan, write_project


def rewrite(project, body):
    (project / "CLAUDE.md").write_text(body, encoding="utf-8")


def sync(api, name="proj"):
    return api.post(f"/api/profiles/{name}/sync")


def test_a_project_that_did_not_change_reports_everything_as_unchanged(api, tmp_path):
    scan(api, write_project(tmp_path))

    diff = sync(api).json()
    assert [slot["content"] for slot in diff["unchanged"]] == [
        "Static export is enabled in next.config.ts"
    ]
    assert diff["added"] == []
    assert diff["removed"] == []
    assert diff["modified"] == []


def test_an_edited_bullet_comes_back_with_both_sides(api, tmp_path):
    project = write_project(tmp_path)
    scan(api, project)
    rewrite(project, "# Proj\n\n## Convenciones\n\n- Static export is disabled in next.config.ts\n")

    diff = sync(api).json()
    assert len(diff["modified"]) == 1
    change = diff["modified"][0]
    assert change["before"]["content"] == "Static export is enabled in next.config.ts"
    assert change["after"]["content"] == "Static export is disabled in next.config.ts"
    assert change["after"]["source"] == {"file": "CLAUDE.md", "line": 5}
    assert diff["added"] == []
    assert diff["removed"] == []


def test_an_edit_plus_an_addition_under_the_same_heading_is_not_churn(api, tmp_path):
    # El caso que la reconciliación existe para resolver: sin ella, el bullet editado
    # se reporta como un borrado más un agregado y el usuario no ve qué cambió.
    project = write_project(tmp_path)
    scan(api, project)
    rewrite(
        project,
        "# Proj\n\n## Convenciones\n\n"
        "- Static export is disabled in next.config.ts\n"
        "- Los datos del proyecto viven en src/data/\n",
    )

    diff = sync(api).json()
    assert len(diff["modified"]) == 1
    assert diff["modified"][0]["before"]["content"] == "Static export is enabled in next.config.ts"
    assert diff["modified"][0]["after"]["content"] == "Static export is disabled in next.config.ts"
    assert [slot["content"] for slot in diff["added"]] == [
        "Los datos del proyecto viven en src/data/"
    ]
    assert diff["removed"] == []


def test_an_unclosed_fence_surfaces_as_a_modification_needing_review(api, tmp_path):
    # El contenido del bullet no cambió, pero dejó de inyectarse: reportarlo como
    # "sin cambios" escondería justo la consecuencia que importa.
    project = write_project(tmp_path)
    scan(api, project)
    rewrite(project, CLAUDE + "\n```bash\npbrief scan .\n")

    diff = sync(api).json()
    assert diff["unchanged"] == []
    assert len(diff["modified"]) == 1
    change = diff["modified"][0]
    assert change["before"]["needs_review"] is False
    assert change["after"]["needs_review"] is True
    assert change["after"]["content"] == change["before"]["content"]


def test_sync_does_not_write_anything(api, tmp_path):
    project = write_project(tmp_path)
    scan(api, project)
    before = api.get("/api/profiles/proj").json()
    rewrite(project, "# Proj\n\n## Convenciones\n\n- Otra cosa totalmente distinta\n")

    assert sync(api).status_code == 200
    # Es un preview: para aplicarlo el front vuelve a llamar a scan con force=true.
    assert api.get("/api/profiles/proj").json() == before
    assert scan(api, project, force=True).status_code == 200
    assert api.get("/api/profiles/proj").json()["slots"][0]["content"] == (
        "Otra cosa totalmente distinta"
    )


def test_syncing_an_unknown_profile_is_a_404(api):
    assert sync(api, "nope").status_code == 404


def test_syncing_with_an_invalid_name_is_a_400(api):
    assert sync(api, "CON").status_code == 400


def test_a_profile_whose_root_is_outside_the_allowlist_is_a_403(api, tmp_path):
    # Un perfil escrito a mano (o guardado bajo otra allowlist) apunta afuera. Sin la
    # guarda acá, sync destila lo que haya en ese directorio y lo devuelve por HTTP.
    projects = tmp_path / "home" / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    (projects / "ajeno.yml").write_text(
        "name: ajeno\nroot: C:/\nbudget_tokens: 1500\nsources: []\nslots: []\n",
        encoding="utf-8",
    )

    assert sync(api, "ajeno").status_code == 403


def test_a_root_that_disappeared_is_a_400(api, tmp_path):
    project = write_project(tmp_path)
    scan(api, project)
    shutil.rmtree(project)

    # 400 y no un diff con todo en `removed`: el proyecto no se vació, se fue.
    assert sync(api).status_code == 400
