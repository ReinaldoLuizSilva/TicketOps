from fastapi.testclient import TestClient

from app import db
from app.main import app

def test_sem_banco_health(monkeypatch):
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setenv("DB_USER", "ticketops")
    monkeypatch.setenv("DB_PASSWORD", "ticketops")
    monkeypatch.setenv("DB_DSN", "invalido")

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/chamados").status_code == 503