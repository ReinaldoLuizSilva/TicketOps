from fastapi import APIRouter, Depends, HTTPException
#from app.db import get_conn
#from app.schemas import ChamadoIn, ChamadoOut

router = APIRouter()

"""
@router.post("", response_model=ChamadoOut, status_code=201)
def abrir_chamado(payload: ChamadoIn, conn=Depends(get_conn)):
    with conn.cursor() as cur:
        novo_id = cur.var(int)

        cur.execute(
            
            
            
        )
        conn.commit()
    return buscar_chamado
"""
