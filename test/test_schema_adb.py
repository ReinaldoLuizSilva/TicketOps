"""O M4 aceitou uma dívida conhecida: dois scripts de schema, um para o container do
CI e outro para o ADB, que podem divergir. A divergência apareceria do pior jeito
possível — teste verde e produção quebrada — porque o CI só executa o primeiro.

Este teste é o que transforma essa dívida em check vermelho. Ele não roda SQL:
compara o texto dos dois arquivos, a partir da primeira tabela. O que vem antes é
o que legitimamente difere — o ALTER SESSION no local, o CREATE USER no do ADB.
"""

from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
_LOCAL = _RAIZ / "database" / "01-schema.sql"
_ADB = _RAIZ / "database" / "adb" / "01-schema-adb.sql"

_PRIMEIRA_TABELA = "CREATE TABLE ticketops.clientes"


def _ddl_compartilhado(arquivo: Path) -> str:
    texto = arquivo.read_text(encoding="utf-8")
    inicio = texto.find(_PRIMEIRA_TABELA)
    assert inicio != -1, f"{arquivo.name} não tem '{_PRIMEIRA_TABELA}'"

    # Espaço no fim da linha não é divergência de schema: um editor que apara um
    # arquivo e não o outro não pode deixar o teste vermelho. Comentários também
    # não contam — cada script comenta o que faz sentido no ambiente dele.
    linhas = [
        linha.rstrip()
        for linha in texto[inicio:].strip().splitlines()
        if not linha.lstrip().startswith("--")
    ]
    return "\n".join(linhas)


def test_schema_adb_espelha_o_local():
    assert _ddl_compartilhado(_ADB) == _ddl_compartilhado(_LOCAL), (
        "o DDL do ADB divergiu do local. Toda mudança de schema é em dois lugares: "
        "database/01-schema.sql (que o CI executa num container descartável) e "
        "database/adb/01-schema-adb.sql (aplicado à mão no Autonomous Database)."
    )
