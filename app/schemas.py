from typing import Literal

from pydantic import BaseModel, Field


class ClienteCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=1, max_length=120)


class ClienteUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=1, max_length=120)


class ChamadosCreate(BaseModel):
    cliente_id: int
    titulo: str = Field(min_length=1, max_length=200)
    descricao: str | None = None
    # B = Baixo, M = Media, A = Alta, C = Critica
    prioridade: Literal["B", "M", "A", "C"] = "M"


class ChamadoUpdate(BaseModel):
    cliente_id: int | None = None
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    descricao: str | None = None
    # B = Baixo, M = Media, A = Alta, C = Critica
    prioridade: Literal["B", "M", "A", "C"] | None = None
    # A = Aberto, E = Em andamento, R = Resolvido, C = Cancelado
    # data_resolvido é derivado do status pelo router, não é informado pelo cliente
    status: Literal["A", "E", "R", "C"] | None = None

class ComentarioCreate(BaseModel):
    autor: str = Field(min_length=1, max_length=120)
    texto: str = Field(min_length=1)
