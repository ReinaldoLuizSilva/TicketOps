from fastapi import APIRouter, FastAPI, Depends, HTTPException
from app.db import get_conn
from app.schemas import ClienteCreate, ClienteUpdate

app = FastAPI()
router = APIRouter()


@router.get("/", status_code=200)
def clienteslist (conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute("SELECT id, nome, email FROM clientes ORDER BY id")
        return [
            {"ID" : id, "NOME" : nome, "EMAIL" : email } for id, nome, email in cur.fetchall()
        ]

@router.post("/addcliente", status_code=201)
def clientesAdd (cliente: ClienteCreate, conn=Depends(get_conn)):
    with conn.cursor() as cur:
        new_id = cur.var(int)
        cur.execute("INSERT INTO clientes (nome, email) VALUES (:nome, :email) RETURNING id INTO :new_id", {"nome": cliente.nome, "email": cliente.email, "new_id": new_id},)
        conn.commit()
        return{"ID": new_id.getvalue()[0], "NOME": cliente.nome, "EMAIL": cliente.email}
    
@router.delete("/deletecliente/{cliente_id}", status_code=204)
def clientesDel (cliente_id: int, conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM clientes WHERE id = :id", {"id": cliente_id},)
        conn.commit()
        return
    
@router.put("/updatecliente/{cliente_id}", status_code=204)
def clientesUpt (cliente_id: int, cliente: ClienteUpdate, conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute("UPDATE clientes SET nome = :nome, email = :email WHERE id = :id", {"nome": cliente.nome, "email": cliente.email, "id": cliente_id})
        conn.commit()
        return