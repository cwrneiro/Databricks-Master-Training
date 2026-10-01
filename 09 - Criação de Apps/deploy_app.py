# Databricks notebook source
# MAGIC %md
# MAGIC # Exercício 9 — Central de Retenção (Databricks App)
# MAGIC
# MAGIC Este notebook **implanta o seu app** *Central de Retenção* — o painel que amarra todo o
# MAGIC treinamento: o **Cockpit** de churn (mapa + gráficos com leitura por IA), o **Assistente**
# MAGIC (o Supervisor do Ex. 7) e a **Retenção Personalizada** (a função `get_cliente_360` do Ex. 8).
# MAGIC
# MAGIC A IA do app (a leitura dos gráficos e o e-mail de retenção) passa por um **model service do
# MAGIC Unity Gateway** que este notebook cria no **seu** schema: um modelo governado pelo Unity
# MAGIC Catalog, com limite de uso e registro de cada chamada.
# MAGIC
# MAGIC Você **não escreve código** e **não concede nenhuma permissão manual**: preencha os campos no
# MAGIC topo e clique em **Run all**.
# MAGIC
# MAGIC **Como o app acessa os dados (on-behalf-of):** o app roda cada consulta e cada chamada de
# MAGIC IA **com a identidade do usuário logado** (autenticação *on-behalf-of-user*, via o header
# MAGIC `X-Forwarded-Access-Token`). Como VOCÊ já tem acesso — `SELECT` em `dbacademy.churn` (pelo
# MAGIC grupo do treino), é dono do seu schema e das suas funções, e é dono do seu Supervisor/Genies
# MAGIC — **nada precisa ser concedido** ao *service principal* do app. Esse é o pulo do gato deste
# MAGIC deploy: zero concessões, funciona para qualquer aluno.
# MAGIC
# MAGIC **Pré-requisitos** (no seu schema `dbacademy.<seu_schema>`):
# MAGIC - **Ex. 7** — seu **Supervisor** publicado (endpoint `mas-...-endpoint`).
# MAGIC - **Ex. 6** — a tabela `churn_scores`.
# MAGIC - **Ex. 8** — a função `get_cliente_360` (com as ofertas calculadas em SQL).
# MAGIC
# MAGIC > Rode no cluster `dbacademy_workshop_cluster`. O app roda em compute próprio do Databricks Apps.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Passo 1 — Preencha os campos e rode tudo
# MAGIC 1. **Rode só a célula abaixo** (Shift+Enter) para os campos aparecerem no topo do notebook.
# MAGIC 2. Preencha **Seu schema** (ex.: `cbettanim`) e **Endpoint do Supervisor (Ex.07)**
# MAGIC    (o endpoint do seu Supervisor do Ex. 7, ex.: `mas-3d713414-endpoint`).
# MAGIC 3. O campo **Model service** já vem com `retencao-gateway`: é o nome do modelo que o
# MAGIC    notebook vai criar no Unity Gateway, dentro do seu schema. Pode deixar como está.
# MAGIC 4. Só então clique em **Run all**.

# COMMAND ----------

# Cria os campos no topo do notebook. Rode ESTA célula primeiro, preencha os campos e depois Run all.
# O warehouse vira um dropdown com os warehouses reais do workspace, já com o do Setup selecionado.
from databricks.sdk import WorkspaceClient as _WC
_wh_names = [x.name for x in _WC().warehouses.list()]
_WH_DEFAULT = "dbacademy_workshop_wh"
_wh_choices = _wh_names or [""]
_wh_sel = _WH_DEFAULT if _WH_DEFAULT in _wh_names else (_wh_names[0] if _wh_names else "")

dbutils.widgets.text("schema", "", "Seu schema")
dbutils.widgets.text("supervisor_endpoint", "", "Endpoint do Supervisor (Ex.07)")
dbutils.widgets.dropdown("warehouse", _wh_sel, _wh_choices, "Warehouse")
dbutils.widgets.text("model_service", "retencao-gateway", "Model service")

# COMMAND ----------

SCHEMA = dbutils.widgets.get("schema").strip()
SUPERVISOR = dbutils.widgets.get("supervisor_endpoint").strip()
CATALOG = "dbacademy"
WAREHOUSE_W = dbutils.widgets.get("warehouse").strip()
MODEL_SERVICE_NAME = dbutils.widgets.get("model_service").strip() or "retencao-gateway"

assert SCHEMA, "Preencha o widget 'Seu schema' (ex.: cbettanim)."
assert SUPERVISOR, "Preencha o widget 'Endpoint do Supervisor (Ex.07)' (ex.: mas-...-endpoint do Ex. 7)."

import os, re, shutil, time
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Escopos OBO: `sql` (SQL Warehouse) + `model-serving` (serving endpoints: Supervisor) +
# `ai-gateway` (model service do Unity Gateway). Sem `ai-gateway`, o Gateway responde 403.
USER_API_SCOPES = ["sql", "model-serving", "ai-gateway"]
EXPLAIN_MODEL = "databricks-claude-sonnet-4-5"   # leitura por IA dos gráficos (Cockpit)
WAREHOUSE_NAME = "dbacademy_workshop_wh"          # criado no Setup (Ex. 00)
GATEWAY_DEST_MODEL = "models/system.ai.gpt-oss-20b"  # modelo por trás do model service

# Nome do app: prefixo + database normalizado, LIMITADO a 30 caracteres
# (Databricks Apps exige nome entre 2 e 30 chars). Trunca e remove hífen sobrando no fim.
APP_NAME = ("central-retencao-" + re.sub(r"[^a-z0-9-]", "-", SCHEMA.lower()).strip("-"))[:30].rstrip("-")
ME = w.current_user.me().user_name

print("Aluno            :", ME)
print("App              :", APP_NAME, f"({len(APP_NAME)} chars)")
print("Catálogo/schema  :", f"{CATALOG}.{SCHEMA}  (+ {CATALOG}.churn compartilhado)")
GATEWAY_MODEL = f"{CATALOG}.{SCHEMA}.{MODEL_SERVICE_NAME}"
print("Supervisor       :", SUPERVISOR)
print("Model service    :", GATEWAY_MODEL, "(Unity Gateway)")
print("Auth             : on-behalf-of-user (roda como VOCÊ; sem grants ao service principal)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Passo 2 — Resolver o SQL Warehouse
# MAGIC O app lê os dados via warehouse (com o SEU token). Resolvemos por **nome** (o ID não é
# MAGIC portável): widget → `dbacademy_workshop_wh` → primeiro warehouse disponível.

# COMMAND ----------

def resolver_warehouse():
    whs = list(w.warehouses.list())
    if not whs:
        raise RuntimeError("Nenhum SQL Warehouse encontrado no workspace. Rode o Setup (Ex. 00).")
    if WAREHOUSE_W:
        m = next((x for x in whs if x.id == WAREHOUSE_W or x.name == WAREHOUSE_W), None)
        if m:
            return m.id, m.name, "widget"
        print(f"  aviso: warehouse '{WAREHOUSE_W}' do widget não encontrado; caindo para a cascata.")
    m = next((x for x in whs if x.name == WAREHOUSE_NAME), None)
    if m:
        return m.id, m.name, f"nome '{WAREHOUSE_NAME}'"
    m = next((x for x in whs if str(getattr(x, "state", "")).upper().endswith("RUNNING")), whs[0])
    return m.id, m.name, "fallback (primeiro disponível)"

WH_ID, WH_NAME, WH_VIA = resolver_warehouse()
print(f"Warehouse: '{WH_NAME}' (id {WH_ID}) — resolvido por {WH_VIA}.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Passo 3 — Criar o seu model service no Unity Gateway
# MAGIC Um **model service** é um modelo de IA governado pelo Unity Catalog: ele fica no **seu**
# MAGIC schema (você é o dono), tem **limite de uso** (60 chamadas por minuto) e uma **tabela de
# MAGIC inferência** que registra cada chamada (pergunta e resposta). O app vai usá-lo para ler os
# MAGIC gráficos e para escrever o e-mail de retenção. Se ele já existir, só reaproveitamos.

# COMMAND ----------

def api(method, path, body=None):
    return w.api_client.do(method, path, body=body)

_ms_path = f"/api/2.1/unity-catalog/model-services/{GATEWAY_MODEL}"
try:
    api("GET", _ms_path)
    print(f"Model service '{GATEWAY_MODEL}' já existe — reaproveitando.")
except Exception:
    api("POST", f"/api/2.1/unity-catalog/model-services?model_service_id={MODEL_SERVICE_NAME}"
                f"&parent=schemas/{CATALOG}.{SCHEMA}", body={
        "comment": "Master Training — modelo da Central de Retenção (Unity Gateway)",
        "config": {
            "routing": {"destinations": [{
                "destination_type": "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
                "name": "primary", "traffic_percentage": 100,
                "pay_per_token_config": {"model": GATEWAY_DEST_MODEL}}]},
            "rate_limits": [{"key": "RATE_LIMIT_KEY_SERVICE",
                             "renewal_period": "RATE_LIMIT_RENEWAL_PERIOD_MINUTE", "requests": 60}],
            "inference_table": {"parent": f"schemas/{CATALOG}.{SCHEMA}",
                                "table_name_prefix": MODEL_SERVICE_NAME.replace("-", "_")},
        },
    })
    print(f"Model service '{GATEWAY_MODEL}' criado.")
_ms = api("GET", _ms_path)
_dest = (_ms.get("config") or {}).get("routing", {}).get("destinations", [{}])[0]
print("  destino        :", (_dest.get("pay_per_token_config") or {}).get("model"))
print("  inference table:", ((_ms.get("config") or {}).get("inference_table") or {}).get("table"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Passo 4 — Preparar o código-fonte do app (com a SUA configuração)
# MAGIC Este notebook é **autocontido**: ele **baixa o código do app** do repositório público no
# MAGIC GitHub (a pasta `09 - Criação de Apps/app/`), copia para uma pasta sua no workspace e grava
# MAGIC os seus valores no `app.yaml`. O app é **inteiramente dirigido por config**
# MAGIC (`server/config.py` lê as variáveis `CR_*`) — nada é escrito no código.

# COMMAND ----------

import urllib.request, zipfile, tempfile, glob

# Baixa o repositório do GitHub (a compute do Databricks alcança github.com) e usa o app/ de lá.
ZIP_URL = "https://github.com/CaduBettanim/Databricks-Master-Training/archive/refs/heads/main.zip"
_tmp = tempfile.mkdtemp()
_zip = os.path.join(_tmp, "repo.zip")
urllib.request.urlretrieve(ZIP_URL, _zip)
with zipfile.ZipFile(_zip) as _zf:
    _zf.extractall(_tmp)
_matches = glob.glob(os.path.join(_tmp, "*", "09 - Criação de Apps", "app"))
assert _matches, (
    "Não consegui baixar o app/ do GitHub. Confirme que a compute alcança github.com "
    "(ou adicione o repositório como Git folder e use a pasta app/ local)."
)
SRC_APP = _matches[0]
print("app baixado do GitHub:", SRC_APP)

STAGE = f"/Workspace/Users/{ME}/.central-retencao/{APP_NAME}"
if os.path.exists(STAGE):
    shutil.rmtree(STAGE)
shutil.copytree(SRC_APP, STAGE)

# app.yaml com a config do aluno. Obs.: os escopos OBO NÃO vão no app.yaml (chave ignorada e
# pode falhar o build); são configurados no APP (campo user_api_scopes) no Passo 6.
APP_YAML = f"""command:
  - "uvicorn"
  - "app:app"
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "8000"

env:
  - name: CR_WAREHOUSE_ID
    value: "{WH_ID}"
  - name: CR_SUPERVISOR_ENDPOINT
    value: "{SUPERVISOR}"
  - name: CR_EXPLAIN_MODEL
    value: "{EXPLAIN_MODEL}"
  - name: CR_GATEWAY_MODEL
    value: "{GATEWAY_MODEL}"
  - name: CR_CATALOG
    value: "{CATALOG}"
  - name: CR_SCHEMA_CHURN
    value: "churn"
  - name: CR_SCHEMA_PESSOAL
    value: "{SCHEMA}"
"""
with open(os.path.join(STAGE, "app.yaml"), "w") as f:
    f.write(APP_YAML)

print("Código preparado em:", STAGE)
print(APP_YAML)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Passo 5 — Criar o app (compute próprio + service principal)
# MAGIC Se já existir (re-execução), seguimos em frente. Esperamos o compute ficar **ACTIVE**.

# COMMAND ----------

try:
    api("GET", f"/api/2.0/apps/{APP_NAME}")
    print(f"App '{APP_NAME}' já existe — reaproveitando.")
except Exception:
    api("POST", "/api/2.0/apps", body={
        "name": APP_NAME,
        "description": "Central de Retenção — Master Training (churn): Cockpit + Assistente + Retenção.",
    })
    print(f"App '{APP_NAME}' criado.")

for _ in range(60):
    app = api("GET", f"/api/2.0/apps/{APP_NAME}")
    if (app.get("compute_status") or {}).get("state") == "ACTIVE":
        break
    time.sleep(10)

SP = app.get("service_principal_client_id")
APP_URL = app.get("url")
print(f"compute: {(app.get('compute_status') or {}).get('state')}  |  SP: {SP}")
print("URL     :", APP_URL)
assert SP, "Service principal do app ainda não disponível; re-execute esta célula."

# COMMAND ----------

# MAGIC %md
# MAGIC ## Passo 6 — Configurar OBO (escopos) + o warehouse
# MAGIC O ÚNICO preparo necessário — e nenhum é uma concessão ao usuário/SP:
# MAGIC - **user_api_scopes** = `sql`, `model-serving`, `ai-gateway` → habilita o app a usar o token
# MAGIC   do usuário nas chamadas de SQL, do Supervisor e do seu model service do Unity Gateway;
# MAGIC - **recurso warehouse** (CAN_USE) → o app precisa declarar o warehouse que vai usar.
# MAGIC
# MAGIC **Não há** GRANT de UC, EXECUTE, CAN_QUERY em endpoints, nem CAN_RUN em Genies: tudo isso é
# MAGIC dispensado pelo OBO (as chamadas rodam como o usuário, que já tem acesso).

# COMMAND ----------

api("PATCH", f"/api/2.0/apps/{APP_NAME}", body={
    "name": APP_NAME,
    "user_api_scopes": USER_API_SCOPES,
    "resources": [
        {"name": "sql-warehouse", "description": "Warehouse p/ ler o Unity Catalog (como o usuário)",
         "sql_warehouse": {"id": WH_ID, "permission": "CAN_USE"}},
    ],
})
_app = api("GET", f"/api/2.0/apps/{APP_NAME}")
print("escopos OBO :", _app.get("effective_user_api_scopes"))
print("recursos    :", [r["name"] for r in _app.get("resources", [])])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Passo 7 — Publicar (deploy)

# COMMAND ----------

api("POST", f"/api/2.0/apps/{APP_NAME}/deployments",
    body={"source_code_path": STAGE, "mode": "SNAPSHOT"})
estado = None
for _ in range(60):
    app = api("GET", f"/api/2.0/apps/{APP_NAME}")
    ad = app.get("active_deployment") or {}
    estado = (ad.get("status") or {}).get("state")
    if estado in ("SUCCEEDED", "FAILED", "STOPPED"):
        break
    time.sleep(10)
print("deploy:", estado)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Pronto! 🎉

# COMMAND ----------

print("=" * 66)
print("  CENTRAL DE RETENÇÃO — publicada (autenticação on-behalf-of usuário)")
print("=" * 66)
print("  App URL :", APP_URL)
print("  Deploy  :", estado)
print("  Modelo  :", GATEWAY_MODEL, "(Unity Gateway)")
print("  Escopos :", USER_API_SCOPES, "(o app usa o SEU token nas chamadas)")
print("  Grants  : NENHUM concedido ao service principal — desnecessário sob OBO.")
print("  Manual  : nada além dos 2 campos deste notebook.")
print("=" * 66)
print("  Abra a URL acima e explore as 3 abas. Tudo roda com a SUA identidade:")
print("  o Cockpit lê os dados, o Assistente usa o seu Supervisor/Genies e a")
print("  Retenção chama as suas UC functions — sem precisar conceder nada.")
displayHTML(f'<h3>Central de Retenção</h3><a href="{APP_URL}" target="_blank">{APP_URL}</a>')
