from conftest import novo_email

def test_criar_cliente(api):
    response = api.post("/clientes", json={"nome": "Cliente Teste", "email": novo_email()})
    assert response.status_code == 201, response.text

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

def test_criar_cliente_campo_telefone(api):
    response = api.post("/clientes", json={"nome": "Cliente Teste", "email": novo_email(), "telefone": "123456789"})
    assert response.status_code == 201, response.text
    dados = response.json()
    assert dados