"""
Leitura do Unity Catalog com a identidade do USUÁRIO logado (OBO).

Usa o `databricks-sql-connector` (caminho de dados do SQL Warehouse,
`/sql/1.0/warehouses/<id>`) — e NÃO a REST `/api/2.0/sql/statements`. Motivo: o token OAuth
do usuário repassado pelo Databricks Apps (X-Forwarded-Access-Token) é *down-scoped* para os
escopos do app (`sql`); esse token autoriza o conector SQL (padrão OBO documentado), mas a REST
de Statement Execution volta vazia com ele. O conector é síncrono; rodamos em thread para não
bloquear as rotas async. Degrade gracioso: erro/token ausente -> lista vazia.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from . import config


def _run_query(sql: str, token: str, host: str, warehouse_id: str) -> list[dict]:
    from databricks import sql as dbsql

    hostname = host.replace("https://", "").replace("http://", "").rstrip("/")
    http_path = f"/sql/1.0/warehouses/{warehouse_id}"
    conn = dbsql.connect(server_hostname=hostname, http_path=http_path, access_token=token)
    try:
        cur = conn.cursor()
        try:
            cur.execute(sql)
            cols = [c[0] for c in cur.description] if cur.description else []
            return [dict(zip(cols, list(row))) for row in cur.fetchall()]
        finally:
            cur.close()
    finally:
        conn.close()


async def query(sql: str, token: Optional[str]) -> list[dict]:
    """Roda um SELECT no warehouse COMO O USUÁRIO e devolve lista de dicts."""
    if not token:
        print("[warehouse] sem token de usuário; retornando vazio")
        return []
    try:
        return await asyncio.to_thread(
            _run_query, sql, token, config.get_workspace_host(), config.WAREHOUSE_ID
        )
    except Exception as exc:
        causa = exc.__cause__ or exc.__context__
        print(f"[warehouse] erro: {type(exc).__name__}: {exc} | causa: {type(causa).__name__ if causa else None}: {str(causa)[:300] if causa else ''}")
        return []


def num(v) -> float:
    """Converte valor para float com segurança (o conector pode devolver Decimal/int/str)."""
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
