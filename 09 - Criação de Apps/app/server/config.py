"""
Configuração central e autenticação da Central de Retenção.

AUTENTICAÇÃO ON-BEHALF-OF (OBO): dentro do Databricks App, TODAS as chamadas de dados e IA
rodam com a identidade do USUÁRIO LOGADO — não do service principal do app. O Databricks Apps
injeta o token OAuth do usuário no header `X-Forwarded-Access-Token` (habilitado pelos escopos
`user_api_scopes` no app.yaml: `sql` para o SQL Warehouse e `model-serving` para os serving
endpoints). As rotas leem esse header e passam o token para warehouse.py e llm.py.

Consequência (o ponto do OBO): o app NÃO precisa de nenhum GRANT no seu service principal. O
usuário já tem SELECT em `dbacademy.churn` (grupo do treino), é dono do seu schema pessoal e
das UC functions, e é dono do Supervisor/Genies — então tudo funciona sem conceder nada ao SP.

Localmente (fora do App) não há header: caímos para o token do profile do CLI (dev), via
`get_workspace_token()`.

Gotchas resolvidos aqui:
  1. Token OAuth local: `w.config.token` é None em auth U2M/OAuth. Use `w.config.authenticate()`.
  2. DATABRICKS_HOST dentro do App vem SEM esquema (só o hostname). Prefixe com https://.
"""
from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from typing import Optional

# -----------------------------------------------------------------------------
# Ambiente
# -----------------------------------------------------------------------------
IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))

DATABRICKS_PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE") or os.environ.get(
    "DATABRICKS_PROFILE", "mastertraining"
)

WORKSPACE_HOST_DEFAULT = "https://SEU_WORKSPACE_HOST"

# Header que o Databricks Apps injeta com o token OAuth do usuário logado (OBO).
USER_TOKEN_HEADER = "x-forwarded-access-token"

# -----------------------------------------------------------------------------
# Recursos (parametrizáveis por env var; defaults = valores do workspace do treino).
# Sob OBO, o SQL Warehouse ainda é anexado como App resource (o SP precisa de CAN_USE no
# COMPUTE do warehouse), mas as consultas rodam com o token do usuário. Serving endpoints NÃO
# precisam de anexo/CAN_QUERY: o token do usuário (escopo model-serving) autoriza a invocação.
# -----------------------------------------------------------------------------
WAREHOUSE_ID = os.environ.get("CR_WAREHOUSE_ID", "d788121d0edfbb7a")

# Schemas do Unity Catalog. Dados compartilhados (read-only) em churn; dados pessoais + as duas
# UC functions em cbettanim.
CATALOG = os.environ.get("CR_CATALOG", "dbacademy")
SCHEMA_CHURN = os.environ.get("CR_SCHEMA_CHURN", "churn")
SCHEMA_PESSOAL = os.environ.get("CR_SCHEMA_PESSOAL", "cbettanim")

# Supervisor (Ex.07) — roteia entre os Genies de Faturamento e Suporte.
SUPERVISOR_ENDPOINT = os.environ.get("CR_SUPERVISOR_ENDPOINT", "mas-3d713414-endpoint")
# Foundation model p/ a "leitura da IA" dos gráficos (✨ Explicar).
EXPLAIN_MODEL = os.environ.get("CR_EXPLAIN_MODEL", "databricks-claude-sonnet-4-5")
# Model service do Unity Gateway (catalogo.schema.nome). Quando definido, as chamadas de chat
# do app (✨ Explicar e o e-mail de retenção) passam pelo Gateway em vez do serving endpoint.
GATEWAY_MODEL = os.environ.get("CR_GATEWAY_MODEL", "").strip()


@lru_cache(maxsize=1)
def _workspace_client():
    """WorkspaceClient autenticado. Import preguiçoso do SDK."""
    from databricks.sdk import WorkspaceClient

    if IS_DATABRICKS_APP:
        return WorkspaceClient()
    return WorkspaceClient(profile=DATABRICKS_PROFILE)


def get_workspace_host() -> str:
    """Host do workspace COM esquema https://."""
    if IS_DATABRICKS_APP:
        host = os.environ.get("DATABRICKS_HOST", "")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        return host or WORKSPACE_HOST_DEFAULT
    try:
        return _workspace_client().config.host or WORKSPACE_HOST_DEFAULT
    except Exception:
        return os.environ.get("CR_HOST", WORKSPACE_HOST_DEFAULT)


def get_workspace_token() -> Optional[str]:
    """Token de portador para as APIs REST (SQL Statements + serving endpoints).

    Gotcha: em auth OAuth/U2M o `config.token` é None. Recorre a `authenticate()`.
    """
    try:
        w = _workspace_client()
        if getattr(w.config, "token", None):
            return w.config.token
        headers = w.config.authenticate()
        if headers and "Authorization" in headers:
            return headers["Authorization"].replace("Bearer ", "")
    except Exception as exc:  # pragma: no cover
        print(f"[config] SDK token indisponível ({exc}); tentando CLI")
    if not IS_DATABRICKS_APP:
        try:
            out = subprocess.run(
                ["databricks", "auth", "token", "-p", DATABRICKS_PROFILE],
                capture_output=True, text=True, check=True,
            ).stdout
            return json.loads(out)["access_token"]
        except Exception as exc:
            print(f"[config] falha ao obter token via CLI: {exc}")
    return None


def token_for_request(header_token: Optional[str]) -> Optional[str]:
    """Token a usar nas chamadas (SQL + serving).

    No App: SEMPRE o token do USUÁRIO logado (X-Forwarded-Access-Token) — OBO. Se o header
    faltar em produção, retornamos None (não caímos para o SP, que não tem grants — isso só
    mascararia o erro). Local (fora do App): usa o token do profile do CLI (dev).
    """
    if header_token:
        return header_token
    if IS_DATABRICKS_APP:
        return None
    return get_workspace_token()


def summary() -> dict:
    """Diagnóstico legível do ambiente, exposto em /api/health."""
    return {
        "modo": "databricks_app" if IS_DATABRICKS_APP else "local",
        "auth": "on-behalf-of-user (X-Forwarded-Access-Token)",
        "profile": None if IS_DATABRICKS_APP else DATABRICKS_PROFILE,
        "host": get_workspace_host(),
        "warehouse_id": WAREHOUSE_ID,
        "catalog": CATALOG,
        "schema_churn": SCHEMA_CHURN,
        "schema_pessoal": SCHEMA_PESSOAL,
        "supervisor_endpoint": SUPERVISOR_ENDPOINT,
        "explain_model": EXPLAIN_MODEL,
    }
