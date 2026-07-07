from pydantic import BaseModel

class ClienteCreate(BaseModel):
    nome: str
    email: str

class ClienteUpdate(BaseModel):
    nome: str | None = None
    email: str | None = None

class ChamadosCreate(BaseModel):
    cliente_id: int
    titulo: str
    descricao: str
    prioridade: str
    status: str
    data_resolvido: str | None = None

class ChamadoUpdate(BaseModel):
    cliente_id: int | None = None
    titulo: str | None = None
    descricao: str | None = None
    prioridade: str | None = None
    status: str | None = None
    data_resolvido: str | None = None