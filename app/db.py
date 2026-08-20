import logging
import os

import oracledb
from fastapi import HTTPException

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
            min=1,
            max=4,
            increment=1,
        )
    except Exception :
        logger.exception("Erro ao criar pool de conexões com o banco de dados.")
        _pool = None
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_conn():
    if _pool is None and init_pool() is None:
        raise HTTPException(status_code=503, detail="Erro ao criar pool de conexões com o banco de dados.")
    with _pool.acquire() as conn:
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
