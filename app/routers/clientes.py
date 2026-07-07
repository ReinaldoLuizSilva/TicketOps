from fastapi import APIRouter, FastAPI, Depends, HTTPException
from app.db import get_conn


app = FastAPI()
router = APIRouter()

@router.get("/", status_code=200)
def clienteslist (conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute("SELECT id, nome, email FROM clientes ORDER BY id")
        return [
            {"ID" : id, "NOME" : nome, "EMAIL" : email } for id, nome, email in cur.fetchall()
        ]
