"""O dashboard agrega a tabela inteira, e o banco local carrega resíduo de outras rodadas.
Por isso os testes conferem o delta — o que mudou entre duas leituras — e nunca um número
absoluto, que quebraria de forma intermitente conforme o banco acumula dados."""


def _abrir_chamado(api, cliente, prioridade="A"):
    response = api.post(
        "/chamados",
        json={
            "cliente_id": cliente["ID"],
            "titulo": "Chamado Teste",
            "descricao": "Descrição do chamado teste",
            "prioridade": prioridade,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_dashboard(api):
    response = api.get("/dashboard")
    assert response.status_code == 200, response.text
    dados = response.json()
    assert dados["TOTAL"] >= 0
    assert set(dados["POR_STATUS"]) == {"A", "E", "R", "C"}
    assert set(dados["POR_PRIORIDADE"]) == {"B", "M", "A", "C"}


def test_dashboard_soma_dos_buckets_bate_com_o_total(api, chamado):
    dados = api.get("/dashboard").json()
    assert sum(dados["POR_STATUS"].values()) == dados["TOTAL"]
    assert sum(dados["POR_PRIORIDADE"].values()) == dados["TOTAL"]


def test_dashboard_conta_o_chamado_novo(api, cliente):
    antes = api.get("/dashboard").json()
    _abrir_chamado(api, cliente, prioridade="A")
    depois = api.get("/dashboard").json()

    assert depois["TOTAL"] == antes["TOTAL"] + 1
    assert depois["POR_STATUS"]["A"] == antes["POR_STATUS"]["A"] + 1
    assert depois["POR_PRIORIDADE"]["A"] == antes["POR_PRIORIDADE"]["A"] + 1


def test_dashboard_resolver_move_o_chamado_de_bucket(api, cliente):
    chamado = _abrir_chamado(api, cliente)
    antes = api.get("/dashboard").json()

    response = api.patch(f"/chamados/{chamado['ID']}", json={"status": "R"})
    assert response.status_code == 204, response.text

    depois = api.get("/dashboard").json()
    assert depois["TOTAL"] == antes["TOTAL"]
    assert depois["POR_STATUS"]["A"] == antes["POR_STATUS"]["A"] - 1
    assert depois["POR_STATUS"]["R"] == antes["POR_STATUS"]["R"] + 1


def test_dashboard_tempo_medio_com_chamado_resolvido(api, cliente):
    chamado = _abrir_chamado(api, cliente)
    response = api.patch(f"/chamados/{chamado['ID']}", json={"status": "R"})
    assert response.status_code == 204, response.text

    dados = api.get("/dashboard").json()
    # >= 0, e não > 0: o CAST para DATE trunca a fração de segundo, e um chamado aberto e
    # resolvido dentro do mesmo teste tem diferença zero
    assert dados["TEMPO_MEDIO_RESOLUCAO_HORAS"] is not None
    assert dados["TEMPO_MEDIO_RESOLUCAO_HORAS"] >= 0


def test_dashboard_nao_aceita_post(api):
    response = api.post("/dashboard", json={})
    assert response.status_code == 405, response.text
