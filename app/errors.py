import logging

import oracledb
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_ORA_HTTP = {
    "ORA-00001": (409, "Registro duplicado"),
    "ORA-02291": (400, "Referência informada não existe"),
    "ORA-02292": (409, "Registro possui dependentes e não pode ser excluído"),
    "ORA-12899": (400, "Valor muito grande para o campo"),
    "ORA-01400": (400, "Campo obrigatório não informado"),
    "ORA-02290": (400, "Valor inválido para o campo"),
}


async def oracle_error_handler(request: Request, exc: oracledb.DatabaseError):
    error = exc.args[0]
    full_code = getattr(error, "full_code", None)
    status, detail = _ORA_HTTP.get(full_code, (500, "Erro interno do servidor"))

    logger.error(
        "erro de banco %s %s: %s",
        request.method,
        request.url.path,
        getattr(error, "message", exc),
    )

    return JSONResponse(status_code=status, content={"detail": detail})
