"""
Aba 3 — Retenção Personalizada.

  - /retencao/lista: os 12 clientes mais propensos a churn (faixa Alto).
  - /retencao/email: chama a UC function get_cliente_360(id), que devolve o perfil E as ofertas
    já calculadas em SQL (CASE: a regra de negócio é governada no Unity Catalog). O texto do
    e-mail é redigido pelo modelo do Unity Gateway (CR_GATEWAY_MODEL); a IA só escreve.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import config, llm, warehouse
from ..warehouse import num

router = APIRouter()

CH = f"{config.CATALOG}.{config.SCHEMA_CHURN}"
PE = f"{config.CATALOG}.{config.SCHEMA_PESSOAL}"


def _user_token(request: Request):
    return config.token_for_request(request.headers.get(config.USER_TOKEN_HEADER))


@router.get("/retencao/lista")
async def lista(request: Request):
    rows = await warehouse.query(f"""
        SELECT s.id_cliente, c.nome_cliente, c.cidade, c.uf,
               floor(datediff(DATE '2026-09-23', c.data_cadastro)/365) anos,
               s.nome_plano, round(s.prob_churn,3) prob, s.fator_principal
        FROM {PE}.churn_scores s JOIN {CH}.dim_cliente c USING(id_cliente)
        WHERE s.faixa_risco='Alto'
        ORDER BY s.prob_churn DESC
        LIMIT 12
    """, _user_token(request))
    clientes = [
        {
            "id": r.get("id_cliente"),
            "nome": r.get("nome_cliente"),
            "cidade": r.get("cidade"),
            "uf": r.get("uf"),
            "anos": int(num(r.get("anos"))),
            "plano": r.get("nome_plano"),
            "prob": round(num(r.get("prob")) * 100),
            "fator": r.get("fator_principal"),
        }
        for r in rows
    ]
    return {"clientes": clientes}


class EmailReq(BaseModel):
    id_cliente: str


def _sanitiza_id(raw: str) -> str:
    """Só letras/dígitos maiúsculos — evita injeção na string literal da UC function."""
    return "".join(ch for ch in (raw or "").strip().upper() if ch.isalnum())[:16]


@router.post("/retencao/email")
async def email(req: EmailReq, request: Request):
    cid = _sanitiza_id(req.id_cliente)
    if not cid:
        return {"ok": False, "erro": "ID inválido."}
    token = _user_token(request)
    rows = await warehouse.query(f"SELECT * FROM {PE}.get_cliente_360('{cid}')", token)
    if not rows:
        return {"ok": False, "erro": "ID não encontrado na base de risco."}
    perfil = rows[0]
    texto = await llm.redigir_email_retencao(perfil, token)
    if not texto:
        return {"ok": False, "erro": "Não foi possível gerar o e-mail agora. Tente novamente."}
    return {
        "ok": True,
        "id_cliente": cid,
        "email": texto,
        "ofertas": {k: perfil.get(k) for k in ("desconto", "oferta_internet", "oferta_fator")},
    }
