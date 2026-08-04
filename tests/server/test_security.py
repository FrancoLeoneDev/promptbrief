import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from promptbrief.core.errors import (
    ProfileAlreadyExists,
    ProfileNotFound,
    PromptBriefError,
    StoredProfileCorrupt,
)
from promptbrief.server.errors import to_http_exception
from promptbrief.server.security import (
    MAX_BODY_BYTES,
    TOKEN_HEADER,
    SecurityConfig,
    install_security,
)

CONFIG = SecurityConfig(token="t" * 40, port=8765)


@pytest.fixture
def client():
    app = FastAPI()

    @app.get("/api/ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    @app.post("/api/echo")
    def echo(payload: dict) -> dict:
        return payload

    install_security(app, CONFIG)
    return TestClient(app)


def auth() -> dict[str, str]:
    return {TOKEN_HEADER: CONFIG.token, "Host": "127.0.0.1:8765"}


def test_a_request_without_a_token_is_rejected(client):
    assert client.get("/api/ping").status_code == 401


def test_a_request_with_the_wrong_token_is_rejected(client):
    assert client.get("/api/ping", headers={TOKEN_HEADER: "adivinado"}).status_code == 401


def test_a_request_with_the_right_token_passes(client):
    assert client.get("/api/ping", headers=auth()).status_code == 200


def test_a_non_ascii_token_is_a_401_not_a_500(client):
    # compare_digest sobre str exige ASCII puro: sin encode esto es un TypeError
    # y un 500 que cualquiera puede disparar sin conocer el token.
    # El valor va en bytes porque httpx se niega a serializar un header str no ASCII
    # (UnicodeEncodeError del lado del cliente); en el cable siempre son bytes igual.
    assert client.get("/api/ping", headers={TOKEN_HEADER: "ñoño".encode()}).status_code == 401
    assert client.get(f"/api/ping?token={'ñ'}").status_code == 401


def test_the_api_does_not_accept_the_token_from_the_query_string(client):
    # Viajaría en el access log de uvicorn y en el historial del navegador.
    assert client.get(f"/api/ping?token={CONFIG.token}").status_code == 401


def test_a_foreign_host_is_rejected_even_with_a_valid_token(client):
    # DNS rebinding: la IP es 127.0.0.1 y no hay Origin, pero el Host delata.
    headers = {TOKEN_HEADER: CONFIG.token, "Host": "evil.example"}
    assert client.get("/api/ping", headers=headers).status_code == 403


def test_localhost_is_accepted_as_host(client):
    headers = {TOKEN_HEADER: CONFIG.token, "Host": "localhost:8765"}
    assert client.get("/api/ping", headers=headers).status_code == 200


def test_a_foreign_origin_is_rejected(client):
    assert client.get(
        "/api/ping", headers={**auth(), "Origin": "https://evil.example"}
    ).status_code == 403


def test_the_own_origin_is_accepted(client):
    assert client.get(
        "/api/ping", headers={**auth(), "Origin": CONFIG.origin}
    ).status_code == 200


def test_a_cross_site_fetch_without_origin_is_rejected(client):
    # Sec-Fetch-Site viaja donde Origin no: <img>, <script>, navegación, no-cors.
    assert client.get(
        "/api/ping", headers={**auth(), "Sec-Fetch-Site": "cross-site"}
    ).status_code == 403


def test_a_same_origin_fetch_passes(client):
    assert client.get(
        "/api/ping", headers={**auth(), "Sec-Fetch-Site": "same-origin"}
    ).status_code == 200


def test_a_request_with_neither_origin_nor_sec_fetch_passes(client):
    # curl y los tests no mandan ninguno de los dos; el token y el Host los cubren.
    assert client.get("/api/ping", headers=auth()).status_code == 200


def test_an_oversized_body_is_rejected(client):
    response = client.post(
        "/api/echo", headers=auth(), content=b'{"x":"' + b"a" * (MAX_BODY_BYTES + 10) + b'"}'
    )
    assert response.status_code == 413


def test_an_oversized_chunked_body_is_rejected_too(client):
    # Sin Content-Length el chequeo del header no ve nada: hay que contar lo que llega.
    def chunks():
        yield b'{"x":"'
        for _ in range((MAX_BODY_BYTES // 1000) + 5):
            yield b"a" * 1000
        yield b'"}'

    assert client.post("/api/echo", headers=auth(), content=chunks()).status_code == 413


def test_a_normal_body_passes(client):
    assert client.post("/api/echo", headers=auth(), json={"x": "corto"}).status_code == 200


def test_a_post_without_a_token_is_rejected_too(client):
    # Los negativos de token no pueden ser todos GET: una guarda que solo cubriera
    # métodos seguros pasaría igual.
    assert client.post("/api/echo", json={"x": "y"}).status_code == 401


def test_the_generated_config_is_unguessable_and_fresh():
    first = SecurityConfig.generate(port=8765)
    assert len(first.token) >= 32
    assert first.origin == "http://127.0.0.1:8765"
    assert SecurityConfig.generate(port=8765).token != first.token


def test_a_short_token_is_refused_at_construction():
    # Un SecurityConfig(token="") abriría el servidor entero.
    with pytest.raises(ValueError):
        SecurityConfig(token="corto", port=8765)


def test_the_error_mapping_covers_the_hierarchy():
    assert to_http_exception(ProfileNotFound("x")).status_code == 404
    assert to_http_exception(ProfileAlreadyExists("x")).status_code == 409
    assert to_http_exception(PromptBriefError("x")).status_code == 400


def test_a_corrupt_profile_on_disk_is_not_the_clients_fault():
    # El cliente no lo mandó ni puede arreglarlo reenviando otra cosa.
    with pytest.raises(TypeError):
        to_http_exception(StoredProfileCorrupt("el YAML del servidor está roto"))


def test_an_internal_error_is_refused_by_the_mapper():
    with pytest.raises(TypeError):
        to_http_exception(RuntimeError("bug interno"))
