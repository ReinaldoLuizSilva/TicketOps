# Observabilidade — logs estruturados e alerta de 5xx

Este diretório documenta como a aplicação registra o que acontece e como alguém fica sabendo
quando ela para de funcionar. São duas metades independentes: um **formatter próprio** que
transforma todo log em uma linha de JSON que o Cloud Logging entende, e uma **política de alerta**
no Cloud Monitoring que manda e-mail quando respostas 5xx aparecem.

Entregue no **M5**, o último milestone de infraestrutura. Depende do
[Terraform](../infra/README.md) para os recursos e da [pipeline](../cicd/README.md) para o `exec`
no `CMD`, sem o qual todo scale-down apareceria como término anormal.

> **Estado atual:** as duas políticas estão ligadas no Terraform, e o uptime check aponta para
> `/ready`. O que falta para o M5 fechar de fato é **provar o alerta disparando** — item 7 da
> definição de pronto. Uma política que nunca disparou é uma linha de Terraform, não é
> monitoramento; o procedimento está em [Provar o alerta](#provar-o-alerta).

## As três perguntas

Observabilidade sem pergunta é coleta de dados. As deste projeto são três:

| Pergunta | O que responde |
| --- | --- |
| *O deploy que subiu quebrou a produção?* | O alerta de 5xx, e o label `revision` no log, que diz **qual** revisão |
| *Por que a requisição das 14h32 falhou?* | O log estruturado, com `severity`, `logger`, traceback e correlação por trace |
| *O Autonomous Database parou sozinho?* | O alerta de 5xx de novo, alimentado pelo 503 — e o uptime check, que faz a requisição quando ninguém faz |

A terceira é a mais valiosa e a mais silenciosa: a infraestrutura pode estar perfeita e a
demonstração morta ao mesmo tempo, e a única coisa que distingue os dois casos é um e-mail.

## Como funciona

```
app/logging_config.py    FormatterCloudLogging  ->  uma linha de JSON em stdout
                         configurar_logging()   ->  root + os tres loggers do uvicorn
app/main.py              configurar_logging() no topo, antes do FastAPI(...)
                         middleware contexto_trace  ->  captura X-Cloud-Trace-Context
Dockerfile               PYTHONUNBUFFERED=1, uvicorn --no-access-log
terraform/monitoring.tf  canal de e-mail, politica de 5xx, uptime check
terraform/run.tf         env GCP_PROJECT (o Cloud Run nao injeta este)
```

No Cloud Run, **escrever em stdout já é escrever no Cloud Logging**: o agente lê o stream do
container e, se a linha é um JSON válido, ela vira `jsonPayload` com os campos separados e
filtráveis individualmente.

## O formato de log

Uma linha por evento. Exemplo real, emitido pelo tradutor de erro Oracle:

```json
{
  "severity": "INFO",
  "message": "erro de banco traduzido para 409",
  "logger": "app.errors",
  "logging.googleapis.com/sourceLocation": {"file": "/app/app/errors.py", "line": 25, "function": "oracle_error_handler"},
  "logging.googleapis.com/trace": "projects/ticketops-63450/traces/4bf92f3577b34da6a3ce929d0e0e4736",
  "logging.googleapis.com/labels": {"revision": "ticketops-00042-abc"},
  "ora": "ORA-00001",
  "rota": "/clientes",
  "metodo": "POST",
  "mensagem": "ORA-00001: unique constraint (TICKETOPS.UK_CLIENTES_EMAIL) violated"
}
```

### Os campos que o Cloud Logging promove

O serviço reconhece um conjunto fechado de chaves e promove cada uma ao campo correspondente da
`LogEntry`. Qualquer outra chave fica como campo comum dentro do `jsonPayload` — que é exatamente
o que se quer para os campos de negócio.

| Chave no JSON | Vira | Nota |
| --- | --- | --- |
| `severity` | a severidade da entrada | `DEBUG`, `INFO`, `NOTICE`, `WARNING`, `ERROR`, `CRITICAL`, `ALERT`, `EMERGENCY` |
| `message` | o texto principal | é o que o Logs Explorer mostra na lista colapsada |
| `logging.googleapis.com/trace` | `trace` da entrada | formato `projects/PROJETO/traces/ID` — **o nome do projeto faz parte** |
| `logging.googleapis.com/sourceLocation` | arquivo, linha e função | objeto com `file`, `line`, `function` |
| `logging.googleapis.com/labels` | labels indexadas | objeto de string para string, e só |
| `httpRequest` | o bloco de requisição | **não usamos** — o Cloud Run já emite o dele |

O `timestamp` tem chave própria e **não** é preenchido de propósito: o Cloud Logging estampa o
tempo de recebimento do stdout, que está a milissegundos do evento, e um timestamp em formato
levemente errado é descartado sem aviso. Um campo que só pode piorar não vale ser preenchido.

### Campos de negócio via `extra=`

É o que separa "JSON no log" de log estruturado de verdade:

```python
logger.warning("banco indisponível", extra={"evento": "pool_indisponivel"})
```

Tudo que vem em `extra=` cai como chave de primeiro nível no `jsonPayload`, o que permite filtrar
por `jsonPayload.ora="ORA-00001"` em vez de buscar substring numa frase. O formatter descobre
esses campos comparando o `__dict__` do registro com os atributos padrão de um `LogRecord` — o que
sobra veio de `extra=`.

Os campos em uso hoje:

| Campo | Onde | Para quê |
| --- | --- | --- |
| `ora` | `app/errors.py` | Código Oracle (`ORA-00001`), filtrável direto |
| `rota`, `metodo` | `app/errors.py` | Qual endpoint gerou o erro |
| `mensagem` | `app/errors.py` | Texto do Oracle, que traz nome de constraint e tamanhos |
| `evento` | `app/db.py` | `pool_indisponivel` quando o pool não subiu, `acquire_falhou` quando o pool está de pé e o banco recusa a conexão |

**Nunca use `message` como chave de `extra`.** Ela colide com o campo que o formatter monta a
partir de `record.getMessage()`, e o `update()` no fim do `format()` sobrescreveria o texto
principal. Daí `mensagem`, em português, como o resto do projeto.

## A tabela de severidades

A regra segue a distinção que o M3 já construiu no código:

| Situação | HTTP | `severity` | Por quê |
| --- | --- | --- | --- |
| Constraint traduzida (duplicado, FK, campo obrigatório) | 4xx | `INFO` | Cliente mandou dado inválido. É o sistema funcionando |
| `ORA` fora da tabela de tradução | 500 | `ERROR` | "Eu tenho um bug". Precisa de alguém |
| Pool ou `acquire` falhando (banco fora) | 503 | `WARNING` | Dependência externa fora. Precisa de alguém, mas o culpado é outro |
| Requisição servida | 2xx | não logamos | O log de requisição do Cloud Run já cobre |

O 503 ser `WARNING` e não `ERROR` é uma escolha deliberada: um filtro por `severity>=ERROR` deve
devolver **só** os bugs do projeto. Se a queda do Autonomous Database entrar nessa lista, ela
deixa de responder "o que eu quebrei" e passa a responder "o que está ruim" — pergunta diferente,
e já respondida pelo alerta de 5xx.

Isso não deixa o 503 sem vigilância: o alerta é sobre a **classe 5xx** da resposta HTTP, e 503
está nela. O log diz *qual* dos dois é; o alerta diz *que* algo é.

## Decisões

### Formatter próprio, não a biblioteca `google-cloud-logging`

O caminho de todo tutorial é `google.cloud.logging.Client().setup_logging()`. Não é o que este
projeto usa:

| | Biblioteca `google-cloud-logging` | Formatter próprio em stdout |
| --- | --- | --- |
| Dependências novas na imagem | `google-cloud-logging`, `google-api-core`, `grpcio`, `protobuf` — dezenas de MB | zero |
| Como o log chega ao Cloud Logging | chamada de API autenticada, em background | o agente do Cloud Run já coleta stdout |
| IAM | exige `roles/logging.logWriter` na SA de runtime | nada |
| O que acontece se falhar | log perdido, ou latência na requisição | não há o que falhar |

O ponto decisivo é o segundo: pagar uma chamada de API para entregar o que já está sendo entregue
de graça é trabalho a mais para conseguir menos. E há um efeito colateral valioso — o formatter
funciona idêntico no `docker-compose` local, sem credencial nenhuma, então o log de
desenvolvimento e o de produção têm o mesmo formato, e o "só reproduz em produção" perde um dos
seus motivos.

O custo honesto: a biblioteca captura o `trace` do header sozinha e preenche `httpRequest`. A
primeira coisa este projeto reimplementa em vinte linhas; a segunda é dispensável, porque o Cloud
Run **já** emite um log de requisição por requisição, com método, status, latência e user agent.
Reimplementá-lo seria criar uma segunda fonte de verdade pior que a primeira.

### Correlação por `ContextVar`, não por variável global

O Cloud Run injeta `X-Cloud-Trace-Context` no formato `TRACE_ID/SPAN_ID;o=1`. O middleware
`contexto_trace` em `app/main.py` guarda o `TRACE_ID` num `ContextVar`, e o formatter monta
`projects/PROJETO/traces/ID` a partir dele.

Tem que ser `ContextVar` — não variável de módulo, não thread-local. A aplicação é async, várias
requisições coexistem na mesma thread, e uma variável global faria os logs de uma requisição
aparecerem sob o trace de outra. É pior que não ter correlação nenhuma, porque parece funcionar.

Uma nota de Starlette que economiza uma tarde: `BaseHTTPMiddleware` executa a aplicação numa task
própria, que **copia** o contexto no momento da criação. Valores definidos **antes** do
`call_next` chegam ao endpoint; valores definidos dentro do endpoint não voltam para o middleware.
O código está do lado certo dessa assimetria — mas quem tentar acumular informação no contexto
durante a requisição para logar no final vai encontrar `None`.

### `GCP_PROJECT` entra por `env` no Terraform

O Cloud Run injeta `PORT`, `K_SERVICE`, `K_REVISION` e `K_CONFIGURATION` — **não** o ID do
projeto. Como o campo de trace exige `projects/PROJETO/traces/ID`, o `GCP_PROJECT` é declarado
como `env` em `run.tf`. O `K_REVISION`, esse vem de graça, e é aproveitado como label `revision`.

Sem `GCP_PROJECT` o campo de trace é omitido e o resto do log continua funcionando. Degradação
silenciosa é o comportamento certo aqui: log é o que se usa quando algo já deu errado, e não é
hora de o log ser a segunda coisa a falhar.

Vale saber que `_PROJETO` e `_REVISAO` são lidos **no import do módulo**. Mudar a variável de
ambiente depois não tem efeito — em teste, o caminho é `monkeypatch.setattr`, não `setenv`.

### O access log do uvicorn está desligado

`--no-access-log` no `CMD`. O Cloud Run emite um log de requisição por requisição, com método,
rota, status, latência, user agent e o trace já preenchido; o `uvicorn.access` emite uma linha de
texto com método, rota e status. É metade da informação, no dobro do volume, e duas contagens de
requisição que podem discordar.

O `docker-compose` local usa a mesma imagem, então o access log também some do desenvolvimento. É
aceitável — quem desenvolve tem o Swagger e os testes — e quem quiser de volta sobrescreve o
`command:` no `docker-compose.yml`.

### `PYTHONUNBUFFERED=1`

O Python bufferiza stdout em bloco quando não há TTY. O `StreamHandler` dá `flush()` a cada
emissão, então os logs propriamente ditos estão salvos — mas qualquer `print()` e qualquer saída
de biblioteca fica no buffer, e um container derrubado no scale-down leva o buffer com ele. Uma
linha de `ENV` compra a garantia.

### `LOG_FORMAT` e `LOG_LEVEL`

| Variável | Default | Efeito |
| --- | --- | --- |
| `LOG_FORMAT` | `json` | Qualquer outro valor faz `configurar_logging()` não fazer nada, devolvendo o comportamento padrão do Python |
| `LOG_LEVEL` | `INFO` | Nível aplicado ao root e aos loggers do uvicorn |

O `LOG_FORMAT` tem dois usuários legítimos: o `test/conftest.py`, que define `texto` para não
brigar com o `caplog` do pytest, e quem prefere ler texto no terminal local. Um flag com dois
usuários é configuração; com um, é workaround.

## O alerta: contagem, não taxa

Todo material sobre alertas recomenda **taxa de erro** — 5xx sobre total de requisições. Para esta
API, taxa é a métrica errada, e o motivo é aritmético.

O serviço tem `min_instance_count = 0` e tráfego próximo de zero. Numa janela de cinco minutos com
**duas** requisições, uma delas com erro, a taxa é 50%. Com uma requisição só, é 100%. E com zero
requisições o denominador é zero e a razão não existe. Numa API sem tráfego, taxa de erro é ruído
com casas decimais.

**"Três respostas 5xx em cinco minutos"** é uma frase que significa algo, é fácil de raciocinar e
é fácil de provar disparando.

A métrica é `run.googleapis.com/request_count`, filtrada pelo label `response_code_class = "5xx"`.
Filtrar por classe evita enumerar códigos e pega 500, 502, 503 e 504 de uma vez — incluindo os 5xx
que o **próprio Cloud Run** devolve quando o container não sobe. Esse caso é importante: é o
deploy quebrado, e ele não passa pela aplicação, então nenhum log da aplicação existiria para
contá-lo.

Os parâmetros que não são estética:

| Campo | Valor | Por quê |
| --- | --- | --- |
| `per_series_aligner` | `ALIGN_SUM` | `request_count` é DELTA. Com `ALIGN_RATE` o valor viraria requisições por segundo, e o threshold um número que ninguém confere de cabeça |
| `alignment_period` | `300s` | Com `ALIGN_SUM`, o valor alinhado passa a ser a contagem na janela |
| `cross_series_reducer` | `REDUCE_SUM` por `service_name` | Cada revisão é uma série. Sem reduzir, um deploy quebrado com dois erros na revisão nova e um na antiga não passa de nenhum limiar |
| `threshold_value` / `comparison` | `2` / `COMPARISON_GT` | "mais que dois" — ou seja, três ou mais |
| `duration` / `trigger.count` | `60s` / `1` | A janela de cinco minutos já é o amortecimento, e `0s` seria o ideal — mas a API recusa `0s` junto com `evaluation_missing_data` (ver armadilhas). `60s` é o menor valor que não atrasa nada na prática |
| `evaluation_missing_data` | `EVALUATION_MISSING_DATA_INACTIVE` | Sem dados significa sem erros — ver armadilhas |
| `auto_close` | `1800s` | O incidente fecha sozinho meia hora depois de o erro parar |
| `notification_rate_limit.period` | `3600s` | No máximo um e-mail por hora pelo mesmo incidente. Um alerta que manda quarenta e-mails vira regra de filtro no Gmail, e aí é como se não existisse |

### Por que e-mail, e não Slack

O `google_monitoring_notification_channel` suporta Slack, mas o canal exige uma autorização OAuth
feita pela console do GCP — o token não é declarável por Terraform. Seria um passo manual num
projeto cuja tese é "sem passo manual". E-mail funciona, não exige verificação, é 100% IaC e chega
no celular. Slack fica como melhoria óbvia para quem tiver um workspace de verdade do outro lado.

O `alert_email` vai para `terraform.tfvars`, que é gitignored, com entrada correspondente no
`terraform.tfvars.example`. Não é segredo, mas é dado pessoal, e ele **vai** para o state — mais
uma razão para o bucket do state continuar sendo tratado como material sensível.

## O uptime check

Um `google_monitoring_uptime_check_config` bate em `/ready` a cada 15 minutos, de três regiões.
Resolve três coisas de uma vez:

1. **Detecta indisponibilidade sem depender de tráfego.** O alerta de 5xx só dispara se alguém
   fizer uma requisição. Numa API sem visitantes, "está fora do ar e ninguém tentou" é
   indistinguível de "está tudo bem" — o uptime check é quem faz a tentativa.
2. **Dá linha de base à métrica.** Com requisições regulares, `request_count` deixa de ser uma
   série cheia de buracos.
3. **Substitui o keep-alive do M4.** O `google_cloud_scheduler_job` fazia um `GET /ready` diário
   para o Autonomous Database não parar pelos 7 dias de inatividade. O uptime check faz o mesmo
   com muito mais folga — 96 requisições por dia contra uma — então o job saiu, e a API
   `cloudscheduler` com ele.

Ele aponta para `/ready`, e é isso que faz o item 3 valer: `/ready` executa `SELECT 1 FROM dual`,
ou seja, cada execução abre uma sessão no ADB e conta como uso. Um check contra `/health` provaria
só que o container está de pé.

Cada execução abrir uma sessão é também o que limita baixar o `period`: com `min=0` no pool e
`max_instance_count = 2`, os 900s atuais cabem folgados na conta de sessões do Always Free feita
no M4 — 60s exigiria refazer a conta.

**Três regiões — e não é escolha, é exigência da API.** `selected_regions` com menos de três é
recusado no apply. A regra existe pelo motivo certo: com uma região só, um problema de rede dela
é indistinguível de queda do serviço, e o primeiro falso-positivo custa mais credibilidade do que
o alerta inteiro vale. Estão em uso `USA_IOWA`, `USA_OREGON` e `USA_VIRGINIA`; o limiar da
política de falha é "mais de uma região falhando", então uma região isolada com problema não
gera e-mail.

O `period` aceita um conjunto pequeno de valores — 60s, 300s, 600s, 900s. Outros são recusados no
apply.

O que ele estraga, e é preciso decidir com os olhos abertos: o serviço **quase nunca escala a
zero**. Com `cpu_idle = true` não há custo de CPU ociosa, mas a história de "escala a zero" fica
menos verdadeira. É uma troca consciente — escala a zero é argumento de custo, monitoramento
sintético é argumento de confiabilidade, e neste projeto o custo não muda.

## Armadilhas

### Um alerta mal filtrado nunca dispara, e nada avisa

É **a** armadilha deste milestone. Um filtro que não casa com nenhuma série temporal não é erro de
sintaxe: é uma condição que avalia zero séries e permanece calada para sempre. O `apply` passa, a
política aparece na console com uma marca verde de "OK", e você acredita ter monitoramento.

Três formas de errar o filtro, todas comuns:

- **`resource.labels` no lugar de `resource.label`.** No filtro de *Logging* é `labels`, plural.
  No de *Monitoring* é `label`, singular. Os dois aparecem lado a lado em qualquer tutorial de GCP
  e a diferença é uma letra.
- **`response_code` no lugar de `response_code_class`.** O primeiro existe e vale `500`, `503`; o
  segundo vale `5xx`. Comparar `response_code = "5xx"` casa com nada.
- **`service_name` errado.** É `ticketops`, de `var.service_name`. Interpolar `var.repo_name`
  produz um filtro válido e vazio.

A defesa não é revisar o filtro com mais cuidado, é **provar o alerta disparando**. Um alerta não
testado é uma linha de Terraform, não é monitoramento.

### `level` não é `severity`

`level` é o nome que o `structlog`, o `loguru` e metade dos exemplos de Python usam. Emitir
`{"level": "ERROR"}` produz uma entrada de severidade `DEFAULT` com um campo `level` dentro dela.
Não há erro, não há aviso; `severity>=ERROR` simplesmente não a encontra — e é exatamente o filtro
que alguém vai usar no dia em que precisar.

O nível do Python já é uma severidade válida: `record.levelname` devolve `DEBUG`, `INFO`,
`WARNING`, `ERROR` e `CRITICAL`, todas reconhecidas. Não há tabela de conversão a escrever, e
escrever uma seria convidar divergência. O teste `test_formatter_emite_json_com_severity` afirma
`"level" not in entrada` justamente por isso.

### Os loggers do uvicorn não propagam

O `uvicorn` aplica um `dictConfig` próprio ao subir e marca `uvicorn`, `uvicorn.error` e
`uvicorn.access` com `propagate = False`. Um handler no root nunca vê esses registros. O resultado
de configurar só o root é o pior dos mundos: os logs da aplicação em JSON, os do servidor em texto
— e a metade em texto é justamente a que aparece quando o container não sobe.

Daí `configurar_logging()` iterar sobre `("", "uvicorn", "uvicorn.error", "uvicorn.access")`.

A ordem funciona a favor: o `uvicorn` configura o logging dentro do `Config.load()` e **depois**
importa a aplicação. Chamar `configurar_logging()` no topo do `app/main.py`, antes do
`FastAPI(...)`, faz o setup do projeto acontecer por último e ganhar. Chamar de dentro do
`lifespan` também funcionaria para a aplicação, mas deixaria as linhas de boot do `uvicorn` fora
do formato — e são justamente elas que aparecem quando o container não sobe.

### O stream decide a severity quando o JSON não decide

No Cloud Run, uma linha sem `severity` própria herda a severidade do stream em que saiu: stdout é
tratado como informativo, stderr como erro. E o `basicConfig` do Python escreve em **stderr** por
default, assim como o handler `default` do `uvicorn`.

O efeito é cômico e custa tempo: as duas linhas de boot do `uvicorn` (`Started server process`,
`Application startup complete`) apareceriam no Cloud Logging como erro. Não quebraria o alerta de
5xx, que é sobre HTTP e não sobre log — mas envenenaria qualquer filtro por severidade. O
`StreamHandler(sys.stdout)` explícito e o `severity` em toda linha resolvem os dois casos.

### Traceback sem JSON é vinte entradas sem contexto

Cada linha de um traceback em texto é uma linha em stderr, e o Cloud Logging cria uma entrada por
linha. Um traceback de banco fora do ar ficaria espalhado por vinte entradas sem contexto, e a
busca por `severity>=ERROR` devolveria uma linha dizendo apenas `File "/app/app/db.py", line 21`.

O formatter resolve escapando os `\n` dentro do `message`: a linha continua sendo uma linha, e o
Logs Explorer mostra o traceback inteiro ao expandir a entrada. O teste
`test_formatter_mantem_traceback_em_uma_entrada` verifica exatamente isso, afirmando que a saída
do `format()` não contém nenhuma quebra de linha real.

### `configurar_logging()` no import brigaria com o `caplog`

O `app/main.py` é importado pelos testes, então o setup roda dentro do pytest — e
`logger.handlers = [handler]` no root **remove** o handler que o `caplog` instala. Qualquer teste
que verifique log falharia, com uma mensagem que não menciona logging.

Por isso o `test/conftest.py` faz `os.environ.setdefault("LOG_FORMAT", "texto")` no nível do
módulo — e no nível do módulo, não numa fixture: o `test_sem_banco.py` importa `app.main` no topo
do arquivo, ou seja, na coleta, antes de qualquer fixture rodar.

Os testes de logging contornam a questão por outro caminho: montam um `LogRecord` na mão e chamam
`format()` direto, ou plugam um handler próprio num `StringIO`. Nenhum depende de configuração
global, então nenhum depende dessa variável.

### A métrica tem atraso de ingestão

`request_count` não aparece no Monitoring no instante da requisição. Somando ingestão da métrica,
período de alinhamento de 5 minutos e o ciclo de avaliação da política, o e-mail chega **entre 3 e
10 minutos** depois do erro.

Não é defeito a corrigir, é expectativa a calibrar. Quem provar o alerta e não esperar o
suficiente vai concluir que ele não funciona e mexer no filtro que estava correto.

### `evaluation_missing_data` no default é surpresa nas duas direções

Uma API que escala a zero e não recebe tráfego não produz a série de 5xx. Com o campo omitido, o
comportamento em "sem dados" fica com o default do serviço, que já mudou de interpretação entre
versões da API e da console.

Os dois resultados possíveis são ruins e difíceis de diagnosticar: um alerta que dispara toda
noite porque o tráfego parou, ou um incidente aberto que nunca fecha porque a série sumiu antes de
a condição voltar ao normal. `EVALUATION_MISSING_DATA_INACTIVE` diz o que se quer: sem dados
significa sem erros.

### O `terraform validate` não conhece as regras do Cloud Monitoring

Duas restrições da API passam pelo `validate` e pelo `fmt` sem uma palavra, e só aparecem no
`apply` — depois de o Terraform já ter criado metade dos recursos:

```
Error: Field ... evaluation_missing_data had an invalid value of
"EVALUATION_MISSING_DATA_INACTIVE": Conditions setting evaluation_missing_data
must have a non-zero duration.

Error: Error creating UptimeCheckConfig: selected_regions must include at
least three locations
```

**`evaluation_missing_data` exige `duration` não-zero.** A combinação natural — janela de cinco
minutos fazendo o amortecimento e `duration = "0s"` para não atrasar o aviso — é recusada. Entre
abrir mão do `evaluation_missing_data` e aceitar uma duração, a segunda custa menos: `60s` é
irrelevante diante dos 3 a 10 minutos de ingestão, e o comportamento em "sem dados" continua
explícito.

**`selected_regions` exige no mínimo três.** Duas não bastam. A regra do Google existe pelo mesmo
motivo pelo qual não se usa uma só, levado um passo adiante.

A lição é a mesma das outras armadilhas deste doc, aplicada ao Terraform: `validate` prova que o
HCL está bem formado, não que a nuvem vai aceitar. Para recursos de Monitoring, o `plan` também
não prova nada — quem valida é o `apply`, e ele valida depois de já ter mexido no que veio antes
na ordem de dependência.

### Logar a mensagem do Oracle é logar o que o Oracle escolher

Nas constraints traduzidas isso é seguro e útil: `ORA-00001` traz o nome da constraint,
`ORA-12899` traz tamanhos, nenhum traz valor de coluna.

O caso que merece atenção é o `exc_info=True` do `init_pool`: a exceção do `python-oracledb` para
connect string inválida **ecoa a connect string**. Depois do M4, essa string é o descritor do
Autonomous Database, com host e service name. Não é senha, é topologia — e o traceback é o que
sustenta o requisito de "uma entrada, traceback inteiro". A troca é consciente.

A regra, simples: **nunca logar corpo de requisição, e-mail de cliente, senha, wallet password ou
DSN completo.** E, antes de considerar isto fechado, ler uma linha de log real de cada ponto de
log em produção. É a única forma de saber o que está lá.

### O volume não é problema de custo, é problema de leitura

O log de requisição do Cloud Run mais o uptime check a cada 15 minutos enchem o Logs Explorer de
linhas idênticas de `/ready` respondendo 200, e a linha interessante fica soterrada.

A solução é o filtro na busca, não a exclusão na ingestão. Um `google_logging_project_exclusion`
descartando os 200 funcionaria e criaria um problema novo: no dia em que você precisar provar
*quando* o serviço estava de pé, a evidência foi descartada. Neste volume, exclusão de log é
otimização de um problema que não existe.

## Como validar

Confirmar que o payload é estruturado — e não texto que parece JSON:

```bash
URL=$(cd terraform && terraform output -raw service_url)
curl -s "$URL/health" > /dev/null

gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="ticketops"' \
  --limit 3 --freshness=10m --format='value(jsonPayload)'
```

Se isso vier vazio e a mesma leitura com `--format='value(textPayload)'` trouxer linhas, o log
**não** está estruturado — o JSON está sendo tratado como texto, e a causa costuma ser mais de uma
linha por entrada.

Confirmar que a severidade chegou onde deveria:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND severity>=WARNING' \
  --limit 5 --freshness=1h --format='table(severity,jsonPayload.logger,jsonPayload.message)'
```

Confirmar a correlação por requisição:

```bash
PROJETO=ticketops-63450
TRACE=$(openssl rand -hex 16)
curl -s -H "X-Cloud-Trace-Context: $TRACE/1;o=1" "$URL/chamados" > /dev/null

gcloud logging read "trace=\"projects/$PROJETO/traces/$TRACE\"" --limit 10 --freshness=10m
```

Devolver as entradas daquela requisição e só as dela é a prova. Vazio com log funcionando aponta
para `GCP_PROJECT` ausente no container:

```bash
gcloud run services describe ticketops --region us-central1 \
  --format='value(spec.template.spec.containers[0].env)' | tr ',' '\n' | grep GCP_PROJECT
```

Confirmar que a política existe como se pretendia:

```bash
gcloud alpha monitoring policies list \
  --format='table(displayName,enabled,conditions[0].conditionThreshold.thresholdValue)'
```

E, localmente, sem nuvem nenhuma:

```powershell
ruff check .
pytest -q                  # 72 testes, quatro deles em test/test_logging.py
cd terraform
terraform fmt -check -recursive
terraform validate
```

No PowerShell, `curl.exe` e não `curl`: o apelido para `Invoke-WebRequest` ignora as flags e
descarta o corpo em resposta de erro.

## Runbook — chegou o e-mail de 5xx

O corpo do alerta traz estes quatro passos, que também estão no `documentation` da política:

1. **`severity>=ERROR` no Logs Explorer.** Se houver traceback, é bug da aplicação. O campo
   `logging.googleapis.com/labels.revision` diz qual revisão, e o `trace` permite reconstruir a
   requisição inteira.
2. **`GET /ready`.** Se devolver 503, a dependência é o Autonomous Database, não o código.
   Confirme pelo `jsonPayload.evento`: `pool_indisponivel` é o pool que não subiu,
   `acquire_falhou` é o pool de pé com o banco recusando a conexão.
3. **ADB parado por inatividade** é o caso mais provável — religar na console da OCI. O
   Autonomous Database do Always Free para sozinho após 7 dias sem uso.
4. **Deploy recente?** `gcloud run revisions list` e rollback por troca de tráfego, conforme
   [Pipeline CI/CD](../cicd/README.md).

Se nenhum dos quatro explicar, a próxima pergunta é se o alerta está certo — e a resposta vem de
comparar a contagem do alerta com o log de requisição do Cloud Run no mesmo intervalo.

### Provar o alerta

Um alerta que nunca disparou não é monitoramento. **Prove as duas metades separadamente**, porque
um e-mail que não chega pode ser as duas coisas, e descobrir qual é metade do trabalho:

- **O canal**, com o botão de notificação de teste na console (Monitoring → Alerting →
  Notification channels). Independe das políticas.
- **A condição**, forçando 5xx de verdade. A forma limpa é **parar o Autonomous Database na
  console da OCI** por alguns minutos: `/ready` e `/chamados` passam a 503, três requisições
  cruzam o limiar, o ADB volta e o incidente fecha sozinho pelo `auto_close`. É reversível, custa
  zero, e exercita exatamente o cenário para o qual o alerta existe — inclusive a armadilha dos 7
  dias. Prova as duas políticas de uma vez: a de 5xx pelas respostas, e a do uptime check pelas
  execuções que falharem enquanto o banco estiver parado.

```bash
for _ in 1 2 3; do curl -s -o /dev/null -w '%{http_code}\n' "$URL/ready"; done
```

Espere dez minutos antes de mudar qualquer coisa (ver o atraso de ingestão, acima), e confirme
também o `auto_close`: o incidente deve fechar sozinho meia hora depois de o erro parar.

O que **não** funciona bem é fabricar erro com uma revisão de teste: sem tráfego roteado ela não
recebe requisição, e com `--command` inválido a revisão não fica `Ready`, o que faz o próprio
deploy falhar antes de gerar 5xx contáveis.

## Custo

R$ 0, e este é o milestone em que isso é mais fácil — quase nada aqui é cobrado em qualquer volume
que este projeto produza.

| Item | Situação |
| --- | --- |
| Cloud Logging | 50 GiB de ingestão grátis por projeto/mês; `_Default` com 30 dias de retenção sem custo. Esta API não gera MB/mês |
| Métricas do Cloud Run | São métricas de sistema — não contam como métrica customizada e não são cobradas |
| Políticas de alerta e canais | Sem custo hoje. O Google já anunciou cobrança por condição de alerta no passado e recuou; confirme na página de preços antes de multiplicar políticas |
| Uptime checks | Sem custo na cota atual. Três regiões a cada 15 min dão ~8,7 mil requisições/mês contra ~2 milhões grátis |
| Notificação por e-mail | Grátis, e sem limite que este projeto alcance |
| Cloud Trace | **Não usado, de propósito** — com um serviço só, o trace mostra o que o log já mostra |
| Log-based metrics | **Não usadas, de propósito** — ver abaixo |

Uma métrica baseada em log contando entradas `ERROR` seria fácil e é tentadora. Foi recusada por
uma razão que não é de custo: ela cria uma **segunda** fonte de verdade sobre "quantos erros
houve", derivada do log em vez do HTTP, e as duas vão discordar — um 5xx do Cloud Run com o
container fora do ar não gera log da aplicação, e um `ERROR` logado num caminho tratado não gera
5xx. Dois alertas que discordam viram dois alertas que ninguém lê.

Os alertas de orçamento das duas nuvens continuam sendo a rede de segurança de custo, e agora
fazem par com o alerta de 5xx: um vigia a conta, o outro vigia o serviço.

## Fronteiras

**O que falta para fechar** — provar o alerta, e registrar aqui o que foi feito e quanto tempo
passou entre o erro e o e-mail. É o único item da definição de pronto ainda em aberto.

**`GET /dashboard`**, que está no escopo do projeto e não pertence a nenhum milestone: com log
estruturado no lugar, vale instrumentá-lo com `extra=` desde o primeiro commit — contagens por
status e tempo médio de resolução são exatamente o tipo de coisa que alguém vai querer ver por
requisição quando ela ficar lenta.

O que fica de fora, de propósito:

| | Por que não agora |
| --- | --- |
| Cloud Trace / OpenTelemetry | Com três tabelas e um único serviço, o trace mostra o que o log já mostra. Passa a valer no dia em que houver um segundo serviço |
| Dashboard como código (`google_monitoring_dashboard`) | JSON longo em Terraform para um serviço só. O Logs Explorer e a página do Cloud Run já respondem as perguntas do projeto |
| SLO e alerta por burn rate | Evolução natural do alerta de contagem, mas exige linha de base de tráfego real. Numa API sem visitantes, um SLO é um número inventado |
| Sink de logs para BigQuery | Faz sentido a partir de retenção maior que 30 dias ou análise histórica. Aqui seria custo e complexidade sem pergunta correspondente |
