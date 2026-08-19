from conftest import apagar_cliente, novo_email


def test_criar_cliente(api, db):
    response = api.post("/clientes", json={"nome": "Cliente Teste", "email": novo_email()})
    assert response.status_code == 201, response.text
    apagar_cliente(db, response.json()["ID"])

def test_listar_clientes(api, cliente):
    response = api.get("/clientes")
    assert response.status_code == 200, response.text

    lista = response.json()
    encontrado = next((c for c in lista if c["ID"] == cliente["ID"]), None)
    assert encontrado == {
        "ID": cliente["ID"],
        "NOME": cliente["NOME"],
        "EMAIL": cliente["EMAIL"],
    }

def test_criar_cliente_email_duplicado(api, cliente):
    response = api.post("/clientes", json={"nome": "Cliente Teste", "email": cliente["EMAIL"]})
    assert response.status_code == 409, response.text
    assert response.json() == {"detail": "Registro duplicado"}

def test_criar_cliente_sem_email(api):
    response = api.post("/clientes", json={"nome": "Cliente Teste"})
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "missing",
                "loc": ["body", "email"],
                "msg": "Field required",
                "input": {"nome": "Cliente Teste"},
            }
        ]
    }

def test_criar_cliente_nome_vazio(api):
    response = api.post("/clientes", json={"nome": "", "email": novo_email()})
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "string_too_short",
                "loc": ["body", "nome"],
                "msg": "String should have at least 1 character",
                "input": '',
                "ctx": {"min_length": 1},
            }
        ]
    }

def test_criar_cliente_nome_max_length(api):
    nome = "A" * 121
    response = api.post("/clientes", json={"nome": nome, "email": novo_email()})
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "string_too_long",
                "loc": ["body", "nome"],
                "msg": "String should have at most 120 characters",
                "input": nome,
                "ctx": {"max_length": 120},
            }
        ]
    }

def test_criar_cliente_valida_created_createdby(api, db):
    email = novo_email()
    response = api.post("/clientes", json={"nome": "Cliente Teste", "email": email})
    assert response.status_code == 201, response.text
    dados = response.json()

    with db.cursor() as cursor:
        cursor.execute("SELECT created, createdby FROM clientes WHERE id = :id", id=dados["ID"])
        row = cursor.fetchone()
        assert row is not None
        created = row[0]
        assert created is not None
        createdby = row[1]
        assert createdby is not None

    apagar_cliente(db, dados["ID"])

def test_criar_cliente_campo_telefone(api, db):
    response = api.post("/clientes", json={"nome": "Cliente Teste", "email": novo_email(), "telefone": "123456789"})
    assert response.status_code == 201, response.text
    dados = response.json()
    assert set(dados.keys()) == {"ID", "NOME", "EMAIL"}
    apagar_cliente(db, dados["ID"])

def test_listar_clientes_por_id(api, db, cliente):
    outro = api.post("/clientes", json={"nome": "Outro Cliente", "email": novo_email()})
    assert outro.status_code == 201, outro.text
    try:
        ids = [c["ID"] for c in api.get("/clientes").json()]

        assert len(ids) >= 2
        assert ids == sorted(ids)
    finally:
        apagar_cliente(db, outro.json()["ID"])

def test_atualizar_cliente_nome(api, cliente):
    novo_nome = "Cliente Atualizado"
    response = api.patch(f"/clientes/{cliente['ID']}", json={"nome": novo_nome})
    assert response.status_code == 204, response.text

    atualizado = next(c for c in api.get("/clientes").json() if c["ID"] == cliente["ID"])
    assert atualizado["NOME"] == novo_nome
    assert atualizado["EMAIL"] == cliente["EMAIL"]

def test_atualizar_cliente_email(api, cliente):
    email = novo_email()
    response = api.patch(f"/clientes/{cliente['ID']}", json={"email": email})
    assert response.status_code == 204, response.text

    atualizado = next(c for c in api.get("/clientes").json() if c["ID"] == cliente["ID"])
    assert atualizado["NOME"] == cliente["NOME"]
    assert atualizado["EMAIL"] == email

def test_atualizar_cliente(api, cliente):
    novo_nome = "Cliente Atualizado"
    email = novo_email()
    response = api.patch(f"/clientes/{cliente['ID']}", json={"nome": novo_nome, "email": email})
    assert response.status_code == 204, response.text

    atualizado = next(c for c in api.get("/clientes").json() if c["ID"] == cliente["ID"])
    assert atualizado == {"ID": cliente["ID"], "NOME": novo_nome, "EMAIL": email}

def test_atualizar_cliente_nada(api, cliente):
    response = api.patch(f"/clientes/{cliente['ID']}", json={})
    assert response.status_code == 400, response.text
    assert response.json() == {"detail": "Nada para atualizar"}

def test_atualizar_cliente_inexistente(api):
    response = api.patch("/clientes/999999", json={"nome": "Cliente Atualizado"})
    assert response.status_code == 404, response.text

def test_atualizar_cliente_email_duplicado(api, db, cliente):
    outro = api.post("/clientes", json={"nome": "Outro Cliente", "email": novo_email()})
    assert outro.status_code == 201, outro.text
    try:
        response = api.patch(f"/clientes/{outro.json()['ID']}", json={"email": cliente["EMAIL"]})
        assert response.status_code == 409, response.text
        assert response.json() == {"detail": "Registro duplicado"}
    finally:
        apagar_cliente(db, outro.json()["ID"])

def test_atualizar_cliente_valida_updated_updatedby(api, db):
    response = api.post("/clientes", json={"nome": "Cliente Teste", "email": novo_email()})
    assert response.status_code == 201, response.text
    dados = response.json()

    with db.cursor() as cursor:
        cursor.execute("SELECT updated, updatedby FROM clientes WHERE id = :id", id=dados["ID"])
        assert cursor.fetchone() == (None, None)

    response = api.patch(f"/clientes/{dados['ID']}", json={"nome": "Cliente Atualizado"})
    assert response.status_code == 204, response.text

    with db.cursor() as cursor:
        cursor.execute("SELECT updated, updatedby FROM clientes WHERE id = :id", id=dados["ID"])
        updated, updatedby = cursor.fetchone()
        assert updated is not None
        assert updatedby is not None

    apagar_cliente(db, dados["ID"])

def test_atualizar_cliente_nome_nulo(api, cliente):
    response = api.patch(f"/clientes/{cliente['ID']}", json={"nome": None})
    assert response.status_code == 400, response.text
    assert response.json() == {"detail": "Campo obrigatório não informado"}

def test_atualizar_cliente_nome_vazio(api, cliente):
    response = api.patch(f"/clientes/{cliente['ID']}", json={"nome": ""})
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "string_too_short",
                "loc": ["body", "nome"],
                "msg": "String should have at least 1 character",
                "input": '',
                "ctx": {"min_length": 1},
            }
        ]
    }

def test_excluir_cliente(api, db, cliente):
    response = api.delete(f"/clientes/{cliente['ID']}")
    assert response.status_code == 204, response.text

    with db.cursor() as cursor:
        cursor.execute("SELECT 1 FROM clientes WHERE id = :id", id=cliente["ID"])
        assert cursor.fetchone() is None

def test_excluir_cliente_inexistente(api):
    response = api.delete("/clientes/999999")
    assert response.status_code == 404, response.text

def test_excluir_cliente_com_chamados(api, cliente, chamado):
    response = api.delete(f"/clientes/{cliente['ID']}")
    assert response.status_code == 409, response.text
    assert response.json() == {"detail": "Registro possui dependentes e não pode ser excluído"}


def test_excluir_cliente_duas_vezes(api, cliente):
    response = api.delete(f"/clientes/{cliente['ID']}")
    assert response.status_code == 204, response.text

    response = api.delete(f"/clientes/{cliente['ID']}")
    assert response.status_code == 404, response.text


