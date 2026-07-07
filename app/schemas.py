from pydantic import BaseModel

class ClienteCreate(BaseModel):
    nome: str
    email: str

class ClienteUpdate(BaseModel):
    nome: str | None = None
    email: str | None = None