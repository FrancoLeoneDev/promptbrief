from fastapi.testclient import TestClient

from promptbrief.core.errors import ProfileNotFound, StoredProfileCorrupt

# La fixture `api` vive en tests/server/conftest.py: la comparten los cuatro grupos de
# endpoints, y una copia por archivo se desincronizaría con el contrato de create_app.


def test_health_answers(api):
    assert api.get("/api/health").json()["status"] == "ok"


def test_health_still_needs_the_token(api):
    assert TestClient(api.app).get("/api/health").status_code == 401


def test_an_unknown_route_is_a_404(api):
    assert api.get("/api/nope").status_code == 404


def test_a_promptbrief_error_becomes_its_4xx(api):
    @api.app.get("/api/notfound")
    def notfound() -> None:
        raise ProfileNotFound("no existe")

    assert api.get("/api/notfound").status_code == 404


def test_a_stored_corruption_is_a_500_not_a_4xx(api):
    # El caso mixto: hereda de ProfileCorrupt, que sí es 400, pero éste no.
    @api.app.get("/api/rotten")
    def rotten() -> None:
        raise StoredProfileCorrupt("el YAML del servidor está roto")

    lenient = TestClient(api.app, raise_server_exceptions=False)
    lenient.headers.update(api.headers)
    assert lenient.get("/api/rotten").status_code == 500


def test_an_internal_bug_surfaces_as_500(api):
    @api.app.get("/api/boom")
    def boom() -> None:
        raise RuntimeError("bug interno")

    lenient = TestClient(api.app, raise_server_exceptions=False)
    lenient.headers.update(api.headers)
    assert lenient.get("/api/boom").status_code == 500


def test_the_allowlist_reaches_the_app_state(api, tmp_path):
    assert api.app.state.allowed_roots == (tmp_path,)


def test_docs_live_under_api_and_need_the_token(api):
    # Bajo /api para no quedar tapados por FrontendFallback, y por eso mismo exigen el
    # token igual que cualquier otra ruta de la API.
    assert api.get("/api/docs").status_code == 200
    assert TestClient(api.app).get("/api/docs").status_code == 401
