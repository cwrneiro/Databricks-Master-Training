"""Aba 2 — Assistente. Encaminha a pergunta ao Supervisor (Ex.07) e devolve o texto."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import config, llm

router = APIRouter()


class PerguntaReq(BaseModel):
    pergunta: str


@router.post("/assistente/perguntar")
async def perguntar(req: PerguntaReq, request: Request):
    pergunta = (req.pergunta or "").strip()
    if not pergunta:
        return {"resposta": "Digite uma pergunta.", "ok": False}
    token = config.token_for_request(request.headers.get(config.USER_TOKEN_HEADER))
    resposta = await llm.supervisor_ask(pergunta, token)
    if not resposta:
        return {
            "resposta": "O Supervisor não respondeu agora (pode estar em cold start). Tente de novo.",
            "ok": False,
        }
    return {"resposta": resposta, "ok": True}
