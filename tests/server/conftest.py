import pytest
from fastapi.testclient import TestClient

from promptbrief.server.app import create_app
from promptbrief.server.security import TOKEN_HEADER, SecurityConfig

CONFIG = SecurityConfig(token="t" * 40, port=8765)

CLAUDE = "# Proj\n\n## Convenciones\n\n- Static export is enabled in next.config.ts\n"


def write_project(tmp_path, folder="proj", body=CLAUDE):
    """Un proyecto mínimo con un CLAUDE.md destilable. El bullet cae en la línea 5."""
    project = tmp_path / folder
    project.mkdir(parents=True, exist_ok=True)
    (project / "CLAUDE.md").write_text(body, encoding="utf-8")
    return project


def scan(api, project, **extra):
    return api.post("/api/profiles/scan", json={"root": str(project), **extra})


@pytest.fixture
def api(tmp_path, monkeypatch):
    """Cliente autenticado contra una app cuya allowlist es `tmp_path`.

    Vive en el conftest y no en cada archivo porque son cuatro los grupos de endpoints
    que la usan: una copia por archivo se desincroniza en cuanto cambie el contrato de
    `create_app`.
    """
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    client = TestClient(create_app(CONFIG, allowed_roots=(tmp_path,)))
    client.headers.update({TOKEN_HEADER: CONFIG.token, "Host": "127.0.0.1:8765"})
    return client


@pytest.fixture
def lenient(api):
    """El mismo cliente, pero un 500 llega como respuesta en vez de propagarse.

    Es la única forma de afirmar sobre el status de un error de servidor: con el
    TestClient por defecto la excepción se re-lanza y el test nunca ve la respuesta.
    """
    client = TestClient(api.app, raise_server_exceptions=False)
    client.headers.update(api.headers)
    return client
