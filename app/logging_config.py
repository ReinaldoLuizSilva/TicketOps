import json
import logging
import os
import sys
from contextvars import ContextVar

trace_atual: ContextVar[str | None] = ContextVar("trace_atual", default=None)

_PROJETO = os.environ.get("GCP_PROJECT", "")
_REVISAO = os.environ.get("K_REVISION", "")

_PADRAO = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}

class FormatterCloudLogging(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entrada = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "logging.googleapis.com/sourceLocation": {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName
            },
        }

        if record.exc_info:
            entrada["message"] += "\n" + self.formatException(record.exc_info)

        trace = trace_atual.get()
        if trace and _PROJETO:
            entrada["logging.googleapis.com/trace"] = f"projects/{_PROJETO}/traces/{trace}"

        if _REVISAO:
            entrada["logging.googleapis.com/labels"] = {"revision": _REVISAO}

        entrada.update({k: v for k, v in record.__dict__.items() if k not in _PADRAO})

        return json.dumps(entrada, ensure_ascii=False, default=str)

def configurar_logging() -> None:
    if os.environ.get("LOG_FORMAT", "json").lower() != "json":
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(FormatterCloudLogging())

    for nome in ("","uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(nome)
        logger.handlers = [handler]
        logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
