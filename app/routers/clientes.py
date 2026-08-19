from fastapi import APIRouter, Depends, HTTPException

from app.db import get_conn
from app.schemas import ClienteCreate, ClienteOut, ClienteUpdate

router = APIRouter()

_COLUNAS_CLIENTE = ("nome", "email")


@router.get("", status_code=200, response_model=list[ClienteOut])
def listar_clientes(conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute("SELECT id, nome, email FROM clientes ORDER BY id")
        return [{"ID": id, "NOME": nome, "EMAIL": email} for id, nome, email in cur.fetchall()]


@router.post("", status_code=201, response_model=ClienteOut)
def criar_cliente(cliente: ClienteCreate, conn=Depends(get_conn)):
    with conn.cursor() as cur:
        new_id = cur.var(int)
        cur.execute(
            "INSERT INTO clientes (nome, email) VALUES (:nome, :email) RETURNING id INTO :new_id",
            {"nome": cliente.nome, "email": cliente.email, "new_id": new_id},
        )
        conn.commit()
        return {"ID": new_id.getvalue()[0], "NOME": cliente.nome, "EMAIL": cliente.email}


@router.delete("/{cliente_id}", status_code=204)
def excluir_cliente(cliente_id: int, conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM clientes WHERE id = :id", {"id": cliente_id})
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        conn.commit()
        return


@router.patch("/{cliente_id}", status_code=204)
def atualizar_cliente(cliente_id: int, cliente: ClienteUpdate, conn=Depends(get_conn)):
    campos = cliente.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(status_code=400, detail="Nada para atualizar")

    partes = [f"{c} = :{c}" for c in _COLUNAS_CLIENTE if c in campos]
    campos["id"] = cliente_id
    with conn.cursor() as cur:
        cur.execute(f"UPDATE clientes SET {', '.join(partes)} WHERE id = :id", campos)
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        conn.commit()
    return
