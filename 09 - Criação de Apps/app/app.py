"""
Central de Retenção — entrypoint FastAPI (Master Training / churn).

Serve a API (/api/*) e o build do React (frontend/dist). Três abas: Cockpit (mapa + gráficos),
Assistente (Supervisor Ex.07) e Retenção Personalizada (lista de risco + e-mail via UC function).
Todo o dado vem do Unity Catalog via SQL Warehouse; a IA, de dois serving endpoints.

Local:  uv run uvicorn app:app --reload --port 8000
Remoto: definido em app.yaml (uvicorn na 8000).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server import config, llm, warehouse
from server.routes import assistente, cockpit, retencao

FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"

app = FastAPI(title="Central de Retenção")

app.include_router(cockpit.router, prefix="/api")
app.include_router(assistente.router, prefix="/api")
app.include_router(retencao.router, prefix="/api")


@app.get("/api/health")
async def health(request: Request):
    """Saúde + diagnóstico OBO: confirma que o header do usuário chegou e mostra COMO QUEM as
    consultas rodam (current_user()) — deve ser o usuário logado, não o service principal."""
    hdr = request.headers.get(config.USER_TOKEN_HEADER)
    token = config.token_for_request(hdr)
    obo = {"user_header_present": bool(hdr)}
    try:
        rows = await warehouse.query("SELECT current_user() AS u", token)
        obo["user_query_ok"] = bool(rows)
        obo["consulta_roda_como"] = rows[0].get("u") if rows else None
    except Exception as exc:  # pragma: no cover
        obo["user_query_ok"] = False
        obo["erro"] = str(exc)[:200]
    return {
        "app": "central-retencao",
        "ambiente": config.summary(),
        "obo": obo,
        "ia": await llm.ping(),
    }


# -----------------------------------------------------------------------------
# Frontend (SPA). Em dev o Vite serve na 5173 com proxy /api -> 8000.
# -----------------------------------------------------------------------------
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"erro": "rota não encontrada"}, status_code=404)
        arquivo = FRONTEND_DIST / full_path
        if full_path and arquivo.is_file():
            return FileResponse(arquivo)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    async def sem_build():
        return JSONResponse(
            {"aviso": "frontend/dist não construído. Rode `npm run build` em frontend/.",
             "health": "/api/health"}
        )
