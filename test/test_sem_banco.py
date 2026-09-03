from fastapi.testclient import TestClient

from app import db
from app.main import app

_DSN_INALCANCAVEL = "127.0.0.1:1/ticketops"


def test_sem_banco_health(monkeypatch):
    """DSN que nem parseia: o create_pool estoura e o init_pool tolerante devolve
    None. É o caminho do 503 que o M3 construiu."""
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setenv("DB_USER", "ticketops")
    monkeypatch.setenv("DB_PASSWORD", "ticketops")
    monkeypatch.setenv("DB_DSN", "invalido")

    with TestClient(app) as client:
        assert db._pool is None
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert client.get("/chamados").status_code == 503
        assert client.get("/dashboard").status_code == 503


def test_sem_banco_falha_no_acquire(monkeypatch):
    """DSN que parseia mas não responde: com min=0 o pool é criado com sucesso e a
    falha aparece no acquire(). Sem o try/except do get_conn isto seria 500."""
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setenv("DB_USER", "ticketops")
    monkeypatch.setenv("DB_PASSWORD", "ticketops")
    monkeypatch.setenv("DB_DSN", _DSN_INALCANCAVEL)

    with TestClient(app) as client:
        assert db._pool is not None, "com min=0 o create_pool não devia ter falhado"
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert client.get("/chamados").status_code == 503
        assert client.get("/dashboard").status_code == 503
