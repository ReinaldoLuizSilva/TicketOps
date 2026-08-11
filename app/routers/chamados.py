from fastapi import APIRouter, Depends, HTTPException

from app.db import get_conn
from app.schemas import ChamadosCreate, ChamadoUpdate

router = APIRouter()

# Colunas que o cliente pode escrever via PUT, em ordem fixa: o mesmo conjunto de
# campos gera sempre o mesmo texto SQL, e o Oracle reaproveita o cursor.
# data_resolvido fica fora de propósito — é derivada do status, no próprio endpoint.
_COLUNAS_CHAMADO = ("cliente_id", "titulo", "descricao", "prioridade", "status")


@router.get("", status_code=200)
def listar_chamados(conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute("""SELECT
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
                        clientes b ON b.id = a.cliente_id
                    ORDER BY
                        a.id""")
        return [
            {
                "ID": id,
                "CLIENTE_ID": cliente_id,
                "CLIENTE_NOME": cliente_nome,
                "TITULO": titulo,
                "DESCRICAO": descricao.read() if descricao else None,
                "PRIORIDADE": prioridade,
                "STATUS": status,
                "DATA RESOLVIDO": data_resolvido,
            }
            for id, cliente_id, cliente_nome, titulo, descricao, prioridade, status, data_resolvido in cur.fetchall()
        ]


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


@router.put("/{chamado_id}", status_code=204)
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
        cur.execute(
            """SELECT
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
                clientes b ON b.id = a.cliente_id
            WHERE
                a.id = :id""",
            {"id": chamado_id},
        )
        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Chamado não encontrado")
        id, cliente_id, cliente_nome, titulo, descricao, prioridade, status, data_resolvido = result
        return {
            "ID": id,
            "CLIENTE_ID": cliente_id,
            "CLIENTE_NOME": cliente_nome,
            "TITULO": titulo,
            "DESCRICAO": descricao.read() if descricao else None,
            "PRIORIDADE": prioridade,
            "STATUS": status,
            "DATA RESOLVIDO": data_resolvido,
        }
