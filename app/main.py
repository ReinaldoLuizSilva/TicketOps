from contextlib import asynccontextmanager

import oracledb
from fastapi import FastAPI

from app.db import close_pool, init_pool
from app.errors import oracle_error_handler
from app.routers import chamados, clientes
from app.schemas import HealthOut


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

app.include_router(clientes.router, prefix="/clientes", tags=["clientes"])

app.include_router(chamados.router, prefix="/chamados", tags=["chamados"])


@app.get("/health", tags=["infra"], response_model=HealthOut)
def health():
    return {"status": "ok", "service": "ticketops", "version": app.version}
