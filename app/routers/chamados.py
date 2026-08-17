from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_conn
from app.schemas import ChamadosCreate, ChamadoUpdate

router = APIRouter()

# Colunas que o cliente pode escrever via PUT, em ordem fixa: o mesmo conjunto de
# campos gera sempre o mesmo texto SQL, e o Oracle reaproveita o cursor.
# data_resolvido fica fora de propósito — é derivada do status, no próprio endpoint.
_COLUNAS_CHAMADO = ("cliente_id", "titulo", "descricao", "prioridade", "status")
_SELECT_CHAMADO = """SELECT
                        a.id,
                        a.cliente_id,
                        b.nome,
                        a.titulo,
                        a.descricao,
                        a.prioridade,
                        a.status,
                        a.data_resolvido
                    FROM
                        chamados a
                    JOIN
                        clientes b ON b.id = a.cliente_id"""

def _row_to_dict(row) -> dict:
    id, cliente_id, cliente_nome, titulo, descricao, prioridade, status, data_resolvido = row
    return{
        "ID": id,
        "CLIENTE_ID": cliente_id,
        "CLIENTE_NOME": cliente_nome,
        "TITULO": titulo,
        "DESCRICAO": descricao.read() if descricao else None,
        "PRIORIDADE": prioridade,
        "STATUS": status,
        "DATA_RESOLVIDO": data_resolvido,
    }

@router.get("", status_code=200)
def c(
    status: Literal["A", "E", "R", "C"] | None = Query(
        default= None,
        description="Filtra por status: A = Aberto, E = Em andamento, R = Resolvido, C = Calcelado"
    ),
    conn = Depends(get_conn),
):
    sql = _SELECT_CHAMADO
    params = {}
    if status:
        sql += " WHERE a.status = :status"
        params["status"] = status
    sql += " ORDER BY a.id"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return[_row_to_dict(row) for row in cur.fetchall()]

@router.post("", status_code=201)
def criar_chamado(chamado: ChamadosCreate, conn=Depends(get_conn)):
    with conn.cursor() as cur:
        new_id = cur.var(int)
        cur.execute(
            "INSERT INTO chamados (cliente_id, titulo, descricao, prioridade) "
            "VALUES (:cliente_id, :titulo, :descricao, :prioridade) "
            "RETURNING id INTO :new_id",
            {
                "cliente_id": chamado.cliente_id,
                "titulo": chamado.titulo,
                "descricao": chamado.descricao,
                "prioridade": chamado.prioridade,
                "new_id": new_id,
            },
        )
        conn.commit()
        return {
            "ID": new_id.getvalue()[0],
            "CLIENTE": chamado.cliente_id,
            "TITULO": chamado.titulo,
            "DESCRICAO": chamado.descricao,
            "PRIORIDADE": chamado.prioridade,
        }


@router.delete("/{chamado_id}", status_code=204)
def excluir_chamado(chamado_id: int, conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chamados WHERE id = :id", {"id": chamado_id})
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Chamado não encontrado")
        conn.commit()
        return


@router.patch("/{chamado_id}", status_code=204)
def atualizar_chamado(chamado_id: int, chamado: ChamadoUpdate, conn=Depends(get_conn)):
    campos = chamado.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(status_code=400, detail="Nada para atualizar")

    partes = [f"{c} = :{c}" for c in _COLUNAS_CHAMADO if c in campos]

    if "status" in campos:
        if campos["status"] == "R":
            partes.append("data_resolvido = NVL(data_resolvido, SYSTIMESTAMP)")
        else:
            partes.append("data_resolvido = NULL")

    campos["id"] = chamado_id
    with conn.cursor() as cur:
        cur.execute(f"UPDATE chamados SET {', '.join(partes)} WHERE id = :id", campos)
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Chamado não encontrado")
        conn.commit()
    return


@router.get("/{chamado_id}", status_code=200)
def obter_chamado(chamado_id: int, conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute(_SELECT_CHAMADO + " WHERE a.id = :id", {"id": chamado_id})
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chamado não encontrado")
        return _row_to_dict(row)