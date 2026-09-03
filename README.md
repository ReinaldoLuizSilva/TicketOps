# TicketOps

[![CI](https://github.com/ReinaldoLuizSilva/TicketOps/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ReinaldoLuizSilva/TicketOps/actions/workflows/ci.yml)

API REST de gestão de chamados de suporte (mini-helpdesk), construída como projeto de
portfólio para Cloud/DevOps Engineering. A aplicação é deliberadamente simples — três
tabelas e regras de negócio diretas — para que o esforço fique na infraestrutura em volta
dela: containers, IaC, pipeline, gestão de segredos e observabilidade.

Clientes abrem chamados, analistas atualizam status e comentam. Um endpoint de dashboard
resume o atendimento: total de chamados, contagem por status e por prioridade, e o tempo médio
de resolução.

## Stack

| Camada | Tecnologia |
| --- | --- |
| API | Python 3.12, FastAPI, uvicorn |
| Banco | Oracle Database Free 23ai (local) / Oracle Autonomous Database (nuvem) |
| Driver | `python-oracledb` em modo thin, SQL puro com bind variables |
| Container | Docker, docker-compose |
| Lint e testes | ruff, pytest |

Não há ORM: as queries são escritas à mão com bind variables, tanto por desempenho quanto
para manter o domínio de banco explícito. Também não é necessário instalar o Oracle Instant
Client — o driver opera em modo thin.

## Arquitetura

Cloud Run, Artifact Registry e Secret Manager estão provisionados por Terraform (M2); desde
o M3 todo merge na `main` publica a imagem e cria uma revisão nova, autenticando por Workload
Identity Federation — sem nenhuma credencial do GCP no repositório; e desde o M4 a API grava
num Oracle Autonomous Database na OCI, por mTLS, com a wallet montada em runtime a partir do
Secret Manager. Desde o M5 os logs saem estruturados em JSON e duas políticas do Cloud
Monitoring avisam por e-mail quando o serviço responde 5xx ou fica inalcançável.

```
GitHub Actions ──(Workload Identity Federation)──> GCP
                                                    ├── Cloud Run (API em container)
                                                    ├── Artifact Registry (imagens)
                                                    ├── Secret Manager (wallet + credenciais)
                                                    ├── Cloud Logging (logs em JSON)
                                                    └── Cloud Monitoring (2 alertas + uptime check)

Cloud Run ──(mTLS via wallet)──> Oracle Autonomous Database (OCI)
```

Em produção, `GET /health` responde 200 sem tocar o banco e `GET /ready` responde
`{"status":"ready","database":"ok"}` depois de um `SELECT 1 FROM dual` no ADB. As duas rotas
respondem perguntas diferentes, e o smoke test da pipeline checa as duas.

A documentação está dividida por camada: [docs/infra](docs/infra/) para o Terraform no GCP,
[docs/cicd](docs/cicd/) para a pipeline, [docs/adb](docs/adb/) para a ponte multi-cloud com o
Autonomous Database, e [docs/observabilidade](docs/observabilidade/) para o formato de log, os
alertas e o runbook — cada uma com as decisões de projeto e as armadilhas encontradas
construindo.

## Como rodar localmente

Pré-requisitos: Docker e Docker Compose. Nada além disso — Python e Oracle rodam nos
containers.

```bash
git clone https://github.com/ReinaldoLuizSilva/TicketOps.git
cd TicketOps
cp .env.example .env    # edite as senhas antes de subir
docker compose up -d --build
```

A primeira subida leva alguns minutos: o container do Oracle inicializa o banco e executa
`database/01-schema.sql`, que cria as tabelas, índices e triggers. Acompanhe com
`docker compose logs -f db` e aguarde o container ficar `healthy`.

Com tudo no ar:

- Swagger UI: <http://localhost:8080/docs>
- Health check: <http://localhost:8080/health>
- Banco: `localhost:1522/FREEPDB1`

### Variáveis de ambiente

Todas ficam no `.env`, na raiz do projeto. O arquivo está no `.gitignore`; use o
`.env.example` como base.

| Variável | Descrição |
| --- | --- |
| `ORACLE_PASSWORD` | Senha do `SYS`/`SYSTEM` no container do banco |
| `APP_USER_PASSWORD` | Senha do usuário `ticketops`, criado pelo container |
| `DB_USER` | Usuário usado pela API (`ticketops`) |
| `DB_PASSWORD` | Senha usada pela API |
| `DB_DSN` | Connect string (`db:1521/FREEPDB1` entre containers) |

**`DB_PASSWORD` e `APP_USER_PASSWORD` precisam ter o mesmo valor.** A segunda é usada pelo
container do banco para criar o usuário da aplicação; a primeira é usada pela API para se
conectar com ele. Se divergirem, o banco sobe normalmente e a API falha na inicialização
do pool com `ORA-01017: invalid credential`.

O `DB_DSN` usa `db` como host porque esse é o nome do serviço no `docker-compose.yml`. Para
conectar de fora dos containers (SQL Developer, sqlplus), use `localhost:1522/FREEPDB1`.

Três variáveis existem para a conexão com o Autonomous Database e ficam **vazias no ambiente
local** — o container fala TCP simples:

| Variável | Em produção |
| --- | --- |
| `DB_WALLET_LOCATION` | `/wallet` — o **diretório** onde o Cloud Run monta o `ewallet.pem` |
| `DB_WALLET_PASSWORD` | a senha da wallet, vinda do Secret Manager |
| `DB_CONFIG_DIR` | continua vazia: o `DB_DSN` guarda o descritor de conexão completo, então não há `tnsnames.ora` para ler |

Como o `os.environ.get` devolve `None` quando a variável não existe, o mesmo `app/db.py` serve
os dois ambientes sem `if`. Ver [docs/adb](docs/adb/README.md).

## Endpoints

| Método | Rota | Descrição | Sucesso |
| --- | --- | --- | --- |
| `GET` | `/health` | Health check, usado pelo pipeline. **Não toca o banco** | 200 |
| `GET` | `/ready` | Readiness: `SELECT 1 FROM dual` no banco. 503 se ele estiver fora | 200 |
| `GET` | `/clientes` | Lista clientes | 200 |
| `POST` | `/clientes` | Cadastra cliente | 201 |
| `PATCH` | `/clientes/{id}` | Atualiza cliente | 204 |
| `DELETE` | `/clientes/{id}` | Exclui cliente | 204 |
| `GET` | `/chamados` | Lista chamados, com filtro opcional `?status=` | 200 |
| `POST` | `/chamados` | Abre um chamado | 201 |
| `GET` | `/chamados/{id}` | Detalhe do chamado, com seus comentários | 200 |
| `PATCH` | `/chamados/{id}` | Atualiza status, prioridade ou dados do chamado | 204 |
| `POST` | `/chamados/{id}/comentarios` | Adiciona comentário ao chamado | 201 |
| `GET` | `/dashboard` | Estatísticas: total, contagem por status e prioridade, tempo médio de resolução | 200 |

Erros seguem o padrão do FastAPI (`{"detail": "..."}`). Violações de constraint do Oracle
são traduzidas para o status HTTP correspondente em `app/errors.py` — por exemplo, e-mail
duplicado devolve 409, e não 500.

Chamado não tem `DELETE`: cancelamento é uma transição de status (`PATCH` com
`{"status": "C"}`), porque num helpdesk o histórico de atendimento é o ativo — apagar o
chamado levaria os comentários com ele. Cliente tem `DELETE`, para cadastro criado por
engano; excluir um cliente que já abriu chamado devolve 409.

### Exemplos

```bash
# abrir um chamado
curl -X POST http://localhost:8080/chamados \
  -H "Content-Type: application/json" \
  -d '{"cliente_id": 1, "titulo": "Sistema fora do ar", "descricao": "Erro 500 no login", "prioridade": "A"}'

# listar apenas os chamados em andamento
curl "http://localhost:8080/chamados?status=E"

# comentar
curl -X POST http://localhost:8080/chamados/1/comentarios \
  -H "Content-Type: application/json" \
  -d '{"autor": "Reinaldo", "texto": "Reiniciei o serviço, acompanhando."}'

# resolver (data_resolvido é preenchida automaticamente)
curl -X PATCH http://localhost:8080/chamados/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "R"}'

# cancelar (não há DELETE de chamado: cancelamento é transição de status)
curl -X PATCH http://localhost:8080/chamados/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "C"}'

# estatísticas do atendimento
curl http://localhost:8080/dashboard
```

O `/dashboard` responde com os buckets sempre completos, mesmo zerados, para que o consumidor
não precise tratar chave ausente:

```json
{
  "TOTAL": 12,
  "POR_STATUS": {"A": 5, "E": 3, "R": 4, "C": 0},
  "POR_PRIORIDADE": {"B": 2, "M": 6, "A": 3, "C": 1},
  "TEMPO_MEDIO_RESOLUCAO_HORAS": 18.75
}
```

`TEMPO_MEDIO_RESOLUCAO_HORAS` é `null` — e não `0` — quando nenhum chamado foi resolvido
ainda: zero afirmaria que a resolução foi instantânea.

No PowerShell, `curl` é alias de `Invoke-WebRequest`, que lança exceção em respostas de
erro e descarta o corpo. Use `curl.exe` para ver o JSON de resposta.

## Modelo de dados

```
CLIENTES ─< CHAMADOS ─< COMENTARIOS
```

| Tabela | Campos |
| --- | --- |
| `clientes` | `id`, `nome`, `email` (único) |
| `chamados` | `id`, `cliente_id`, `titulo`, `descricao`, `prioridade`, `status`, `data_resolvido` |
| `comentarios` | `id`, `chamado_id`, `autor`, `texto` |

As três tabelas têm colunas de auditoria (`created`, `createdby`, `updated`, `updatedby`),
preenchidas por default e por trigger de `UPDATE`.

`prioridade` e `status` são armazenados como um caractere, validados por `CHECK` no banco e
por `Literal` no Pydantic:

| `prioridade` | | `status` | |
| --- | --- | --- | --- |
| `B` | Baixa | `A` | Aberto |
| `M` | Média (default) | `E` | Em andamento |
| `A` | Alta | `R` | Resolvido |
| `C` | Crítica | `C` | Cancelado |

`data_resolvido` não é informada pelo cliente: é derivada do `status` no próprio endpoint de
atualização — preenchida ao passar para `R`, limpa em qualquer outro status.

## Desenvolvimento

Lint e testes rodam fora do container, num virtualenv local:

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt

ruff check .                    # --fix aplica as correções automáticas
pytest
```

Após alterar código da aplicação, reconstrua a imagem — o `Dockerfile` copia o diretório
`app/` na build, então reiniciar o container não é suficiente:

```bash
docker compose up -d --build
```

Após alterar `database/01-schema.sql`, recrie o volume. O diretório de inicialização do
Oracle só é executado quando o banco é criado pela primeira vez, então um restart comum
mantém o schema antigo:

```bash
docker compose down -v && docker compose up -d --build
```

CUIDADO: `-v` apaga o volume `oracle-data`, e com ele todos os dados.

### Estrutura

```
app/
  main.py            aplicação FastAPI, lifespan e registro dos routers
  db.py              pool de conexões Oracle
  schemas.py         modelos Pydantic de entrada
  errors.py          tradução de erros Oracle para status HTTP
  routers/           endpoints por recurso
database/
  01-schema.sql      DDL do container local, executado na primeira subida do banco
  adb/
    01-schema-adb.sql  o mesmo DDL para o Autonomous Database, aplicado à mão
test/                testes com pytest
```

Os dois scripts de schema existem porque o local começa com um `ALTER SESSION SET CONTAINER`
que é inválido no ADB, e o do ADB precisa criar o usuário `ticketops`, que localmente nasce do
container. É uma duplicação assumida — e `test/test_schema_adb.py` compara o DDL dos dois
arquivos, para que a divergência apareça como CI vermelho e não como produção quebrada.

O pool é criado no `lifespan` da aplicação e fechado no encerramento, com dimensionamento
pequeno (`min=0`, `max=4`). O `min=0` é escolha do M4: o pool nasce sem conectar e abre a
primeira conexão só no `acquire()`, o que tira o handshake TLS até a OCI do cold start e não
deixa instância parada segurando sessão. O teto de sessões é `max_instance_count × max` — hoje
`2 × 4 = 8` —, e os dois números estão acoplados.

### Convenções

Branches curtas com Pull Request para a `main`, conventional commits e squash merge.

## Roadmap

- [x] **M0** — API `/health` rodando local em Docker, com teste
- [x] **M1** — CRUD de chamados conectado ao Oracle, local via docker-compose
- [x] **M2** — Terraform provisionando o GCP (Cloud Run, Artifact Registry, Secret Manager)
- [x] **M3** — Pipeline CI/CD com Workload Identity Federation
- [x] **M4** — Conexão ao Oracle Autonomous Database via wallet no Secret Manager
- [x] **M5** — Observabilidade: logs estruturados e alerta de erro 5xx

O M5 está fechado: logs estruturados em JSON, duas políticas de alerta e um uptime check em
`/ready` — e **o alerta foi provado disparando**, com o Autonomous Database parado de propósito
na console da OCI e o e-mail recebido. É esse último item que separa uma política de Terraform de
monitoramento de verdade.

A pipeline, a infraestrutura, a ponte com o Autonomous Database e a observabilidade estão
documentadas em [`docs/cicd/`](docs/cicd/README.md), [`docs/infra/`](docs/infra/README.md),
[`docs/adb/`](docs/adb/README.md) e
[`docs/observabilidade/`](docs/observabilidade/README.md), com as decisões e as armadilhas
encontradas construindo.

Fora dos milestones: o `GET /dashboard` (contagens por status e prioridade, tempo médio de
resolução) está implementado. É uma query só, com agregação condicional — as contagens
precisam da tabela inteira, então separar os recortes por `WHERE` custaria um round-trip até o
Autonomous Database para cada um. O tempo médio sai de `data_resolvido - created`, com os dois
`TIMESTAMP` convertidos para `DATE` antes da subtração: em Oracle a diferença entre dois
`TIMESTAMP` é um `INTERVAL DAY TO SECOND`, que o `AVG` recusa com `ORA-00932`.
