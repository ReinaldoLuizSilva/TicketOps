import os

import oracledb

_pool: oracledb.ConnectionPool | None = None


def init_pool() -> oracledb.ConnectionPool:
    global _pool
    if _pool is None:
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
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_conn():
    if _pool is None:
        raise RuntimeError("pool não inicializado — init_pool() deve rodar no lifespan.")
    with _pool.acquire() as conn:
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
