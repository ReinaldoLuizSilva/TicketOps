# Oracle Autonomous Database — a ponte multi-cloud por mTLS

O Cloud Run roda no GCP e o banco roda na OCI. As duas nuvens se falam por mTLS, com a wallet
vivendo no Secret Manager e montada no container como arquivo, em runtime. É o **M4**, e é o
milestone em que `GET /chamados` deixou de devolver 503.

> Complemento de [Infraestrutura — Terraform no GCP](../infra/README.md), que descreve o lado
> GCP da ponte, e de [Pipeline CI/CD](../cicd/README.md), que descreve o smoke test.
>
> O que está aqui é **console e CLI, aplicado à mão**. Nada nesta página é executado por
> pipeline, e é de propósito: o ADB é criado uma vez, e o `terraform apply` está fora do CI
> desde o M3.

## A decisão que define o milestone: mTLS ou TLS

O Autonomous Database serverless aceita dois modos de conexão, e a escolha muda quase tudo.

| | mTLS (com wallet) | TLS one-way (sem wallet) |
| --- | --- | --- |
| Arquivos no container | `ewallet.pem` | nenhum |
| Secrets a mais | 2 (wallet e senha dela) | 0 |
| O que autentica o cliente | certificado da wallet + usuário/senha | usuário/senha, e a **ACL de rede** |
| Exige na OCI | nada além do default | ACL com IPs ou VCNs autorizados |

TLS parece mais simples, e seria — se o cliente tivesse IP fixo. Para desligar o mTLS a OCI
exige uma lista de controle de acesso, e ela é **por endereço**. O Cloud Run com
`min_instance_count = 0` não tem IP de saída estável: para ter, seria preciso Serverless VPC
Access mais um Cloud NAT com IP reservado, e **Cloud NAT é cobrado por hora e não está no Always
Free**.

Então a conclusão não é estética, é de conta: a wallet é o caminho **mais barato**. Que também é
o mais defensável — "ponte multi-cloud por mTLS" se sustenta numa entrevista, "deixei o banco
aberto para a internet com senha" não.

O TLS fica registrado como a saída de emergência caso a wallet vire um poço de tempo. Não foi
preciso.

## O que foi escolhido na criação, e o que não dá para desfazer

**A home region é definida na criação da tenancy e não muda.** Os recursos Always Free existem
**somente** nela. Escolher errado significa recriar a conta — não há migração.

A home region desta tenancy é **`sa-vinhedo-1`** (Brazil Southeast, São Paulo). O Cloud Run está
em `us-central1` (Iowa), e essas duas escolhas não se conversam: são cerca de **9.000 km em linha
reta** e mais que isso de fibra, porque a rota sai pelos cabos do Atlântico.

Vale escrito por que isso é o que é. Se o critério fosse só a latência da API, a home region a
escolher seria a mais próxima do Cloud Run — `us-chicago-1` ou `us-ashburn-1`. O critério aqui
acabou sendo outro: proximidade de quem opera e demonstra o banco, o que também tem valor real
(console e APEX respondendo rápido). O que não dá é para ter os dois, e a escolha da OCI é a que
**não** pode ser desfeita.

A consequência está medida na seção de [latência](#latência-agora-é-uma-característica-da-arquitetura).
Se um dia ela incomodar, quem se move é o lado do GCP, não o da OCI: `southamerica-east1` (São
Paulo) colocaria o Cloud Run ao lado do banco. Isso é mudança de outro milestone — troca a URL
pública do serviço, quer o Artifact Registry na mesma região e sai da faixa de preço Tier 1 —, mas
é a única direção possível.

Outras escolhas da tela de criação:

| Item | Valor | Por quê |
| --- | --- | --- |
| Workload type | Transaction Processing | É uma API OLTP. Data Warehouse muda os serviços disponíveis |
| Sempre grátis | sim | 1 OCPU, 20 GB. O Always Free dá **duas** instâncias; uma basta |
| Acesso de rede | mTLS obrigatório (default) | Ver a seção acima |
| Serviço de conexão | **`devapex_tp`** | `_high` e `_medium` reservam paralelismo e limitam sessões concorrentes com força: em 1 OCPU, `_medium` pode aceitar uma única sessão por vez. `_tpurgent` é para carga prioritária |

A senha do ADMIN tem regras próprias — na data em que isto foi escrito, 12 a 30 caracteres, com
maiúscula, minúscula e número, sem aspas duplas, e sem conter o nome do usuário. Confirme na
própria tela, porque a validação só acontece **depois** do provisionamento começar.

## A wallet: no modo thin, um arquivo só

O zip que a OCI entrega tem nove arquivos. O `python-oracledb` em modo **thin** — que é o que
este projeto usa, e é o que dispensa o Instant Client — ignora quase todos:

| Arquivo | Serve para |
| --- | --- |
| `ewallet.pem` | **o que importa**: chave e certificado do cliente, cifrados pela senha da wallet |
| `tnsnames.ora` | os aliases (`..._tp`, `..._low`); dispensável se o `DB_DSN` for o descritor completo |
| `cwallet.sso`, `ewallet.p12` | modo thick / Instant Client |
| `keystore.jks`, `truststore.jks`, `ojdbc.properties` | JDBC |
| `sqlnet.ora` | ignorado pelo modo thin |
| `README` | — |

Confirme o conteúdo antes de assumir:

```bash
unzip -l Wallet_ticketops.zip
```

**Se `ewallet.pem` não estiver na lista, a wallet foi gerada sem senha** — gere de novo
informando uma. O modo thin exige o PEM e a senha dele; metade dos tutoriais de ADB manda
apontar a aplicação para o diretório da wallet e pronto, porque metade dos tutoriais é sobre o
modo thick, que lê o `cwallet.sso`. Montar a wallet inteira sem passar a senha rende um erro de
handshake TLS que não menciona senha nenhuma.

### Por que sobra um arquivo só

Se o `DB_DSN` guardar o **descritor de conexão completo** em vez de um alias, o `tnsnames.ora`
também deixa de ser necessário. O descritor sai da página de conexão do ADB (ou do próprio
`tnsnames.ora` dentro do zip) e tem esta cara:

```
(description=(retry_count=20)(retry_delay=3)
 (address=(protocol=tcps)(port=1522)(host=adb.sa-vinhedo-1.oraclecloud.com))
 (connect_data=(service_name=<dbid>_devapex_tp.adb.oraclecloud.com))
 (security=(ssl_server_dn_match=yes)))
```

O `retry_count=20` e o `retry_delay=3` vêm de fábrica no descritor e ganham importância nesta
topologia: são eles que absorvem uma queda momentânea da rota entre as duas nuvens em vez de
transformá-la em 503.

É por isso que `DB_CONFIG_DIR` continua **vazia**, e por isso o `app/db.py` não precisou mudar
nessa parte: os três parâmetros de wallet entram por `os.environ.get`, que devolve `None` quando
a variável não existe, e `config_dir=None` é exatamente o que o driver espera quando não há
`tnsnames.ora` para ler.

## O schema no ADB

O `database/01-schema.sql` **não roda no ADB**, e o motivo está na primeira linha:

```sql
ALTER SESSION SET CONTAINER = FREEPDB1;
```

No ADB você conecta direto no PDB e não tem privilégio de trocar de container. A linha é correta
no container local — o entrypoint do `gvenzl/oracle-free` executa os scripts a partir do
`CDB$ROOT` — e inválida aqui.

Há uma segunda diferença, mais silenciosa: o script cria tudo qualificado por `ticketops.` mas
**não cria o usuário `ticketops`**. Localmente ele nasce da variável `APP_USER` do container.

Daí o segundo script, [`database/adb/01-schema-adb.sql`](../../database/adb/01-schema-adb.sql),
aplicado **uma vez à mão**, conectado como ADMIN:

```sql
CREATE USER ticketops IDENTIFIED BY "<senha>";
GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE, CREATE TRIGGER TO ticketops;
ALTER USER ticketops QUOTA UNLIMITED ON DATA;
```

Três detalhes que custam tempo se passarem batido:

- **`DATA` é o nome da tablespace no ADB** — não é `USERS`, nem o nome do banco. Sem a quota, as
  tabelas são criadas normalmente e o **primeiro `INSERT`** falha com `ORA-01950`, que não
  menciona quota nenhuma.
- **Resista ao `GRANT DWROLE`.** É o atalho idiomático do ADB e concede muito mais do que três
  tabelas precisam.
- A senha do `ticketops` é a que vai para o secret `ticketops-db-password`. O script tem um
  placeholder `<SENHA_DO_APP>` de propósito: rodá-lo sem trocar falha com erro de sintaxe, alto e
  na hora, em vez de criar um usuário com senha literal.

### O preço dessa decisão, escrito

**São dois scripts que podem divergir.** Toda mudança de schema é em dois lugares, e a
divergência apareceria do pior jeito possível: teste verde e produção quebrada, porque o CI só
executa o script do container.

Tornar o `01-schema.sql` portátil entre os dois seria trocar o teste real pela elegância — ele é
o script que o CI executa a cada run, num volume novo, para os 68 testes.

O que fecha o buraco é o `test/test_schema_adb.py`: ele não roda SQL, compara o texto dos dois
arquivos. O DDL do script do ADB vive entre marcadores e tem de ser idêntico, linha a linha, ao
do script local. Mudou um e não o outro, o CI fica vermelho antes do merge.

## Subir os cinco valores

A fronteira do M2 continua valendo: **o Terraform declara que o segredo existe e quem pode ler;
o valor entra por `gcloud`.**

| Secret | Conteúdo |
| --- | --- |
| `ticketops-db-user` | `ticketops` |
| `ticketops-db-password` | a senha do usuário da aplicação |
| `ticketops-db-dsn` | o descritor de conexão completo |
| `ticketops-db-wallet` | o `ewallet.pem`, binário, como está |
| `ticketops-db-wallet-password` | a senha escolhida ao baixar a wallet |

Existe um atalho tentador que **viola a decisão do M2**: o provider da OCI tem o data source
`oci_database_autonomous_database_wallet`, que devolve a wallet em base64. Usá-lo gravaria a
wallet **no state do Terraform**, que mora num bucket — exatamente o motivo pelo qual as
credenciais do banco não passam pelo Terraform desde o M2. A wallet desce pela console ou pela
CLI da OCI e sobe pelo `gcloud`.

A wallet é binária e vai por arquivo, sem passar por pipe:

```bash
gcloud secrets versions add ticketops-db-wallet --data-file=ewallet.pem
```

O `--data-file` lê bytes e não mexe em nada. **Não** passe o arquivo por pipe do PowerShell: o
pipe reencoda, acrescenta BOM na frente e CRLF no fim, e isso destrói um PEM tão bem quanto
destrói uma senha (a armadilha está detalhada em [Infraestrutura](../infra/README.md#armadilhas)).

Os quatro valores de texto vão pelo mesmo caminho seguro — arquivo temporário sem BOM e sem
newline final:

```powershell
function Set-Segredo($nome) {
  $sec   = Read-Host "valor de $nome" -AsSecureString
  $valor = [System.Net.NetworkCredential]::new("", $sec).Password
  $f = [System.IO.Path]::GetTempFileName()
  [System.IO.File]::WriteAllText($f, $valor, (New-Object System.Text.UTF8Encoding($false)))
  gcloud secrets versions add $nome --data-file=$f
  Remove-Item $f -Force
}

Set-Segredo ticketops-db-user
Set-Segredo ticketops-db-password
Set-Segredo ticketops-db-dsn
Set-Segredo ticketops-db-wallet-password
```

Confira contando bytes — para valor em ASCII, o número tem de bater com o de caracteres:

```powershell
gcloud secrets versions access latest --secret=ticketops-db-user --out-file=- | Measure-Object -Character
```

### O apply é em duas fases, de novo

Mesmo motivo do M2: **o Cloud Run se recusa a criar revisão que monte um secret sem nenhuma
versão.** A ordem é:

1. `apply` criando só os contêineres dos secrets novos, sem o volume e sem os `env`:

   ```powershell
   cd terraform
   terraform apply -target="google_secret_manager_secret.wallet" -target="google_secret_manager_secret.wallet_password"
   ```

   As aspas não são estilo: o PowerShell 5.1 divide argumento não citado no `.` e o Terraform
   responde `Invalid target`.

2. Subir os cinco valores, como acima. Os três antigos passam de `placeholder` para valor real.

3. `apply` completo, que acrescenta o volume, o `volume_mount` e as duas variáveis novas:

   ```powershell
   terraform apply
   terraform plan     # No changes
   ```

Inverter a ordem rende `Revision ... is not ready and cannot serve traffic`, com uma mensagem que
não menciona secret nenhum.

### Depois do apply, confirme que a wallet não virou variável de ambiente

```bash
gcloud run services describe ticketops --region us-central1 \
  --format='value(spec.template.spec.containers[0].env)' | grep -c "BEGIN"   # 0

gcloud run services describe ticketops --region us-central1 --format=yaml | grep -A6 volumeMounts
```

O caminho errado é convidativo e está detalhado em
[Infraestrutura](../infra/README.md#armadilhas): acrescentar `"db-wallet"` ao `local.db_secrets`
faria o `dynamic "env"` do `run.tf` criar uma variável `DB_WALLET` com o PEM inteiro dentro, sem
erro e sem aviso.

## O pool, recalibrado

O pool era `min=1, max=4`. Duas coisas mudaram.

### A aritmética das sessões

O limite é do banco, não da aplicação:

```
max_instance_count × pool max  =  2 × 4  =  8 sessões no teto
```

O Always Free em 1 OCPU comporta na ordem de 20 sessões simultâneas — confirme o número na
console, porque muda com a versão — então há folga. O que **não** há é folga para subir o
`max_instance_count` sem revisar o `max` do pool. Os dois números moram em arquivos diferentes
(`terraform/run.tf` e `app/db.py`) e a conta está comentada nos dois, porque quem os mexer no
futuro não vai lembrar que estão acoplados. O sintoma de errar é `ORA-00018` em produção.

### `min=0`, e o 503 que mudou de lugar

Com `min=1`, o `create_pool` abria uma conexão na criação do pool — um handshake TLS
atravessando a internet até a OCI, pago no cold start, antes da primeira resposta. E uma
instância parada segurava uma sessão do banco sem servir ninguém.

Com `min=0` o pool é criado sem conectar e conecta no primeiro `acquire()`. Medido:

```
create_pool(min=0, dsn=<inalcançável>)  ->  OK em 0,001s,  opened=0
pool.acquire()                          ->  DatabaseError
```

Isso **move o 503 de lugar**, e é por isso que o M4 precisou mexer no código. Antes, banco
inacessível fazia o `create_pool` estourar e o `init_pool` tolerante já devolvia 503. Agora o
`create_pool` **tem sucesso** e a falha aparece no `acquire()` — como `oracledb.DatabaseError`
com um `ORA-12541`, `ORA-12170` ou `DPY-6005`, que não estão na tabela de tradução do
`app/errors.py` e portanto virariam **500**. Um 500 diz "eu tenho um bug"; a distinção que o M3
construiu se perderia exatamente no cenário em que ela mais importa.

O `acquire()` recebeu o mesmo tratamento que o `create_pool` já tinha:

```python
try:
    conn = pool.acquire()
except oracledb.DatabaseError:
    logger.exception("Erro ao obter conexão do pool.")
    raise HTTPException(status_code=503, detail=_INDISPONIVEL) from None
```

Duas consequências que valem estar escritas:

- **Credencial errada agora também é 503**, não erro na subida: com `min=0` o `ORA-01017` só
  acontece no `acquire()`. Quando o `/ready` falhar, leia o log, não só o status — o
  `logger.exception` diz qual `ORA-` foi.
- **Uma conexão que morre depois do `acquire()`** (um `ORA-03113` no meio da query) ainda cai no
  handler genérico e vira 500. É raro por causa do `ping_interval`, e a correção — mapear os
  códigos de rede para 503 no `app/errors.py` — ficou fora do M4 de propósito, para não
  aumentar o escopo.

### `ping_interval` é a rede de segurança que ninguém configura

O `cpu_idle = true` do Cloud Run estrangula a CPU entre requisições e `min_instance_count = 0`
derruba a instância. Uma conexão no pool sobrevive à instância ficando parada e pode estar morta
do outro lado quando a próxima requisição chegar.

O `python-oracledb` pinga conexões mais velhas que `ping_interval` (60s por default) no
`acquire()`, e é isso que transforma "conexão morta" em "reconecta e segue". **Não precisa mudar
o valor; precisa saber que existe** — porque no dia em que alguém o colocar em `-1` para
"economizar um round trip", os `ORA-03113` intermitentes vão levar um dia para serem explicados.

## A rota de readiness

O `/health` não toca o banco. Essa decisão é do M0 e continua valendo — o smoke test da pipeline
usa esse endpoint, e acoplar o banco a ele faria uma indisponibilidade do ADB derrubar o deploy.

Mas o M4 criou um estado novo que ninguém observava: **a revisão fica `Ready`, o `/health`
responde 200, e o banco está inacessível.** O deploy passa, a pipeline fica verde, e a API
devolve 503 em tudo que importa.

```python
@app.get("/ready", tags=["infra"], response_model=ReadyOut)
def ready(conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM dual")
        cur.fetchone()
    return {"status": "ready", "database": "ok"}
```

Ela usa o `get_conn`, então herda o 503 de graça: banco fora, `/ready` responde 503 com o mesmo
corpo que `/chamados`. As duas rotas respondem perguntas diferentes e nenhuma substitui a outra:

| Rota | Pergunta | Toca o banco |
| --- | --- | --- |
| `/health` | a aplicação subiu? | não |
| `/ready` | a aplicação alcança o ADB? | sim, `SELECT 1 FROM dual` |

## O keep-alive, que não podia esperar o M5

**Um ADB Always Free sem atividade é parado automaticamente** — na documentação atual, após 7
dias consecutivos — e um banco parado por tempo suficiente pode ser recuperado pela Oracle e
removido. Confirme os números na console, porque já mudaram.

Para um projeto de portfólio isso falha do jeito mais silencioso possível: o link vai numa
candidatura, alguém abre três semanas depois, e a API responde 503. A infraestrutura está
perfeita e a demonstração está morta.

O remédio é uma requisição por dia, e o Cloud Scheduler resolve com um dos seus 3 jobs grátis:

```
Cloud Scheduler ──(GET diário)──> https://<url>/ready ──> SELECT 1 FROM dual
```

Está em [`terraform/scheduler.tf`](../../terraform/scheduler.tf). Um recurso mata dois problemas:
mantém o ADB acordado **e** é um monitor sintético — se o `/ready` falhar, o job falha.

Isso não podia esperar o M5: o M5 pode levar semanas e a contagem dos 7 dias começou no dia em
que o banco nasceu. O que falta é a voz — hoje o job falha em silêncio, visível só no Cloud
Logging. Dar-lhe um canal de notificação é M5.

**Cuidado com a ordem.** O job é criado pelo `terraform apply`, mas a rota que ele chama vem da
**imagem**, e o Terraform não publica imagem — `template[0].containers[0].image` está em
`ignore_changes` desde o M2, e quem faz deploy é o CI no merge. Entre o `apply` da wallet e o
merge do código existe uma janela em que o job já está ativo e o `/ready` ainda devolve **404**.

Nessa janela o keep-alive **não está mantendo nada acordado**: um 404 é servido pelo FastAPI sem
tocar no banco, então a contagem de inatividade do ADB continua correndo enquanto o job "roda
todo dia". Ele falha, e falha em silêncio até o M5.

Conferir que ele está de pé:

```bash
gcloud scheduler jobs describe ticketops-adb-keepalive --location us-central1 \
  --format='value(state,status.code,lastAttemptTime)'
gcloud scheduler jobs run ticketops-adb-keepalive --location us-central1   # dispara agora
```

## Como validar o milestone

O par de respostas do M3 mudou de significado, e é essa mudança que prova o M4:

```bash
URL=$(cd terraform && terraform output -raw service_url)

curl -s "$URL/health"     # 200 — segue sem tocar o banco
curl -s "$URL/ready"      # 200 {"status":"ready","database":"ok"}   <- rota nova
curl -s "$URL/chamados"   # 200 e uma lista JSON  (era 503 no M3)
```

No PowerShell, `curl.exe` e não `curl` — o apelido para `Invoke-WebRequest` ignora as flags.

**O `SELECT` funcionando não prova gravação.** O ciclo completo, contra produção:

```bash
CID=$(curl -s -X POST "$URL/clientes" -H 'content-type: application/json' \
        -d '{"nome":"Validacao M4","email":"m4@ticketops.test"}' | jq -r .ID)
TID=$(curl -s -X POST "$URL/chamados" -H 'content-type: application/json' \
        -d "{\"cliente_id\":$CID,\"titulo\":\"Validacao M4\",\"descricao\":\"ok\"}" | jq -r .ID)
curl -s -X POST "$URL/chamados/$TID/comentarios" -H 'content-type: application/json' \
        -d '{"autor":"validacao","texto":"comentario de validacao"}'
curl -s -X PATCH "$URL/chamados/$TID" -H 'content-type: application/json' -d '{"status":"R"}'
curl -s "$URL/chamados/$TID"    # status R, data_resolvido preenchida, comentário aninhado
```

Isso exercita o CLOB, a lista aninhada, o trigger de `UPDATE` e o `NVL(data_resolvido, ...)` —
tudo contra o ADB, não contra o container.

Uma observação que a própria API impõe: **o cliente de validação não se apaga pelo `DELETE`.**
Ele tem um chamado, e excluir cliente com chamado devolve 409 — a regra do M1, que existe porque
o histórico é o ativo. Chamado também não tem `DELETE`. Então ou o registro fica (e não é má
ideia: um helpdesk vazio parece quebrado), ou some por SQL no ADB:

```sql
DELETE FROM ticketops.comentarios WHERE chamado_id IN
  (SELECT id FROM ticketops.chamados WHERE cliente_id = 1);
DELETE FROM ticketops.chamados  WHERE cliente_id = 1;
DELETE FROM ticketops.clientes  WHERE id = 1;
COMMIT;
```

E as confirmações herdadas:

```bash
cd terraform && terraform plan     # No changes
```

O CI verde num PR qualquer, com **68 testes ou mais**. Se o número caiu, algum teste passou a
depender de configuração que o runner não tem.

## Latência agora é uma característica da arquitetura

Cada query sai do Cloud Run em Iowa, atravessa a internet pública e chega ao ADB em Vinhedo. Não
são "alguns milissegundos": a ida e volta entre `us-central1` e o sudeste do Brasil fica na ordem
de **120 a 150 ms**, e a rota de fibra é bem maior que os 9.000 km em linha reta. **Meça, não
confie neste número** — ele varia com a rota do dia.

Medido de uma máquina no Brasil, contra a produção, com o pool quente:

| Rota | Toca o banco | Tempo total |
| --- | --- | --- |
| `GET /health` | não | **~0,48 s** |
| `GET /chamados` | sim, 1 query | **~0,95 s** |

A subtração é o que interessa: o `/health` já custa meio segundo **sem chegar perto do banco**,
porque a requisição sai do Brasil, vai até Iowa e volta. O banco acrescenta outros **~0,45 s**.

O caminho de uma requisição de demonstração cruza o equador **quatro vezes**:

```
navegador (BR) ──> Cloud Run (Iowa) ──> ADB (Vinhedo) ──> Cloud Run (Iowa) ──> navegador (BR)
```

E ~450 ms para uma única query é mais que um round trip: o modo thin gasta idas e voltas em
parse, execute e fetch, e o `ping_interval` acrescenta mais uma quando a conexão está parada há
mais de 60 s — o que, numa API de portfólio sem tráfego, é **quase sempre**. Nesta topologia o
ping deixou de ser um detalhe e virou um pedágio por requisição. Continua valendo o preço: a
alternativa é uma conexão morta virando `ORA-03113` no meio de uma query, e aí o custo é um 500.

Não é problema para uma API de demonstração, e é a resposta honesta para "por que multi-cloud é
mais lento": porque é. Mas a conclusão deixa de ser teórica: **reduzir round trips passou a valer
a pena de verdade.** O `GET /chamados/{id}` faz duas queries — o chamado e os comentários — e
poderia fazer uma só. Cache não resolve; menos idas e voltas resolve.

## Custo

Continua R$ 0, agora em duas contas.

| Item | Situação |
| --- | --- |
| ADB Always Free (OCI) | 2 instâncias de 1 OCPU e 20 GB, sem prazo de validade — **mas para após ~7 dias sem atividade** |
| Secret Manager | 6 versões ativas grátis; passou de 3 para **5**. Uma de folga, e ela só existe porque as versões `placeholder` foram destruídas |
| Egress GCP → OCI | A franquia do Cloud Run é de saída **na América do Norte**, e o destino aqui é a América do Sul — vale confirmar em qual faixa o tráfego cai. Na prática, uma query de API de chamados são alguns KB: mesmo fora da franquia, arredonda para zero |
| Ingress na OCI | Grátis. O egress da OCI tem 10 TB/mês no free tier |
| Cloud Scheduler | 3 jobs grátis por mês; o keep-alive usa um |
| Cloud NAT | **Não usado, e é de propósito** — seria o custo do caminho TLS-sem-wallet |

São **duas nuvens, dois alertas**: o alerta de orçamento do GCP (Billing → Budgets & alerts) e o
equivalente na OCI (**Billing → Budgets**), com aviso em qualquer valor acima de zero.

## O que ficou de fora, e para onde foi

- **Provisionar o ADB por Terraform.** O provider da OCI funciona e o
  `oci_database_autonomous_database` é direto, mas exige uma **chave de API da OCI** — credencial
  de longa duração — e, se entrasse na mesma raiz do Terraform atual, todo `plan` do GCP passaria
  a exigir credencial da OCI. A saída seria um `terraform/oci/` com prefixo de state próprio,
  para que a configuração do GCP continue aplicável por quem não tem conta na OCI. Fica
  registrado; o ADB é criado uma vez.
- **A geração da wallet, em qualquer hipótese**, pelo motivo da seção do Secret Manager.
- **Alerta de 5xx e logs estruturados** — M5.
- **`GET /dashboard` e o dashboard APEX** — M6. O APEX já vem ligado no ADB, então o dashboard
  opcional deixou de exigir infraestrutura nova: é um workspace no banco que acabou de nascer.
