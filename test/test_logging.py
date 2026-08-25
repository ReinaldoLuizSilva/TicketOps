import io
import json
import logging
import sys

from fastapi.testclient import TestClient

from app import db, logging_config
from app.logging_config import FormatterCloudLogging
from app.main import app


def _registro(nivel=logging.INFO, msg="mensagem de teste", exc_info=None, **extra):
    record = logging.LogRecord(
        "app.teste", nivel, "/app/app/teste.py", 42, msg, (), exc_info, func="funcao"
    )
    record.__dict__.update(extra)
    return record

def test_formatter_emite_json_severity():
    entrada = json.loads(FormatterCloudLogging().format(_registro(logging.WARNING, "conexões")))

    assert entrada["severity"] == "WARNING"
    assert entrada["message"] == "conexões"
    assert entrada["logger"] == "app.teste"
    assert entrada["logging.googleapis.com/sourceLocation"]["line"] == 42
    assert "level" not in entrada

def test_formatter_mantem_traceback_em_uma_entrada():
    try:
        raise ValueError("falha simulada")
    except ValueError:
        registro = _registro(logging.ERROR, "erro ao criar pool", exc_info=sys.exc_info())

    linha = FormatterCloudLogging().format(registro)

    assert "\n" not in linha
    entrada = json.loads(linha)
    assert "Traceback (most recent call last)" in entrada["message"]
    assert "ValueError: falha simulada" in entrada["message"]

def test_formatter_leva_extra_para_o_payload():
    entrada = json.loads(
        FormatterCloudLogging().format(
            _registro(ora="ORA-00001", rota="/clientes", metodo="POST")
        )
    )

    assert entrada["ora"] == "ORA-00001"
    assert entrada["rota"] == "/clientes"
    assert entrada["metodo"] == "POST"

def test_trace_do_header_chega_na_linha_de_log(monkeypatch):
    monkeypatch.setattr(logging_config, "_PROJETO", "ticketops-teste")
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setenv("DB_USER", "ticketops")
    monkeypatch.setenv("DB_PASSWORD", "ticketops")
    monkeypatch.setenv("DB_DSN", "invalido")

    fluxo = io.StringIO()
    handler = logging.StreamHandler(fluxo)
    handler.setFormatter(FormatterCloudLogging())
    logger = logging.getLogger("app.db")
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)

    trace = "4bf92f3577b34da6a3ce929d0e0e4736"
    try:
        with TestClient(app) as client:
            resposta = client.get("/chamados", headers={"X-Cloud-Trace-Context": f"{trace}/1;o=1"})
    finally:
        logger.removeHandler(handler)

    assert resposta.status_code == 503

    entradas = [json.loads(linha) for linha in fluxo.getvalue().splitlines() if linha.strip()]
    esperado = f"projects/ticketops-teste/traces/{trace}"
    assert any(e.get("logging.googleapis.com/trace") == esperado for e in entradas)
