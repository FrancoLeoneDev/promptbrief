import pytest
from fastapi.testclient import TestClient

from promptbrief.server.app import create_app
from promptbrief.server.frontend import asset_in
from promptbrief.server.security import TOKEN_HEADER

from .conftest import CONFIG

HOST = {"Host": "127.0.0.1:8765"}
AUTH = {**HOST, TOKEN_HEADER: CONFIG.token}


def build(tmp_path, index="<!doctype html><app-root></app-root>"):
    """Un build de mentira: el documento y un bundle con nombre hasheado."""
    dist = tmp_path / "dist" / "browser"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(index, encoding="utf-8")
    (dist / "main-ABC123.js").write_text("console.log('pb')", encoding="utf-8")
    return dist


@pytest.fixture
def web(tmp_path, monkeypatch):
    """Cliente **sin** token: cada test dice cómo lo manda, que es lo que se prueba."""
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    client = TestClient(create_app(CONFIG, allowed_roots=(tmp_path,), web_dist=build(tmp_path)))
    client.headers.update(HOST)
    return client


def test_the_document_loads_with_the_token_in_the_query_string(web):
    # La única forma en que el navegador puede traer el token en la primera carga.
    response = web.get(f"/?token={CONFIG.token}")
    assert response.status_code == 200
    assert "<app-root>" in response.text


def test_the_api_still_refuses_the_token_in_the_query_string(web):
    # La contracara del test de arriba: el permiso del documento no se contagia.
    assert web.get(f"/api/health?token={CONFIG.token}").status_code == 401
    assert web.post(f"/api/lint?token={CONFIG.token}", json={"text": "x"}).status_code == 401


def test_the_api_answers_with_the_token_in_the_header(web):
    assert web.get("/api/health", headers=AUTH).status_code == 200


def test_the_document_without_a_token_explains_where_to_get_one(web):
    response = web.get("/")
    assert response.status_code == 401
    assert "pbrief serve" in response.text


def test_the_document_with_a_wrong_token_is_rejected(web):
    assert web.get("/?token=adivinado").status_code == 401


def test_the_document_also_takes_the_token_from_the_header(web):
    assert web.get("/", headers=AUTH).status_code == 200


def test_index_html_by_name_is_the_document_and_asks_for_the_token(web):
    # Servirlo como un asset más sería la misma página por la puerta de al lado.
    assert web.get("/index.html").status_code == 401
    assert web.get(f"/index.html?token={CONFIG.token}").status_code == 200


def test_a_bundle_is_served_without_a_token(web):
    # El navegador no puede colgarle el query param a los <script> del documento.
    response = web.get("/main-ABC123.js")
    assert response.status_code == 200
    assert "console.log" in response.text


def test_a_client_route_falls_back_to_the_document(web):
    # El router de Angular vive en rutas que el servidor no conoce.
    assert "<app-root>" in web.get(f"/generate?token={CONFIG.token}").text


def test_the_document_is_not_cached(web):
    # Una copia servida del disco del navegador se saltearía la guarda del token.
    assert web.get(f"/?token={CONFIG.token}").headers["cache-control"] == "no-store"


def test_a_traversal_out_of_the_build_is_not_served(web, tmp_path):
    # Con el token puesto, porque sin él el 401 taparía el resultado y el test pasaría
    # aunque el guardarraíl no existiera. `%2f` llega sin normalizar hasta el servidor.
    (tmp_path / "secreto.txt").write_text("credencial", encoding="utf-8")
    response = web.get(f"/..%2f..%2fsecreto.txt?token={CONFIG.token}")
    assert "credencial" not in response.text


def test_a_path_with_backslashes_is_not_an_asset(tmp_path):
    # En Windows `\` es separador: sin esta guarda, `\\host\share` colada por la URL
    # dispara DNS y SMB adentro de resolve(), o sea el hash NTLM de la máquina hacia el
    # host que eligió el atacante. El caso positivo va al lado para que el negativo no
    # pase por el solo hecho de que el archivo no exista.
    dist = build(tmp_path)
    (dist / "sub").mkdir()
    (dist / "sub" / "x.js").write_text("ok", encoding="utf-8")

    assert asset_in(dist, "sub/x.js") is not None
    assert asset_in(dist, "sub\\x.js") is None
    assert asset_in(dist, "\\\\host\\share\\x.js") is None


def test_an_unknown_api_route_stays_a_404_and_does_not_become_the_front(web):
    response = web.get("/api/nope", headers=AUTH)
    assert response.status_code == 404
    assert "<app-root>" not in response.text


def test_a_foreign_host_is_rejected_before_the_front_answers(web):
    # El rebinding tiene que rebotar también contra el documento, no solo contra la API.
    assert web.get(f"/?token={CONFIG.token}", headers={"Host": "evil.example"}).status_code == 403


def test_without_a_build_the_document_says_how_to_generate_it(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    app = create_app(CONFIG, allowed_roots=(tmp_path,), web_dist=tmp_path / "sin-build")
    client = TestClient(app)
    client.headers.update(HOST)

    response = client.get(f"/?token={CONFIG.token}")
    assert response.status_code == 503
    assert "npm run build" in response.text


def test_without_a_build_the_api_keeps_working(tmp_path, monkeypatch):
    # El front es opcional: la CLI y la API no dependen de que alguien haya compilado.
    monkeypatch.setenv("PROMPTBRIEF_HOME", str(tmp_path / "home"))
    app = create_app(CONFIG, allowed_roots=(tmp_path,), web_dist=tmp_path / "sin-build")
    client = TestClient(app)
    client.headers.update(AUTH)

    assert client.get("/api/health").status_code == 200
