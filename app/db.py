import logging
import os

import oracledb
from fastapi import HTTPException

_POOL_MIN = 0
_POOL_MAX = 4

_INDISPONIVEL = "Banco de dados indisponível"

_pool: oracledb.ConnectionPool | None = None
logger = logging.getLogger(__name__)

def init_pool() -> oracledb.ConnectionPool | None:
    global _pool
    if _pool is not None:
        return _pool
    try:
        _pool = oracledb.create_pool(
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            dsn=os.environ["DB_DSN"],
            config_dir=os.environ.get("DB_CONFIG_DIR"),
            wallet_location=os.environ.get("DB_WALLET_LOCATION"),
            wallet_password=os.environ.get("DB_WALLET_PASSWORD"),
            min=_POOL_MIN,
            max=_POOL_MAX,
            increment=1,
        )
    except Exception:
        # WARNING, não ERROR: dependência externa fora não é bug do projeto, e um filtro por
        # severity>=ERROR deve devolver só o que precisa de correção aqui. Quem vigia o 503
        # é o alerta de 5xx. exc_info mantém o traceback inteiro numa entrada só.
        logger.warning(
            "banco indisponível: falha ao criar o pool de conexões",
            exc_info=True,
            extra={"evento": "pool_indisponivel"},
        )
        _pool = None
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_conn():
    pool = _pool if _pool is not None else init_pool()
    if pool is None:
        logger.warning(
            "requisição rejeitada: pool de conexões indisponível",
            extra={"evento": "pool_indisponivel"},
        )
        raise HTTPException(status_code=503, detail=_INDISPONIVEL)

    try:
        conn = pool.acquire()
    except oracledb.DatabaseError:
        logger.warning(
            "requisição rejeitada: falha ao obter conexão do pool",
            exc_info=True,
            extra={"evento": "acquire_falhou"},
        )
        raise HTTPException(status_code=503, detail=_INDISPONIVEL) from None

    with conn:
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
