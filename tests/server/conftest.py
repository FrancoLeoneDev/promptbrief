import pytest
from fastapi.testclient import TestClient

from promptbrief.server.app import create_app
from promptbrief.server.security import TOKEN_HEADER, SecurityConfig

CONFIG = SecurityConfig(token="t" * 40, port=8765)


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
