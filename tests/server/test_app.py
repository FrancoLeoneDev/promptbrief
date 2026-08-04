import pytest
from fastapi.testclient import TestClient

from promptbrief.core.errors import ProfileNotFound, StoredProfileCorrupt
from promptbrief.server.app import create_app
from promptbrief.server.security import TOKEN_HEADER, SecurityConfig

CONFIG = SecurityConfig(token="t" * 40, port=8765)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    client = TestClient(create_app(CONFIG, allowed_roots=(tmp_path,)))
    client.headers.update({TOKEN_HEADER: CONFIG.token, "Host": "127.0.0.1:8765"})
    return client


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
