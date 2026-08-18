def _criar(api, chamado_id, autor="Autor Teste", texto="Comentário de teste"):
    return api.post(f"/chamados/{chamado_id}/comentarios", json={"autor": autor, "texto": texto})


def _comentarios_do_chamado(api, chamado_id):
    response = api.get(f"/chamados/{chamado_id}")
    assert response.status_code == 200, response.text
    return response.json()["COMENTARIOS"]


def test_criar_comentario(api, chamado):
    response = _criar(api, chamado["ID"])
    assert response.status_code == 201, response.text

    dados = response.json()
    assert dados["CHAMADO_ID"] == chamado["ID"]
    assert dados["AUTOR"] == "Autor Teste"
    assert dados["TEXTO"] == "Comentário de teste"
    assert dados["ID"] is not None
    assert dados["CRIADO_EM"] is not None


def test_criar_comentario_persiste_no_banco(api, db, chamado):
    dados = _criar(api, chamado["ID"]).json()

    with db.cursor() as cursor:
        cursor.execute(
            "SELECT chamado_id, autor, texto, created, createdby FROM comentarios WHERE id = :id",
            id=dados["ID"],
        )
        chamado_id, autor, texto, created, createdby = cursor.fetchone()

    assert chamado_id == chamado["ID"]
    assert autor == "Autor Teste"
    assert texto.read() == "Comentário de teste"
    assert created is not None
    assert createdby is not None


def test_comentario_aparece_no_detalhe_do_chamado(api, chamado, comentario):
    comentarios = _comentarios_do_chamado(api, chamado["ID"])
    assert comentarios == [
        {
            "ID": comentario["ID"],
            "AUTOR": comentario["AUTOR"],
            "TEXTO": comentario["TEXTO"],
            "CRIADO_EM": comentario["CRIADO_EM"],
        }
    ]


def test_comentarios_vem_ordenados_por_id(api, chamado):
    ids = [_criar(api, chamado["ID"], texto=f"Comentário {i}").json()["ID"] for i in range(3)]

    comentarios = _comentarios_do_chamado(api, chamado["ID"])
    assert [c["ID"] for c in comentarios] == sorted(ids)
    assert [c["TEXTO"] for c in comentarios] == ["Comentário 0", "Comentário 1", "Comentário 2"]


def test_comentario_nao_vaza_para_outro_chamado(api, cliente, chamado, comentario):
    outro = api.post(
        "/chamados",
        json={
            "cliente_id": cliente["ID"],
            "titulo": "Outro Chamado",
            "descricao": "Descrição do outro chamado",
            "prioridade": "M",
        },
    )
    assert outro.status_code == 201, outro.text

    assert _comentarios_do_chamado(api, outro.json()["ID"]) == []
    assert [c["ID"] for c in _comentarios_do_chamado(api, chamado["ID"])] == [comentario["ID"]]


def test_criar_comentario_texto_longo_sobrevive_ao_clob(api, chamado):
    texto = "áéíóú " * 5000
    dados = _criar(api, chamado["ID"], texto=texto).json()
    assert dados["TEXTO"] == texto

    comentarios = _comentarios_do_chamado(api, chamado["ID"])
    assert comentarios[0]["TEXTO"] == texto


def test_criar_comentario_autor_no_limite(api, chamado):
    autor = "A" * 120
    response = _criar(api, chamado["ID"], autor=autor)
    assert response.status_code == 201, response.text
    assert response.json()["AUTOR"] == autor


def test_criar_comentario_chamado_inexistente(api):
    response = _criar(api, 999999)
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Chamado não encontrado"}


def test_criar_comentario_chamado_id_nao_numerico(api):
    response = _criar(api, "abc")
    assert response.status_code == 422, response.text


def test_criar_comentario_autor_vazio(api, chamado):
    response = _criar(api, chamado["ID"], autor="")
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "string_too_short",
                "loc": ["body", "autor"],
                "msg": "String should have at least 1 character",
                "input": "",
                "ctx": {"min_length": 1},
            }
        ]
    }


def test_criar_comentario_autor_max_length(api, chamado):
    autor = "A" * 121
    response = _criar(api, chamado["ID"], autor=autor)
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "string_too_long",
                "loc": ["body", "autor"],
                "msg": "String should have at most 120 characters",
                "input": autor,
                "ctx": {"max_length": 120},
            }
        ]
    }


def test_criar_comentario_texto_vazio(api, chamado):
    response = _criar(api, chamado["ID"], texto="")
    assert response.status_code == 422, response.text

    erro = response.json()["detail"][0]
    assert erro["type"] == "string_too_short"
    assert erro["loc"] == ["body", "texto"]


def test_criar_comentario_autor_nulo(api, chamado):
    response = _criar(api, chamado["ID"], autor=None)
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["body", "autor"]


def test_criar_comentario_texto_nulo(api, chamado):
    response = _criar(api, chamado["ID"], texto=None)
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["body", "texto"]


def test_criar_comentario_sem_campos(api, chamado):
    response = api.post(f"/chamados/{chamado['ID']}/comentarios", json={})
    assert response.status_code == 422, response.text

    faltando = {tuple(erro["loc"]) for erro in response.json()["detail"]}
    assert faltando == {("body", "autor"), ("body", "texto")}


def test_criar_comentario_ignora_campo_extra(api, chamado):
    response = api.post(
        f"/chamados/{chamado['ID']}/comentarios",
        json={"autor": "Autor Teste", "texto": "Comentário de teste", "chamado_id": 999999},
    )
    assert response.status_code == 201, response.text
    assert response.json()["CHAMADO_ID"] == chamado["ID"]


def test_excluir_chamado_com_comentario_devolve_409(api, db, chamado, comentario):
    response = api.delete(f"/chamados/{chamado['ID']}")
    assert response.status_code == 409, response.text
    assert response.json() == {"detail": "Registro possui dependentes e não pode ser excluído"}

    with db.cursor() as cursor:
        cursor.execute("SELECT 1 FROM chamados WHERE id = :id", id=chamado["ID"])
        assert cursor.fetchone() is not None
