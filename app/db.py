import os
import oracledb

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = oracledb.create_pool(
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            dsn=os.environ["DB_DSN"],
            min=1, max=4, increment=1,
        )
    return _pool

def get_conn():
    with get_pool().acquire() as conn:
        yield conn