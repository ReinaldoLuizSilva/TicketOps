from fastapi import FastAPI

app = FastAPI(
    title="TicketOps",
    description="API de gestão de chamados — CI/CD, Terraform e arquitetura multi-cloud (GCP + OCI)",
    version="0.1.0",
)

@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok", "service": "ticketops", "version": app.version}