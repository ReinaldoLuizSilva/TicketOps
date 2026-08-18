

def test_criar_chamado(api, db, cliente):
    response = api.post("/chamados", json={
        "cliente_id": cliente["ID"],
        "titulo": "Chamado Teste",
        "descricao": "Descrição do chamado teste",
        "prioridade": "A",
    })
    assert response.status_code == 201, response.text
    assert response.json() == {
        "ID": response.json()["ID"],
        "CLIENTE": cliente["ID"],
        "TITULO": "Chamado Teste",
        "DESCRICAO": "Descrição do chamado teste",
        "PRIORIDADE": "A",
    }

    with db.cursor() as cursor:
        cursor.execute("SELECT status, data_resolvido FROM chamados WHERE id = :id",
                       id=response.json()["ID"])
        assert cursor.fetchone() == ("A", None)

def test_listar_chamados(api, cliente):
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
    dados = response.json()
    response = api.get("/chamados")
    assert response.status_code == 200, response.text
    chamados = response.json()
    assert any(chamado["ID"] == dados["ID"] for chamado in chamados)

def test_criar_chamado_cliente_inexistente(api):
    response = api.post(
        "/chamados",
        json={
            "cliente_id": 999999,
            "titulo": "Chamado Teste",
            "descricao": "Descrição do chamado teste",
            "prioridade": 'A',
        },
    )
    assert response.status_code == 400, response.text
    assert response.json() == {"detail": "Referência informada não existe"}

def test_criar_chamado_cliente_nulo(api):
    response = api.post(
        "/chamados",
        json={
            "cliente_id": None,
            "titulo": "Chamado Teste",
            "descricao": "Descrição do chamado teste",
            "prioridade": 'A',
        },
    )
    assert response.status_code == 422, response.text

def test_criar_chamado_titulo_nulo(api, cliente):
    response = api.post(
        "/chamados",
        json={
            "cliente_id": cliente["ID"],
            "titulo": None,
            "descricao": "Descrição do chamado teste",
            "prioridade": 'A',
        },
    )
    assert response.status_code == 422, response.text

def test_criar_chamado_titulo_vazio(api, cliente):
    response = api.post(
        "/chamados",
        json={
            "cliente_id": cliente["ID"],
            "titulo": "",
            "descricao": "Descrição do chamado teste",
            "prioridade": 'A',
        },
    )
    assert response.status_code == 422, response.text

def test_criar_chamado_titulo_max_length(api, cliente):
    titulo = "A" * 201
    response = api.post(
        "/chamados",
        json={
            "cliente_id": cliente["ID"],
            "titulo": titulo,
            "descricao": "Descrição do chamado teste",
            "prioridade": 'A',
        },
    )
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "string_too_long",
                "loc": ["body", "titulo"],
                "msg": "String should have at most 200 characters",
                "input": titulo,
                "ctx": {"max_length": 200},
            }
        ]
    }

def test_criar_chamado_prioridade_invalida(api, cliente):
    response = api.post(
        "/chamados",
        json={
            "cliente_id": cliente["ID"],
            "titulo": "Chamado Teste",
            "descricao": "Descrição do chamado teste",
            "prioridade": "Z",
        },
    )
    assert response.status_code == 422, response.text

    erro = response.json()["detail"][0]
    assert erro["type"] == "literal_error"
    assert erro["loc"] == ["body", "prioridade"]
    assert erro["input"] == "Z"

def test_criar_chamado_prioridade_nula(api, cliente):
    response = api.post(
        "/chamados",
        json={
            "cliente_id": cliente["ID"],
            "titulo": "Chamado Teste",
            "descricao": "Descrição do chamado teste",
            "prioridade": None,
        },
    )
    assert response.status_code == 422, response.text

    erro = response.json()["detail"][0]
    assert erro["type"] == "literal_error"
    assert erro["loc"] == ["body", "prioridade"]

def test_listar_chamados_por_id(api, chamado):
    response = api.get(f"/chamados/{chamado['ID']}")
    assert response.status_code == 200, response.text
    dados = response.json()
    assert dados["ID"] == chamado["ID"]

def test_obter_chamado_traz_cliente_descricao_e_comentarios(api, cliente, chamado):
    dados = api.get(f"/chamados/{chamado['ID']}").json()
    assert dados["CLIENTE_ID"] == cliente["ID"]
    assert dados["CLIENTE_NOME"] == cliente["NOME"]
    assert dados["DESCRICAO"] == "Descrição do chamado teste"
    assert dados["COMENTARIOS"] == []

def test_atualizar_chamado(api, chamado):
    response = api.patch(
        f"/chamados/{chamado['ID']}",
        json={
            "titulo": "Chamado Atualizado",
            "descricao": "Descrição atualizada",
            "prioridade": 'B',
        },
    )
    assert response.status_code == 204, response.text

def test_atualizar_chamado_inexistente(api):
    response = api.patch(
        "/chamados/999999",
        json={
            "titulo": "Chamado Atualizado",
            "descricao": "Descrição atualizada",
            "prioridade": 'B',
        },
    )
    assert response.status_code == 404, response.text

def test_atualizar_chamado_nada(api, chamado):
    response = api.patch(f"/chamados/{chamado['ID']}", json={})
    assert response.status_code == 400, response.text
    assert response.json() == {"detail": "Nada para atualizar"}

def test_atualizar_chamado_updated_updatedby(api, chamado, db):
    response = api.patch(
        f"/chamados/{chamado['ID']}",
        json={
            "titulo": "Chamado Atualizado",
            "descricao": "Descrição atualizada",
            "prioridade": 'B',
        },
    )
    assert response.status_code == 204, response.text

    with db.cursor() as cursor:
        cursor.execute("SELECT updated, updatedby FROM chamados WHERE id = :id", id=chamado["ID"])
        updated, updatedby = cursor.fetchone()
        assert updated is not None
        assert updatedby is not None


def test_atualizar_chamado_nulo(api, chamado):
    response = api.patch(
        f"/chamados/{chamado['ID']}",
        json={
            "titulo": None,
            "descricao": "Descrição atualizada",
            "prioridade": 'B',
        },
    )
    assert response.status_code == 400, response.text
    assert response.json() == {"detail": "Campo obrigatório não informado"}

def test_atualizar_chamado_titulo_vazio(api, chamado):
    response = api.patch(
        f"/chamados/{chamado['ID']}",
        json={
            "titulo": "",
            "descricao": "Descrição atualizada",
            "prioridade": 'B',
        },
    )
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "string_too_short",
                "loc": ["body", "titulo"],
                "msg": "String should have at least 1 character",
                "input": '',
                "ctx": {"min_length": 1},
            }
        ]
    }

def test_atualizar_chamado_para_resolvido_preenche_data(api, db, chamado):
    response = api.patch(f"/chamados/{chamado['ID']}", json={"status": "R"})
    assert response.status_code == 204, response.text
    assert api.get(f"/chamados/{chamado['ID']}").json()["DATA_RESOLVIDO"] is not None

def test_atualizar_chamado_saindo_de_resolvido_limpa_data(api, chamado):
    response = api.patch(f"/chamados/{chamado['ID']}", json={"status": "R"})
    assert response.status_code == 204, response.text

    response = api.patch(f"/chamados/{chamado['ID']}", json={"status": "E"})
    assert response.status_code == 204, response.text
    assert api.get(f"/chamados/{chamado['ID']}").json()["DATA_RESOLVIDO"] is None

def test_resolver_duas_vezes_mantem_a_data_original(api, chamado):
    response = api.patch(f"/chamados/{chamado['ID']}", json={"status": "R"})
    assert response.status_code == 204, response.text
    primeira = api.get(f"/chamados/{chamado['ID']}").json()["DATA_RESOLVIDO"]
    response = api.patch(f"/chamados/{chamado['ID']}", json={"status": "R"})
    assert response.status_code == 204, response.text
    assert api.get(f"/chamados/{chamado['ID']}").json()["DATA_RESOLVIDO"] == primeira

def test_listar_chamados_filtra_por_status(api, chamado):
    abertos = api.get("/chamados?status=A").json()
    assert any(c["ID"] == chamado["ID"] for c in abertos)
    assert all(c["STATUS"] == "A" for c in abertos)

    resolvidos = api.get("/chamados?status=R").json()
    assert all(c["ID"] != chamado["ID"] for c in resolvidos)

def test_excluir_chamado(api, db, chamado):
    response = api.delete(f"/chamados/{chamado['ID']}")
    assert response.status_code == 204, response.text

    with db.cursor() as cursor:
        cursor.execute("SELECT 1 FROM chamados WHERE id = :id", id=chamado["ID"])
        assert cursor.fetchone() is None

def test_excluir_chamado_inexistente(api):
    response = api.delete("/chamados/999999")
    assert response.status_code == 404, response.text

def test_excluir_chamado_duas_vezes(api, chamado):
    response = api.delete(f"/chamados/{chamado['ID']}")
    assert response.status_code == 204, response.text

    response = api.delete(f"/chamados/{chamado['ID']}")
    assert response.status_code == 404, response.text

