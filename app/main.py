from fastapi import FastAPI
from app.routers import clientes, chamados

app = FastAPI(
    title="TicketOps",
    description="API de gestão de chamados — CI/CD, Terraform e arquitetura multi-cloud (GCP + OCI)",
    version="0.1.0",
)

app.include_router(
    clientes.router, 
    prefix="/clientes",
    tags=["clientes"]
)

app.include_router(
    chamados.router,
    prefix="/chamados",
    tags=["chamados"]
)

@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok", "service": "ticketops", "version": app.version}