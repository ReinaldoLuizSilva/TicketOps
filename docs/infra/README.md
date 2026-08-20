# Infraestrutura — Terraform no GCP

Este diretório documenta a infraestrutura em `terraform/`, que provisiona o que hospeda a
API: **Cloud Run**, **Artifact Registry** e **Secret Manager**, com o state num bucket do
Cloud Storage. Nada é criado pelo console, e não existe chave de service account em lugar
nenhum do projeto.

Entregue no **M2** e estendido no **M3**, que acrescentou a federação de identidade para o
GitHub Actions — ver [Pipeline CI/CD](../cicd/README.md). A conexão com o Autonomous Database é
do M4, e os alertas são do M5.

## Pré-requisitos

| | Versão / requisito |
| --- | --- |
| `gcloud` CLI | autenticado, e com ADC gerado (ver abaixo) |
| Terraform | ≥ 1.9 |
| Projeto GCP | com **billing habilitado** — o free tier exige cartão cadastrado, mesmo custando R$ 0 |
| APIs de bootstrap | `cloudresourcemanager` e `serviceusage` habilitadas na mão |

São **dois** logins diferentes, apesar do nome parecido:

```bash
gcloud auth login                          # para o próprio comando gcloud
gcloud auth application-default login      # para o Terraform e bibliotecas Google (ADC)
```

Rodar só o primeiro e o Terraform reclamar de `could not find default credentials` é o erro
mais comum de quem começa. Na tela de consentimento do segundo, **marque todas as caixas** —
se passar direto, só `openid` e e-mail são concedidos e o comando falha com
`cloud-platform scope is required but not consented`.

Depois, aponte o quota project para evitar o aviso de divergência:

```bash
gcloud auth application-default set-quota-project ticketops-63450
```

O ADC é **único por máquina** (`%APPDATA%\gcloud\application_default_credentials.json` no
Windows). Trocar de configuração do `gcloud` **não** troca a credencial que o Terraform usa:
para isso é preciso rodar `application-default login` de novo com a outra conta.

As demais APIs (`run`, `artifactregistry`, `secretmanager`, `iam`, e desde o M3 `sts` e
`iamcredentials`) são habilitadas pelo próprio Terraform, em `apis.tf`. As duas de bootstrap
são exceção por um ovo-e-galinha: é a Service Usage API que permite habilitar as outras, então
ela precisa estar ligada antes do primeiro `terraform apply`.

As duas do M3 existem para a federação de identidade: sem `sts` e `iamcredentials` o
`google-github-actions/auth@v2` falha na troca do token OIDC por credencial do GCP. Habilitação
de API é eventualmente consistente — se o primeiro `apply` depois de acrescentá-las falhar com
*"Identity Pool API has not been used in project ... before or it is disabled"*, rode o `apply`
de novo sem mexer em nada.

### Região

Tudo em **`us-central1`**. A escolha não é arbitrária: é uma das três regiões com Always Free
no Cloud Storage (as outras são `us-east1` e `us-west1`), e manter Artifact Registry e Cloud
Run na mesma região evita egress entre regiões no pull da imagem. Fora dessas três, o bucket
do state passa a ser cobrado.

## Bootstrap: o bucket do state

O bucket é criado **fora** do Terraform, uma única vez, de propósito: o backend `gcs` precisa
dele existindo antes do primeiro `init`, e não se gerencia com Terraform o bucket que guarda
o state desse mesmo Terraform.

```bash
gcloud storage buckets create gs://ticketops-tfstate-63450 \
  --location=us-central1 \
  --uniform-bucket-level-access \
  --public-access-prevention

gcloud storage buckets update gs://ticketops-tfstate-63450 --versioning
```

- **`--versioning`** é o que salva de um state corrompido ou de um `apply` interrompido no
  meio. Não é opcional na prática.
- **`--public-access-prevention`** porque o state guarda nomes de recurso e configuração.
  Nunca deve ser público.

O nome leva sufixo porque nomes de bucket são **globais** no GCP. E o bloco `backend` não
aceita variável, então o nome vai literal em `versions.tf`.

A alternativa — um `terraform/bootstrap/` com state local — funciona, mas deixa um state
órfão para versionar ou esquecer. Uma linha de `gcloud` documentada é mais honesta.

## Estrutura

```
terraform/
  versions.tf              required_version, required_providers, backend "gcs"
  providers.tf             provider google
  variables.tf             project_id, region, repo_name, service_name, image, github_repo
  terraform.tfvars.example valores de exemplo, versionado
  apis.tf                  google_project_service
  registry.tf              Artifact Registry + cleanup policy
  secrets.tf               contêineres dos secrets, sem valores
  iam.tf                   service account de runtime + bindings
  run.tf                   Cloud Run + acesso público
  wif.tf                   Workload Identity Federation, SA de deploy e seus bindings
  outputs.tf               URL do serviço, repositório de imagens, as duas SAs, provider de WIF
```

O `.terraform.lock.hcl` **é versionado** — é ele que fixa os hashes dos providers e garante
que um `init` amanhã resolva a mesma versão de hoje. O `.gitignore` barra
`terraform/.terraform/`, `*.tfstate*` e `*.tfvars`; o `terraform.tfvars.example` passa porque
não casa com `*.tfvars`.

## Recursos provisionados

| Recurso | Para quê |
| --- | --- |
| `google_project_service` | Habilita as APIs, com `disable_on_destroy = false` |
| `google_artifact_registry_repository` | Repositório Docker, com cleanup policy |
| `google_secret_manager_secret` | Um por credencial (`DB_USER`, `DB_PASSWORD`, `DB_DSN`) — **só o contêiner** |
| `google_service_account` | Duas: a identidade de runtime do Cloud Run e a de deploy da pipeline |
| `google_secret_manager_secret_iam_member` | `secretAccessor` para a SA de runtime, **por secret** |
| `google_cloud_run_v2_service` | O serviço |
| `google_cloud_run_v2_service_iam_member` | `allUsers` com `roles/run.invoker` (API pública) e `run.admin` para a SA de deploy, **no serviço** |
| `google_iam_workload_identity_pool` | O pool `github` das identidades federadas do GitHub Actions |
| `google_iam_workload_identity_pool_provider` | Provider OIDC do issuer do GitHub, com `attribute_mapping` e `attribute_condition` |
| `google_service_account_iam_member` | `workloadIdentityUser` para o `principalSet` do repositório, e o `actAs` da SA de deploy sobre a de runtime |
| `google_artifact_registry_repository_iam_member` | `artifactregistry.writer` para a SA de deploy, **no repositório** |

Vinte e quatro recursos no total — eram quinze antes do M3. O bucket do state não está na
lista, pelo motivo da seção anterior. Os nove que o M3 acrescentou estão documentados em
[Pipeline CI/CD](../cicd/README.md); aqui ficam porque vivem no mesmo Terraform.

## Como aplicar

```powershell
cd terraform
Copy-Item terraform.tfvars.example terraform.tfvars   # ajuste o project_id
terraform init
terraform apply
terraform plan            # deve dizer "No changes"
```

### Numa infraestrutura vazia, o apply é em duas fases

Do zero — sem os secrets existindo — um `apply` único **falha**. Um secret sem nenhuma versão
não pode ser lido; o Cloud Run referencia as credenciais com `version = "latest"`, não
resolve nada, a revisão não fica `Ready`, e o Terraform falha esperando por ela.

Isso não é defeito: é a consequência direta da decisão de que valor de segredo nunca passa
pelo Terraform (ver [Decisões](#decisões)). A sequência é:

```powershell
terraform apply -target="google_secret_manager_secret.db"

"placeholder" | gcloud secrets versions add ticketops-db-user     --data-file=-
"placeholder" | gcloud secrets versions add ticketops-db-password --data-file=-
"placeholder" | gcloud secrets versions add ticketops-db-dsn      --data-file=-

terraform apply
```

Placeholders bastam até o M4, quando os valores reais do Autonomous Database entram — aí o
método de escrita importa, ver [Armadilhas](#armadilhas).

### Validação

```powershell
terraform output -raw service_url
curl.exe -s -o NUL -w "%{http_code}`n" "$(terraform output -raw service_url)"
```

A raiz responde **200**. Enquanto a imagem for a placeholder do Google, o corpo é a página de
exemplo do Cloud Run — e `/health` também devolve 200, porque aquele container responde em
qualquer caminho. O critério para saber quem está servindo é o **corpo**, não o status: HTML
de exemplo é placeholder; JSON `{"status":"ok","service":"ticketops",...}` é a aplicação.

## Como destruir

```powershell
terraform destroy
```

Duas consequências a saber:

- **As APIs continuam habilitadas**, por `disable_on_destroy = false`. Desligar API é efeito
  colateral no projeto inteiro, fora do escopo deste state.
- **As versões dos secrets vão junto** com os contêineres. Um `apply` seguinte precisa das
  duas fases descritas acima.

Reconstruir depois de um `destroy` devolve a **mesma URL** do serviço: o Cloud Run deriva o
hostname de projeto, serviço e região, não de um identificador aleatório por revisão. Um link
de portfólio não quebra num rebuild.

## Decisões

**Nenhuma chave de service account.** O Terraform autentica por ADC; no M3 o GitHub Actions
autentica por Workload Identity Federation. Chave de SA é credencial de longa duração — não
existe `google_service_account_key` neste projeto, e não deve passar a existir.

**Valor de segredo nunca passa pelo Terraform.** `google_secret_manager_secret_version` com
`secret_data` grava o valor **em texto claro** no state, e o state mora num bucket. O
Terraform declara *que* o segredo existe e *quem* pode ler; o valor entra por `gcloud`. A
fronteira custa o apply em duas fases, e vale.

**Service account dedicada, não a default.** A SA default do Compute Engine vem com
`roles/editor` no projeto. A SA de runtime recebe `secretAccessor` **no recurso de cada
secret**, não no projeto — a diferença entre "esta API lê estes três segredos" e "esta API lê
todos os segredos que existirem".

**Escala a zero, com teto.** `min_instance_count = 0` significa cold start no primeiro
request; é uma escolha, não esquecimento, e é o argumento do Cloud Run. `min = 1` manteria
instância acesa 24/7 e é o erro mais caro possível aqui. O `max_instance_count = 2` importa
duas vezes: agora contra custo, no M4 contra o limite de sessões do Autonomous Database
Always Free. Com `cpu_idle = true`, paga-se CPU só durante o request.

**Cleanup policy no Artifact Registry não é opcional.** O Always Free é 0,5 GB, e sem política
o repositório cresce a cada merge sem nunca encolher. Medido nos três primeiros deploys do M3:
**91,14 MB com duas imagens, 114,61 MB com três** — ou seja, **~23,5 MB por deploy**, mesmo
quando o deploy não muda uma linha de código da aplicação.

Vale saber por que não é menos: a expectativa razoável é que layers idênticas sejam
compartilhadas e o custo marginal seja a layer do `app/`, de alguns KB. Não é o que acontece,
porque layer de Docker inclui o timestamp dos arquivos — cada build do CI roda num runner
limpo, o `checkout` dá mtime novo a tudo, e sem cache de build o `RUN pip install` também
produz digest novo. Não há o que deduplicar.

Com três versões retidas o teto fica em ~115 MB de 500 MB. É folga por margem, não por
compartilhamento, e é o que permitiria subir a retenção para 5 ou 6 versões se a janela de
rollback de três deploys ficar curta. A política é sem componente de tempo,
de propósito — um `DELETE` por idade apagaria a imagem em produção num período sem deploy, e
o Cloud Run não conseguiria subir instância nova. O par usado é um `DELETE` de tudo mais um
`KEEP` das 3 versões mais recentes; **`KEEP` tem precedência sobre `DELETE`**, então o efeito
é "mantenha as 3 mais recentes, apague o resto".

**O Terraform não disputa a imagem com o CI.** A primeira revisão aponta para
`us-docker.pkg.dev/cloudrun/container/hello`, porque no primeiro `apply` o Artifact Registry
acabou de ser criado, vazio. E `template[0].containers[0].image` está em `ignore_changes`:
sem isso, cada `terraform apply` reverteria o deploy que a pipeline acabou de publicar.

A imagem, porém, não é o único campo que o deploy mexe. Todo `gcloud run deploy` grava também
`client` e `client_version` no serviço, registrando qual cliente o modificou por último — e o
Terraform, que não tem esses campos na configuração, planeja zerá-los. O `plan` fica assim,
para sempre:

```
~ google_cloud_run_v2_service.api will be updated in-place
    - client         = "gcloud" -> null
    - client_version = "568.0.0" -> null
```

O custo não é o campo, é o sinal: com esse ruído permanente o `plan` nunca mais diz
`No changes` e deixa de servir como detector de drift. Os dois entram no `ignore_changes` ao
lado da imagem. Não precisa de `apply` para convergir — `ignore_changes` só afeta o cálculo do
plano.

**`allUsers` como `run.invoker`** porque é uma API pública. Esse binding falha se o projeto
estiver sob uma organização com `constraints/iam.allowedPolicyMemberDomains`; a policy
efetiva deste projeto está em `ALLOW`.

**Versões fixadas.** `required_version >= 1.9` e provider google em `~> 6.0` (resolvido em
6.50.0). Provider do GCP muda rápido, e um `apply` que funcionava mês passado e falha hoje
por bump silencioso de major é tempo perdido. O backend GCS faz lock de state pelo próprio
objeto — não precisa de tabela de lock separada.

## Armadilhas

Todas foram encontradas construindo, não lendo documentação. Ficam registradas porque nenhuma
delas é óbvia e várias custaram tempo.

### `deletion_protection` é invisível até o destroy

`google_cloud_run_v2_service` tem `deletion_protection = true` por default no provider 6.x.
Se o campo for **omitido** da configuração, config e state concordam no valor padrão, o
`plan` diz `No changes`, e nada indica problema — até o `terraform destroy` falhar com
`cannot destroy service without setting deletion_protection=false and running terraform
apply`.

Pior: o remédio exige um `apply` antes do `destroy`, porque a flag vive no recurso no GCP, não
só no state. E se o `destroy` já tiver removido outros recursos antes de chegar no serviço, o
`apply` os recria no caminho.

**Um `plan` limpo não prova que a infraestrutura é destruível.**

### Existem dois blocos `scaling`, e eles são diferentes

`google_cloud_run_v2_service` tem `scaling` dentro de `template` (por revisão:
`min_instance_count`, `max_instance_count`) **e** um `scaling` de nível de serviço
(`min_instance_count`, `manual_instance_count`, `scaling_mode`).

A API devolve o de nível de serviço preenchido com zeros e `scaling_mode` vazio. Como a
configuração não o declara, o Terraform planeja removê-lo — em toda execução, para sempre.
Declará-lo explicitamente é frágil (`scaling_mode = ""` não é valor válido de escrever, e
`manual_instance_count` conflita com modo automático), então ele entra no `ignore_changes`.

### `terraform state mv` mexe só no state

Renomear um recurso exige os **dois** lados: editar o `.tf` e mover no state. Fazer só um
produz um `plan` com "N to add / N to destroy" e nomes quase idênticos — essa é a assinatura
do erro. Aplicar esse plan desfaz o `state mv`.

### O PowerShell quebra endereços de recurso no ponto

No Windows PowerShell 5.1, um argumento não citado é dividido no `.`:

```
-target=google_secret_manager_secret.db
   →  argv: '-target=google_secret_manager_secret'  +  '.db'
```

O Terraform recebe um tipo sem nome e responde `Invalid target`. Vale para `-target`,
`state mv`, `state show`, `import` e `taint` — **qualquer endereço de recurso precisa de
aspas**:

```powershell
terraform apply -target="google_secret_manager_secret.db"
terraform state mv 'google_x.a[\"k\"]' 'google_x.b[\"k\"]'
```

No caso dos colchetes, as aspas internas precisam de barra invertida: aspas simples do
PowerShell não protegem as duplas na chamada de um executável nativo.

### Pipe do PowerShell contamina valor de segredo

`"valor" | gcloud secrets versions add ... --data-file=-` grava **16 bytes** para uma string
de 11: o pipe acrescenta BOM UTF-8 na frente e CRLF no fim.

```
EF BB BF  70 6C 61 63 65 68 6F 6C 64 65 72  0D 0A
└─ BOM ─┘ └────── "placeholder" ──────────┘ └CRLF┘
```

Irrelevante em placeholder. **Fatal com credencial real**: o console mostra o valor correto
na tela, a env var é injetada, e a autenticação falha com erro genérico de credencial
inválida — porque o que chegou no banco foi `﻿senha\r\n`. Vale para senha e para DSN.

O jeito correto, sem BOM e sem newline final:

```powershell
$sec   = Read-Host "valor" -AsSecureString
$valor = [System.Net.NetworkCredential]::new("", $sec).Password

$f = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($f, $valor, (New-Object System.Text.UTF8Encoding($false)))
gcloud secrets versions add ticketops-db-password --data-file=$f
Remove-Item $f -Force
```

`UTF8Encoding($false)` mata o BOM; `WriteAllText` não acrescenta newline. Confira depois com
`--out-file` e conte os bytes: para senha em ASCII, o número tem de bater com o de
caracteres. (`ConvertFrom-SecureString -AsPlainText` é PowerShell 7+ e não existe no 5.1.)

### O container `hello` responde 200 em qualquer caminho

A imagem placeholder do Google não devolve 404 para rota inexistente — serve a mesma página de
exemplo em `/`, `/health`, `/chamados` e qualquer outro path. Distinguir placeholder de
aplicação pelo status HTTP não funciona; use o corpo da resposta.

Confirmado na prática no M3: momentos antes do primeiro deploy real, `GET /chamados` na URL
pública devolvia **200 com o HTML "Congratulations | Cloud Run"**. É por isso que o smoke test
da pipeline faz `grep '"service":"ticketops"'` no corpo em vez de olhar o código HTTP. A
armadilha volta a valer para quem recriar a infraestrutura do zero, porque a primeira revisão é
sempre a placeholder.

### Limites do Always Free são por conta de faturamento

Não por projeto. Projetos antigos na mesma conta de faturamento dividem a cota:

```bash
gcloud billing projects list --billing-account=<ID>
```

O limite do Secret Manager é de **6 versões ativas**, e cada rotação cria uma versão. Passar
de seis sem destruir as antigas começa a contar:

```bash
gcloud secrets versions destroy 1 --secret=ticketops-db-password
```

## Custo

O projeto é desenhado para caber no Always Free, mas R$ 0 depende de configuração.

| Item | Limite grátis | Estado atual |
| --- | --- | --- |
| Cloud Run | ~2M requests/mês, escala a zero | `min = 0`, `max = 2` |
| Artifact Registry | 0,5 GB de storage | 114,61 MB em 3 imagens (~23,5 MB por deploy), teto pela cleanup policy de 3 versões |
| GCS (state) | 5 GB nas regiões `us-*` | alguns KB em `us-central1` |
| Secret Manager | 6 versões ativas | 3 |
| Egress | pequeno | no M4, Cloud Run → Autonomous Database é saída para internet |

Um alerta de orçamento no console (**Billing → Budgets & alerts**), com valor baixo e avisos
em 50% e 100%, é a rede de segurança. Existe `gcloud billing budgets create`, mas a sintaxe
dos `--threshold-rule` muda entre versões e para uma configuração única não vale a briga.

## Fronteiras com os próximos milestones

**M3 — entregue.** O pool e o provider de Workload Identity Federation, a service account de
deploy com `run.admin` no serviço e `artifactregistry.writer` no repositório, e o `actAs` sobre
a SA de runtime estão em `wif.tf`. O workflow, os checks obrigatórios e as decisões da pipeline
estão em [Pipeline CI/CD](../cicd/README.md). Foi aqui que o `ignore_changes` passou a valer de
verdade — e que ficou claro que a imagem não bastava, conforme a seção de decisões acima.

**M4** — wallet do Autonomous Database no Secret Manager, montada em runtime; as variáveis
`DB_CONFIG_DIR`, `DB_WALLET_LOCATION` e `DB_WALLET_PASSWORD` passam a ser preenchidas; as
versões placeholder dos três secrets são substituídas pelos valores reais; e o pool é
recalibrado contra o limite de sessões do Always Free.

**M5** — logs estruturados em JSON (o Cloud Logging já parseia stdout em JSON), uma
`google_monitoring_alert_policy` para taxa de 5xx e um canal de notificação. Continua tudo no
mesmo Terraform.
