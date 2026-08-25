from contextlib import asynccontextmanager

import oracledb
from fastapi import Depends, FastAPI, Request

from app.db import close_pool, get_conn, init_pool
from app.errors import oracle_error_handler
from app.logging_config import configurar_logging, trace_atual
from app.routers import chamados, clientes
from app.schemas import HealthOut, ReadyOut

# Antes do FastAPI(...) de propósito: o uvicorn configura o logging no Config.load() e só
# então importa a aplicação, então o setup do projeto acontece por último e ganha — inclusive
# sobre as linhas de boot do servidor, que são as que aparecem quando o container não sobe.
configurar_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    try:
        yield
    finally:
        close_pool()


app = FastAPI(
    title="TicketOps",
    description="API de gestão de chamados — CI/CD, Terraform e arquitetura multi-cloud (GCP + OCI)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_exception_handler(oracledb.DatabaseError, oracle_error_handler)


@app.middleware("http")
async def contexto_trace(request: Request, call_next):
    """Leva o trace da requisição até o formatter. O Cloud Run manda o header no formato
    TRACE_ID/SPAN_ID;o=1. Tem que ser ContextVar: a aplicação é async, várias requisições
    coexistem na mesma thread, e uma global faria os logs de uma aparecerem sob o trace de outra."""
    cabecalho = request.headers.get("x-cloud-trace-context", "")
    token = trace_atual.set(cabecalho.split("/")[0] or None)
    try:
        return await call_next(request)
    finally:
        trace_atual.reset(token)

app.include_router(clientes.router, prefix="/clientes", tags=["clientes"])

app.include_router(chamados.router, prefix="/chamados", tags=["chamados"])


@app.get("/health", tags=["infra"], response_model=HealthOut)
def health():
    """Prova que a aplicação subiu. Não toca no banco, de propósito: o smoke test
    do CI usa esta rota, e acoplar o banco a ela faria uma indisponibilidade do
    Autonomous Database derrubar o deploy. Quem checa o banco é o /ready."""
    return {"status": "ok", "service": "ticketops", "version": app.version}


@app.get("/ready", tags=["infra"], response_model=ReadyOut)
def ready(conn=Depends(get_conn)):
    """Prova que a aplicação alcança o banco. Herda o 503 do get_conn: banco fora,
    esta rota responde 503 com o mesmo corpo que /chamados."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM dual")
        cur.fetchone()
    return {"status": "ready", "database": "ok"}
