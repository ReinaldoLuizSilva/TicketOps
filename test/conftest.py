import os
from pathlib import Path
from uuid import uuid4

import oracledb
import pytest
from fastapi.testclient import TestClient

_RAIZ = Path(__file__).resolve().parent.parent

def _carregar_env() -> None:
    arquivo = _RAIZ / ".env"
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ[chave.strip()] = valor.strip()


@pytest.fixture(scope="session")
def env():
    _carregar_env()
    os.environ["DB_DSN"] = "localhost:1522/FREEPDB1"

@pytest.fixture(scope="session")
def api(env):
    from app.main import app
    with TestClient(app) as client:
        yield client

@pytest.fixture(scope="session")
def db(env):
    conn = oracledb.connect(
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dsn=os.environ["DB_DSN"],
    )
    with conn:
        yield conn

def novo_email() -> str:
    return f"pytest-{uuid4().hex[:12]}@ticketops.test"

def apagar_cliente(db, cliente_id):
    with db.cursor() as cursor:
        cursor.execute("DELETE FROM comentarios WHERE chamado_id IN (SELECT id FROM chamados WHERE cliente_id = :id)", id=cliente_id)
        cursor.execute("DELETE FROM chamados WHERE cliente_id = :id", id=cliente_id)
        cursor.execute("DELETE FROM clientes WHERE id = :id", id=cliente_id)
    db.commit()

@pytest.fixture
def cliente(api, db):
    response = api.post("/clientes", json={"nome": "Cliente Teste", "email": novo_email()})
    assert response.status_code == 201, response.text
    dados = response.json()
    yield dados
    apagar_cliente(db, dados["ID"])

@pytest.fixture
def chamado(api, cliente):
    response = api.post(
        "/chamados",
        json={
            "cliente_id": cliente["ID"],
            "titulo": "Chamado Teste",
            "descricao": "Descrição do chamado teste",
            "prioridade": 'A',
        },
    )
    assert response.status_code == 201, response.text
    dados = response.json()
    yield dados

@pytest.fixture
def comentario(api, chamado):
    response = api.post(
        f"/chamados/{chamado['ID']}/comentarios",
        json={"autor": "Autor Teste", "texto": "Comentário de teste"},
    )
    assert response.status_code == 201, response.text
    yield response.json()
