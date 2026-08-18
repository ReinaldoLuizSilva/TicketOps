from conftest import novo_email, apagar_cliente

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

def test_atualizar_cliente_nome(api, db, cliente):
    cliente = api.post("/clientes", json={"nome": "Cliente Teste", "email": novo_email()})
    assert cliente.status_code == 201, cliente.text
    novo_nome = "Cliente Atualizado"
    response = api.put(f"/clientes/{cliente.json()['ID']}", json={"nome": novo_nome})
    assert response.status_code == 204, response.text
    apagar_cliente(db, cliente.json()["ID"])

def test_atualizar_cliente_email(api, db, cliente):
    cliente = api.post("/clientes", json={"nome": "Cliente Teste", "email": novo_email()})
    assert cliente.status_code == 201, cliente.text
    email = novo_email()
    response = api.put(f"/clientes/{cliente.json()['ID']}", json={"email": email})
    assert response.status_code == 204, response.text
    apagar_cliente(db, cliente.json()["ID"])

def test_atualizar_cliente_completo(api, db, cliente):
    cliente = api.post("/clientes", json={"nome": "Cliente Teste", "email": novo_email()})
    assert cliente.status_code == 201, cliente.text
    novo_nome = "Cliente Atualizado"
    email = novo_email()
    response = api.put(f"/clientes/{cliente.json()['ID']}", json={"nome": novo_nome, "email": email})
    assert response.status_code == 204, response.text
    apagar_cliente(db, cliente.json()["ID"])

def test_atualizar_cliente_nada(api, db, cliente):
    cliente = api.post("/clientes", json={"nome": "Cliente Teste", "email": novo_email()})
    assert cliente.status_code == 201, cliente.text
    response = api.put(f"/clientes/{cliente.json()['ID']}", json={})
    assert response.status_code == 400, response.text
    apagar_cliente(db, cliente.json()["ID"])

def test_atualizar_cliente_inexistente(api):
    response = api.put("/clientes/999999", json={"nome": "Cliente Atualizado"})
    assert response.status_code == 404, response.text

def test_atualizar_cliente_email_duplicado(api, db, cliente):
    outro = api.post("/clientes", json={"nome": "Outro Cliente", "email": novo_email()})
    assert outro.status_code == 201, outro.text
    try:
        response = api.put(f"/clientes/{outro.json()['ID']}", json={"email": cliente["EMAIL"]})
        assert response.status_code == 409, response.text
        assert response.json() == {"detail": "Registro duplicado"}
    finally:
        apagar_cliente(db, outro.json()["ID"])

def test_atualizar_cliente_valida_updated_updatedby(api, db):
    email = novo_email()
    response = api.post("/clientes", json={"nome": "Cliente Teste", "email": email})
    assert response.status_code == 201, response.text
    dados = response.json()

    novo_nome = "Cliente Atualizado"
    response = api.put(f"/clientes/{dados['ID']}", json={"nome": novo_nome})
    assert response.status_code == 204, response.text

    with db.cursor() as cursor:
        cursor.execute("SELECT updated, updatedby FROM clientes WHERE id = :id", id=dados["ID"])
        row = cursor.fetchone()
        assert row is not None
        updated = row[0]
        assert updated is not None
        updatedby = row[1]
        assert updatedby is not None

    apagar_cliente(db, dados["ID"])

def test_atualizar_cliente_nome_nulo(api, db, cliente):
    cliente = api.post("/clientes", json={"nome": "Cliente Teste", "email": novo_email()})
    assert cliente.status_code == 201, cliente.text
    response = api.put(f"/clientes/{cliente.json()['ID']}", json={"nome": None})
    assert response.status_code == 500, response.text
    apagar_cliente(db, cliente.json()["ID"])

def test_excluir_cliente(api, db, cliente):
    response = api.post("/clientes", json={"nome": "Cliente Teste", "email": novo_email()})
    assert response.status_code == 201, response.text
    cliente = response.json()
    response = api.delete(f"/clientes/{cliente['ID']}")
    assert response.status_code == 204, response.text

    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM clientes WHERE id = :id", id=cliente["ID"])
        row = cursor.fetchone()
        assert row is None

def test_excluir_cliente_inexistente(api):
    response = api.delete("/clientes/999999")
    assert response.status_code == 404, response.text

def test_excluir_cliente_com_chamados(api, db, cliente):
    response = api.post(
        "/chamados",
        json={
            "cliente_id": cliente["ID"],
            "titulo": "Chamado Teste",
            "descricao": "Descrição do chamado teste",
            "prioridade": 'A',
        },
    )
    assert response.status_code == 201, response.text
    chamado = response.json()

    response = api.delete(f"/clientes/{cliente['ID']}")
    assert response.status_code == 409, response.text
    

def test_excluir_cliente_duas_vezes(api, cliente):
    response = api.post("/clientes", json={"nome": "Cliente Teste", "email": novo_email()})
    assert response.status_code == 201, response.text
    cliente = response.json()
    response = api.delete(f"/clientes/{cliente['ID']}")
    assert response.status_code == 204, response.text

    response = api.delete(f"/clientes/{cliente['ID']}")
    assert response.status_code == 404, response.text


