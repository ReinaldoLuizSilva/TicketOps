from typing import Literal

import oracledb
from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_conn
from app.schemas import (
    ChamadoDetalhe,
    ChamadoOut,
    ChamadosCreate,
    ChamadoUpdate,
    ComentarioCreate,
    ComentarioCriado,
)

router = APIRouter()

_COLUNAS_CHAMADO = ("cliente_id", "titulo", "descricao", "prioridade", "status")
_SELECT_CHAMADO = """SELECT
                        a.id,
                        a.cliente_id,
                        b.nome,
                        a.titulo,
                        a.descricao,
                        a.prioridade,
                        a.status,
                        a.data_resolvido,
                        a.created
                    FROM
                        chamados a
                    JOIN
                        clientes b ON b.id = a.cliente_id"""

_SELECT_COMENTARIOS = """SELECT
                            id,
                            autor,
                            texto,
                            created
                        FROM
                            comentarios
                        WHERE
                            chamado_id = :chamado_id
                        ORDER BY
                            id"""

def _row_to_dict(row) -> dict:
    id, cliente_id, cliente_nome, titulo, descricao, prioridade, status, data_resolvido, created = row
    return{
        "ID": id,
        "CLIENTE_ID": cliente_id,
        "CLIENTE_NOME": cliente_nome,
        "TITULO": titulo,
        "DESCRICAO": descricao.read() if descricao else None,
        "PRIORIDADE": prioridade,
        "STATUS": status,
        "DATA_RESOLVIDO": data_resolvido,
        "CRIADO_EM": created,
    }

@router.get("", status_code=200, response_model=list[ChamadoOut])
def listar_chamados(
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

@router.post("", status_code=201, response_model=ChamadoOut)
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
        cur.execute(_SELECT_CHAMADO + " WHERE a.id = :id", {"id": new_id.getvalue()[0]})
        return _row_to_dict(cur.fetchone())

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


@router.get("/{chamado_id}", status_code=200, response_model=ChamadoDetalhe)
def obter_chamado(chamado_id: int, conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute(_SELECT_CHAMADO + " WHERE a.id = :id", {"id": chamado_id})
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chamado não encontrado")
        chamado = _row_to_dict(row)

        cur.execute(_SELECT_COMENTARIOS, {"chamado_id": chamado_id})
        chamado["COMENTARIOS"] = [
            {
                "ID": id,
                "AUTOR": autor,
                "TEXTO": texto.read() if texto else None,
                "CRIADO_EM": created,
            }
            for id, autor, texto, created in cur.fetchall()
        ]
        return chamado

@router.post("/{chamado_id}/comentarios", status_code=201, response_model=ComentarioCriado)
def criar_comentario(chamado_id: int, comentario: ComentarioCreate, conn=Depends(get_conn)):
    with conn.cursor() as cur:
        new_id = cur.var(int)
        new_created = cur.var(oracledb.DB_TYPE_TIMESTAMP)
        try:
            cur.execute(
                "INSERT INTO comentarios (chamado_id, autor, texto) "
                "VALUES (:chamado_id, :autor, :texto) "
                "RETURNING id, created INTO :new_id, :new_created",
                {
                    "chamado_id": chamado_id,
                    "autor": comentario.autor,
                    "texto": comentario.texto,
                    "new_id": new_id,
                    "new_created": new_created,
                },
            )
        except oracledb.IntegrityError as exc:
            if getattr(exc.args[0], "full_code", None) == "ORA-02291":
                raise HTTPException(status_code=404, detail="Chamado não encontrado") from exc
            raise
        conn.commit()
    return{
        "ID": new_id.getvalue()[0],
        "CHAMADO_ID": chamado_id,
        "AUTOR": comentario.autor,
        "TEXTO": comentario.texto,
        "CRIADO_EM": new_created.getvalue()[0]
    }
