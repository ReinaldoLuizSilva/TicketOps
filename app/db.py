import os
import oracledb

pool = oracledb.create_pool (
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    dsn=os.environ["DB_DSN"]
)

def get_conn ():
    with pool.acquire() as conn:
        yield conn