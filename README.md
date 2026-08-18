# TicketOps

API REST de gestão de chamados de suporte (mini-helpdesk), construída como projeto de
portfólio para Cloud/DevOps Engineering. A aplicação é deliberadamente simples — três
tabelas e regras de negócio diretas — para que o esforço fique na infraestrutura em volta
dela: containers, IaC, pipeline, gestão de segredos e observabilidade.

Clientes abrem chamados, analistas atualizam status e comentam, e um endpoint de dashboard
resume as estatísticas.

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

## Arquitetura de destino

O estado atual é o ambiente local. A arquitetura em nuvem é entregue pelos milestones
seguintes (ver [Roadmap](#roadmap)).

```
GitHub Actions ──(Workload Identity Federation)──> GCP
                                                    ├── Cloud Run (API em container)
                                                    ├── Artifact Registry (imagens)
                                                    ├── Secret Manager (wallet + credenciais)
                                                    └── Cloud Monitoring (logs + alerta 5xx)

Cloud Run ──(mTLS via wallet)──> Oracle Autonomous Database (OCI)
```

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
- Banco: `localhost:1521/FREEPDB1`

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
conectar de fora dos containers (SQL Developer, sqlplus), use `localhost:1521/FREEPDB1`.

Três variáveis opcionais existem para a conexão com o Autonomous Database e ficam vazias no
ambiente local: `DB_CONFIG_DIR`, `DB_WALLET_LOCATION` e `DB_WALLET_PASSWORD`.

## Endpoints

| Método | Rota | Descrição | Sucesso |
| --- | --- | --- | --- |
| `GET` | `/health` | Health check, usado pelo pipeline | 200 |
| `GET` | `/clientes` | Lista clientes | 200 |
| `POST` | `/clientes` | Cadastra cliente | 201 |
| `PUT` | `/clientes/{id}` | Atualiza cliente | 204 |
| `DELETE` | `/clientes/{id}` | Exclui cliente | 204 |
| `GET` | `/chamados` | Lista chamados, com filtro opcional `?status=` | 200 |
| `POST` | `/chamados` | Abre um chamado | 201 |
| `GET` | `/chamados/{id}` | Detalhe do chamado, com seus comentários | 200 |
| `PATCH` | `/chamados/{id}` | Atualiza status, prioridade ou dados do chamado | 204 |
| `DELETE` | `/chamados/{id}` | Exclui chamado | 204 |
| `POST` | `/chamados/{id}/comentarios` | Adiciona comentário ao chamado | 201 |

Erros seguem o padrão do FastAPI (`{"detail": "..."}`). Violações de constraint do Oracle
são traduzidas para o status HTTP correspondente em `app/errors.py` — por exemplo, e-mail
duplicado devolve 409, e não 500.

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
```

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

O `-v` apaga o volume `oracle-data`, e com ele todos os dados.

### Estrutura

```
app/
  main.py            aplicação FastAPI, lifespan e registro dos routers
  db.py              pool de conexões Oracle
  schemas.py         modelos Pydantic de entrada
  errors.py          tradução de erros Oracle para status HTTP
  routers/           endpoints por recurso
database/
  01-schema.sql      DDL, executado na primeira subida do banco
test/                testes com pytest
```

O pool é criado no `lifespan` da aplicação e fechado no encerramento, com dimensionamento
pequeno (`min=1`, `max=4`): o Cloud Run escala horizontalmente e o Autonomous Database
Always Free tem limite de sessões.

### Convenções

Branches curtas com Pull Request para a `main`, conventional commits e squash merge.

## Roadmap

- [x] **M0** — API `/health` rodando local em Docker, com teste
- [ ] **M1** — CRUD de chamados conectado ao Oracle, local via docker-compose
- [ ] **M2** — Terraform provisionando o GCP (Cloud Run, Artifact Registry, Secret Manager)
- [ ] **M3** — Pipeline CI/CD com Workload Identity Federation
- [ ] **M4** — Conexão ao Oracle Autonomous Database via wallet no Secret Manager
- [ ] **M5** — Observabilidade: logs estruturados e alerta de erro 5xx

Pendência do M1: cobertura de testes do CRUD. O endpoint `GET /dashboard` (contagens por
status e prioridade, tempo médio de resolução) está previsto e ainda não foi implementado.
