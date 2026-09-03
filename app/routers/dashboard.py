from fastapi import APIRouter, Depends

from app.db import get_conn
from app.schemas import DashboardOut

router = APIRouter()

_SELECT_DASHBOARD = """SELECT
                            COUNT(*),
                            COUNT(CASE WHEN status = 'A' THEN 1 END),
                            COUNT(CASE WHEN status = 'E' THEN 1 END),
                            COUNT(CASE WHEN status = 'R' THEN 1 END),
                            COUNT(CASE WHEN status = 'C' THEN 1 END),
                            COUNT(CASE WHEN prioridade = 'B' THEN 1 END),
                            COUNT(CASE WHEN prioridade = 'M' THEN 1 END),
                            COUNT(CASE WHEN prioridade = 'A' THEN 1 END),
                            COUNT(CASE WHEN prioridade = 'C' THEN 1 END),
                            ROUND(AVG(CASE WHEN status = 'R'
                                           THEN (CAST(data_resolvido AS DATE) - CAST(created AS DATE)) * 24
                                      END), 2)
                        FROM
                            chamados"""


@router.get("", status_code=200, response_model=DashboardOut)
def dashboard(conn=Depends(get_conn)):
    """Estatísticas do atendimento: total de chamados, contagem por status e por prioridade,
    e o tempo médio de resolução em horas."""
    with conn.cursor() as cur:
        cur.execute(_SELECT_DASHBOARD)
        (
            total,
            abertos,
            em_andamento,
            resolvidos,
            cancelados,
            baixa,
            media,
            alta,
            critica,
            tempo_medio,
        ) = cur.fetchone()

    return {
        "TOTAL": total,
        "POR_STATUS": {"A": abertos, "E": em_andamento, "R": resolvidos, "C": cancelados},
        "POR_PRIORIDADE": {"B": baixa, "M": media, "A": alta, "C": critica},
        "TEMPO_MEDIO_RESOLUCAO_HORAS": tempo_medio,
    }
