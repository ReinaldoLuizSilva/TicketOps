# Pipeline CI/CD — GitHub Actions e Workload Identity Federation

Um merge na `main` vira container publicado no Artifact Registry e revisão nova no Cloud Run,
sem ninguém rodar comando e sem uma única credencial do GCP no repositório. Em Pull Request, a
pipeline barra o merge que quebra lint, teste, build ou a validação do Terraform.

> Complemento de [Infraestrutura — Terraform no GCP](../infra/README.md), que descreve o que a
> pipeline consome. Os recursos de Workload Identity Federation vivem no mesmo Terraform.

## Como funciona

Um arquivo, `.github/workflows/ci.yml`, com cinco jobs. Os quatro primeiros rodam em PR e em
push na `main`; o `deploy` só em push na `main`.

| Job | O que faz | Roda em PR | Tempo medido |
| --- | --- | --- | --- |
| `lint` | `ruff check .` | sim | 16s |
| `test` | sobe Oracle por `docker compose` e roda os 66 testes | sim | 58s |
| `build` | `docker build`, sem publicar | sim | 18s |
| `terraform` | `fmt -check`, `init -backend=false`, `validate` | sim | 8s |
| `deploy` | autentica por WIF, publica a imagem e cria revisão | **não** — *skipped* | 2m29s |

Nenhum dos quatro primeiros toca o GCP. Nenhum deles tem permissão para emitir token OIDC.

Dos 2m29s do `deploy`, **101s são roteamento de tráfego** — `Creating Revision` leva 4s. O
tempo da pipeline é quase todo o Cloud Run trocando quem serve, não build nem boot.

## Autenticação: nenhuma credencial no repositório

O GitHub Actions troca um token OIDC por credencial de curta duração do GCP. Não existe secret
do GCP configurado no repositório, e não existe `google_service_account_key` no Terraform.

```
GitHub Actions ──(token OIDC)──> Workload Identity Pool "github"
                                   provider "ticketops"  [attribute_condition]
                                        │
                                        ▼
                                 SA ticketops-deploy  [principalSet]
                                        │
                          ┌─────────────┼──────────────┐
                          ▼             ▼              ▼
                    run.admin      writer no      serviceAccountUser
                    no serviço     repositório    na SA de runtime (actAs)
```

Os dois valores que o workflow precisa saem do `terraform output`:

```bash
terraform output wif_provider            # projects/371390921224/locations/global/workloadIdentityPools/github/providers/ticketops
terraform output deploy_service_account  # ticketops-deploy@ticketops-63450.iam.gserviceaccount.com
```

Os dois ficam **literais** no workflow. Não são segredo: estão no state e no console. O que é
segredo — as credenciais do banco — mora no Secret Manager e é injetado pelo Cloud Run em
runtime, nunca pela pipeline.

O nome do provider usa o **número** do projeto, não o ID. Não é preciso interpolá-lo na mão: o
atributo `.name` dos recursos de pool e provider já vem com o número, e é isso que o output
devolve.

## Checks obrigatórios na `main`

Quatro, referenciados por nome na proteção da branch:

```
lint    test    build    terraform
```

O `deploy` **não** entra na lista. Em PR ele é *skipped*, e um check que nunca reporta deixa o
PR pendente para sempre.

`Require branches to be up to date before merging` fica **desmarcado** (`strict: false`). Com
ela ligada, todo PR precisa estar atualizado com a `main` antes do merge — num repositório de
uma pessoa, com um PR por vez, isso é só atrito. O que se troca em risco é o conflito
semântico: um PR cujos checks passaram contra uma `main` mais antiga pode quebrar depois do
merge. Quando acontecer, o run de push na `main` avisa.

Marcar os checks é configuração no GitHub, não código, e **não** é feita pela API: o endpoint
de proteção é um `PUT` que exige o objeto inteiro, e omitir um campo desliga silenciosamente o
`enforce_admins` ou o histórico linear. Use a interface e verifique depois:

```bash
gh api repos/ReinaldoLuizSilva/TicketOps/branches/main/protection --jq '.required_status_checks.contexts'
gh api repos/ReinaldoLuizSilva/TicketOps/branches/main/protection \
  --jq '{admins: .enforce_admins.enabled, linear: .required_linear_history.enabled}'
```

## Decisões

**`terraform apply` fica fora do CI.** Aplicar Terraform pela pipeline exigiria dar à SA de
deploy permissão de criar e destruir IAM, secrets e o próprio pool de WIF — a pipeline passaria
a poder reescrever as próprias permissões. Para um projeto de uma pessoa, o ganho não paga o
risco. O que cabe no CI é a validação estática, que roda sem bucket e sem credencial nenhuma
graças ao `init -backend=false`.

**Permissão no recurso, não no projeto.** `run.admin` vai **no serviço** e
`artifactregistry.writer` vai **no repositório**. A diferença é entre "esta pipeline atualiza
este serviço" e "esta pipeline cria e destrói qualquer Cloud Run do projeto". Funciona porque o
serviço e o repositório já existem — foram criados pelo Terraform. O IAM do projeto não tem
**nenhuma** referência à SA de deploy, e isso é verificável:

```bash
gcloud projects get-iam-policy ticketops-63450 --format=json | grep -c ticketops-deploy   # 0
```

**Tag pela SHA do commit, nunca `latest`.** `latest` é ponteiro móvel: o Cloud Run resolve a
digest na criação da revisão, então duas revisões "iguais" podem servir imagens diferentes e
não há como saber qual código está no ar lendo a configuração do serviço. Com a SHA, a revisão
aponta para um commit, o rollback é óbvio, e a cleanup policy de "manter as 3 mais recentes"
passa a significar "os 3 últimos deploys".

**A imagem é buildada duas vezes, de propósito.** O job `build` prova que a imagem compila no
PR, mas não publica nada; o `deploy` builda de novo para publicar. Reaproveitar exigiria
empurrar imagens de PR para o registry — gastando a cota de 0,5 GB com PRs fechados e dando à
pipeline de PR permissão de escrita no repositório de imagens. Buildar duas vezes uma imagem
pequena é mais barato que os dois.

**`gcloud run deploy` só com `--image`.** Service account, secrets, scaling e limites continuam
como o Terraform os definiu. Passar outras flags é que seria perigoso: qualquer
`--set-env-vars` no comando **substitui** o conjunto inteiro de variáveis, e a pipeline
passaria a disputar com o Terraform o que o `ignore_changes` foi feito para evitar. A fronteira
é limpa — o Terraform define **como** o serviço é, a pipeline define **qual imagem** ele roda.

**Oracle de verdade no runner, não mock.** Os 66 testes são de integração contra o banco. Um
CI que os mockasse jogaria fora justamente a cobertura que o M1 construiu, e um que os pulasse
(`-m "not integracao"`) aprovaria merge sem testar nada. O volume do runner é sempre novo,
então o `database/01-schema.sql` roda na criação — o schema vem de graça, pelo mesmo caminho do
ambiente local.

**O `.env` é escrito pelo próprio workflow**, com senha descartável de `openssl rand -hex 16`.
Não é só o `pytest` que precisa dele: o `docker compose` interpola `${ORACLE_PASSWORD}` e
`${APP_USER_PASSWORD}` a partir dele. Hex é só `0-9a-f`, então a senha não tem `$`, `#` ou
aspas — importa duas vezes, na interpolação do compose e no SQL que o entrypoint executa. As
três variáveis de senha recebem o **mesmo** valor: `APP_USER_PASSWORD` cria o usuário no
container, `DB_PASSWORD` é o que a API usa para conectar; divergindo, o banco sobe e o `pytest`
morre com `ORA-01017`.

**`id-token: write` no job de deploy, não no topo do arquivo.** Os jobs de PR não falam com o
GCP e não têm por que poder emitir token. Sem a permissão o erro é `Unable to get
ACTIONS_ID_TOKEN_REQUEST_URL env variable`, que não menciona permissão nenhuma.

**O deploy não roda em PR, e isso é segurança.** Um `pull_request` de fork executa código de
terceiro; se esse job pudesse autenticar no GCP, um PR seria caminho para o projeto. A
`attribute_condition` do provider já barra (o token de um fork traz o `repository` do fork), mas
o `if` no job é a primeira das duas trancas e a que se lê sem abrir o Terraform.

**`concurrency` com `cancel-in-progress`.** Dois merges em sequência disparam dois deploys, e
não há garantia de ordem de chegada no Cloud Run: o mais lento pode terminar depois e colocar o
commit mais antigo em produção. Em PR o efeito colateral é bem-vindo — um push novo cancela o
run anterior em vez de gastar minutos com código já superado.

**`ruff` e `pytest` pinados vêm de `requirements-dev.txt`.** Nenhuma action que baixa a versão
mais recente: um bump de minor no linter acrescenta regras e a `main` fica vermelha numa manhã
em que ninguém mexeu no código.

**O `deploy` espera também o job `terraform`.** Não é obrigatório tecnicamente — o deploy não
toca Terraform — mas estabelece uma regra mais limpa: a `main` só publica quando está inteira
verde. Custa 8 segundos.

## Armadilhas

Todas foram encontradas construindo. Nenhuma é óbvia, e várias passam verde.

### Sem `exec` no `CMD`, o SIGTERM não chega à aplicação

O `CMD` precisa honrar a variável `PORT` que o Cloud Run injeta, o que pede um shell. Mas
`CMD ["sh", "-c", "uvicorn ..."]` deixa o `sh` como PID 1 e o uvicorn como filho. Quando o
Cloud Run manda SIGTERM na troca de revisão, o shell morre sozinho e o uvicorn é morto pela
derrubada do namespace — nunca vê o sinal, e o `finally` do `lifespan` (o `close_pool()`) não
roda.

Medido, mesma imagem, só a palavra `exec` de diferença:

| | `sh -c "uvicorn ..."` | `sh -c "exec uvicorn ..."` |
| --- | --- | --- |
| PID 1 | `sh` | `uvicorn` |
| Exit code no `docker stop` | **137** (SIGKILL) | **0** |
| Log de shutdown | nada | `Shutting down` → `Application shutdown complete.` |

```dockerfile
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

Com `exec` o uvicorn substitui o shell e vira PID 1. Importa no M4: sem o `close_pool()`, cada
troca de revisão vaza as sessões do pool, e o Autonomous Database Always Free tem limite
rígido de sessões. E `exit 137` no log parece OOM-kill, o que aponta a investigação para o
lugar errado.

Verificação, com o container rodando:

```bash
docker exec ticketops-api-1 sh -c 'tr "\0" " " < /proc/1/cmdline'   # tem de sair uvicorn, não sh
```

### Um typo no nome do dono abre acesso ao repositório errado

O `principalSet` e a `attribute_condition` referenciam o repositório como `dono/repo`. Um erro
de digitação no nome do dono não produz erro nenhum: o binding é criado, o Terraform aplica
limpo, e o resultado é que o **seu** repositório recebe `Unauthorized` no deploy enquanto o
repositório digitado errado — que pode existir e pertencer a outra pessoa — ganha o direito de
assumir a SA de deploy.

É a armadilha clássica do WIF (`principalSet` frouxo) numa variação que não aparece na
documentação: você não abriu para o GitHub inteiro, abriu para o repositório errado. E os dois
lados leem a mesma variável, então o erro fica consistente e invisível.

Confirme na política viva, não no state:

```bash
gcloud iam service-accounts get-iam-policy ticketops-deploy@ticketops-63450.iam.gserviceaccount.com \
  --format=json
gcloud iam workload-identity-pools providers describe ticketops \
  --location=global --workload-identity-pool=github --format='value(attributeCondition)'
```

### `attribute_condition` ausente falha com uma mensagem sobre claims

O GCP exige condição de atributo para providers do issuer do GitHub. Omiti-la não devolve
"falta a condição", devolve:

```
Error 400: The attribute condition must reference one of the provider's claims.
```

A mensagem descreve o que uma condição precisa ter, não que não existe condição. É defesa em
profundidade, não redundância: a condição filtra na entrada do provider, o `principalSet` filtra
na hora de assumir a SA. As duas.

### `gcloud run deploy` estampa `client` e `client_version`

O `ignore_changes` da imagem não basta. Todo `gcloud run deploy` grava no serviço qual cliente
o modificou por último, e o Terraform — que não tem esses campos na configuração — planeja
zerá-los:

```
~ google_cloud_run_v2_service.api will be updated in-place
    - client         = "gcloud" -> null
    - client_version = "568.0.0" -> null
```

O custo não é o campo, é o sinal: com esse ruído permanente, `terraform plan` nunca mais diz
`No changes` e deixa de servir como detector de drift. Os dois entram no `ignore_changes`, ao
lado da imagem. Não precisa de `apply` — `ignore_changes` só afeta o cálculo do plano.

### Status 200 não prova quem está servindo

A imagem placeholder do Google responde 200 em **qualquer** caminho. Antes do primeiro deploy
real, `GET /chamados` devolvia 200 com o HTML "Congratulations | Cloud Run" — numa rota que a
aplicação nem serve daquele jeito. Um smoke test que checasse só o código HTTP passaria verde
com a placeholder no ar e não detectaria um deploy que não pegou.

O smoke test faz `grep` no **corpo**:

```bash
echo "$CORPO" | grep -q '"service":"ticketops"'
```

O laço com `sleep 5` existe porque `min_instance_count = 0`: a primeira requisição depois do
deploy paga cold start.

### Typo em chave de `with:` não falha o job

`cache-dependecy-path` (sem o `n`) não quebra nada: a action emite um aviso amarelo e segue. O
job fica verde para sempre com o cache calculado pelo arquivo errado — exatamente o problema
que a chave existia para resolver. Vale ler as anotações do run, não só a cor:

```bash
gh api repos/ReinaldoLuizSilva/TicketOps/check-runs/<JOB_ID>/annotations --jq '.[] | .message'
```

### `${{` sem fechar passa pelo validador de YAML

O conteúdo de um bloco `run: |` é string opaca para o YAML — `yaml.safe_load` aceita e lista os
jobs normalmente. O GitHub, sim, valida as expressões, e um `${{` sem fechamento invalida o
**arquivo inteiro**: nenhum job roda, nem o `lint`.

Com checks obrigatórios ativos, o sintoma é pior que vermelho: os checks nunca reportam e o PR
fica travado sem nunca falhar. Checagem local, antes do push:

```bash
python -c "import yaml; d=yaml.safe_load(open('.github/workflows/ci.yml')); print(list(d['jobs'].keys()))"
```

```powershell
$i=0; Get-Content .github/workflows/ci.yml | ForEach-Object { $i++; $a=[regex]::Matches($_,'\$\{\{').Count; $b=[regex]::Matches($_,'\}\}').Count; if ($a -ne $b) { "linha $i desbalanceada: $_" } }
```

### `required_status_checks` é ovo-e-galinha

Os checks são referenciados **por nome**, e o GitHub só conhece o nome depois que o check rodou
uma vez. A ordem é: mergear o workflow → esperar o primeiro run → só então acrescentar os nomes
à proteção da `main`. Os nomes já existem depois do run do próprio PR que introduz o workflow —
não é preciso esperar um segundo run.

### Job com filtro `paths:` não pode ser obrigatório

Um job com `paths: terraform/**` não reporta em PRs que não tocam `terraform/`. Marcado como
obrigatório, ele deixa esses PRs pendentes para sempre — a mesma armadilha do `deploy`, por um
caminho diferente. Ou o job roda sempre, ou não entra na lista. Aqui ele roda sempre, e sai
barato: 8 segundos, sem falar com o GCP.

### Depois de um squash merge, a branch está morta

Não é que dê conflito às vezes: dá sempre. O commit que a `main` recebeu não é o mesmo objeto
que a branch tem, então todo push novo na branch já mergeada produz conflito nos mesmos
arquivos. Ligue **Settings → General → Automatically delete head branches** e comece todo item
novo com:

```bash
git checkout main && git pull && git checkout -b <nova-branch>
```

Se um commit foi feito na branch errada, o resgate é `cherry-pick` na branch nova — não vale
resolver o conflito.

### O boot do Oracle no runner é muito mais rápido que no Windows

Medido: `Container ticketops-db-1 Healthy` em **15,8s** no runner Ubuntu, contra **91s** em
Docker Desktop no Windows, ambos com volume novo. As imagens `gvenzl/oracle-free` embarcam um
banco pré-criado, então "primeiro boot" é abrir um banco existente; os 91s eram overhead de I/O
do WSL2.

Consequência prática: um `start_period` calibrado pelo número local vira folga larga, não
aperto. E o teto real de espera são os `retries` do healthcheck, não o `--wait-timeout` do
compose — o `--wait` falha assim que o healthcheck esgota as tentativas, então quem manda é
`interval × retries` mais o `start_period`.

## Como validar

O primeiro deploy da imagem real muda o que responde na URL pública. A prova é o par de
respostas:

```bash
URL=$(cd terraform && terraform output -raw service_url)
curl -s "$URL/health"                                       # {"status":"ok","service":"ticketops",...}
curl -s -o /dev/null -w '%{http_code}\n' "$URL/chamados"    # 503
```

```powershell
$URL = terraform -chdir=terraform output -raw service_url
curl.exe -s "$URL/health"
curl.exe -s -o NUL -w "%{http_code}`n" "$URL/chamados"
```

No PowerShell use `curl.exe` explicitamente: `curl` é apelido de `Invoke-WebRequest` no 5.1 e as
flags não valem.

`/health` em 200 com aquele JSON prova que quem serve é a aplicação. **`/chamados` em 503 é
resultado de sucesso**, não de falha: prova ao mesmo tempo que o pool tolerante funcionou (a
aplicação subiu sem banco) e que o M4 ainda não aconteceu. Os três secrets valem `placeholder`,
então o `create_pool` falha no parse do DSN — em 0,000s, sem esperar timeout de rede.

Se `/chamados` devolver 500, aí sim há bug: 500 diz "eu tenho um defeito", 503 diz "minha
dependência caiu".

A imagem no ar tem de ser a SHA do último merge:

```bash
gcloud run services describe ticketops --region us-central1 \
  --format='value(spec.template.spec.containers[0].image)'
```

E a pipeline não pode brigar com o Terraform:

```bash
cd terraform && terraform plan     # No changes
```

Por último, o teste negativo — o único que prova a segurança: abra um PR de uma branch qualquer
e confirme que o job `deploy` aparece como *skipped* e que nenhum passo tocou o GCP.

> O `terraform output service_url` e o `gcloud run deploy` devolvem URLs de formatos
> diferentes (`ticketops-<hash>-uc.a.run.app` e `ticketops-<project_number>.<region>.run.app`).
> As duas são válidas e apontam para o mesmo serviço.

## Rollback

Uma revisão pode ficar `Ready` e ainda assim estar quebrada — é o smoke test que pega isso, e
quando pega, a pipeline já roteou tráfego. Voltar não exige buildar nada:

```bash
gcloud run revisions list --service ticketops --region us-central1
gcloud run services update-traffic ticketops --region us-central1 \
  --to-revisions=ticketops-00007-abc=100
```

O limite é a cleanup policy do Artifact Registry: **3 versões retidas** significa que a janela
de rollback é de três deploys. Depois disso a imagem foi apagada e a revisão antiga não sobe
instância nova.

## Custo

| Item | Situação |
| --- | --- |
| GitHub Actions | Ilimitado em repositório **público**. Em privado são 2.000 min/mês, e a cobrança é a soma dos jobs, não o tempo de parede: ~1,7 min num run de PR e ~4,2 min num run de push na `main` |
| Artifact Registry | 0,5 GB grátis. Layers são compartilhadas e o `Dockerfile` instala dependências antes de copiar `app/`, então o custo marginal por deploy é a layer do `app/` — alguns KB. É o `requirements.txt` que, ao mudar, cria layer nova e gorda |
| Cloud Run | Uma revisão nova por merge não custa nada: revisão sem tráfego não tem instância, e `min_instance_count = 0` continua |
| Egress | O `docker push` é entrada (grátis); o pull do Cloud Run é dentro da mesma região |

## Fronteiras com os próximos milestones

**M4** — com o banco real conectado, `/chamados` deixa de devolver 503 e o smoke test pode
passar a checar o banco numa **rota de readiness separada**, sem tocar o `/health`. A decisão de
o `/health` não falar com o banco continua valendo justamente por isso: acoplar o banco a ele
faria uma indisponibilidade do Autonomous Database derrubar o deploy. O `close_pool()` no
shutdown passa a importar de verdade, contra o limite de sessões do Always Free.

**M5** — o `logger.exception` do pool tolerante passa a ser evento estruturado e pesquisável em
vez de linha de texto, e uma `google_monitoring_alert_policy` para taxa de 5xx avisa quando um
deploy quebra em produção, em vez de depender de alguém abrir a URL. O `exit 0` limpo no
shutdown importa aqui: sem ele, todo scale-down aparece como `137` e polui a linha de base do
alerta.
