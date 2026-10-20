"""
Camada de IA do app. Dois consumidores, ambos serving endpoints do workspace, chamados com o
TOKEN DO USUÁRIO logado (OBO) — passado pelas rotas. Isso é o que faz o Supervisor rotear como
o usuário (que é dono dos Genies), sem precisar de CAN_QUERY/CAN_RUN no service principal.

  1. supervisor_ask(): o Supervisor do Ex.07 (mas-...-endpoint). Formato de "Responses API":
     body {"input":[{role,content}]}, e a resposta final é o ÚLTIMO item `message` do array
     `output` (os itens intermediários são tool_calls e ecos com <name>...</name> do roteamento).

  2. explicar_grafico(): um foundation model (databricks-claude-sonnet-4-5) no formato chat
     completions padrão (/serving-endpoints/<modelo>/invocations), para a "leitura da IA" de
     cada gráfico do cockpit. Resposta curta (1-2 frases PT-BR).

Degrade gracioso: qualquer falha devolve None / texto de fallback.
"""
from __future__ import annotations

import json
import os
import ssl
from functools import lru_cache
from typing import Optional

import aiohttp

from . import config


@lru_cache(maxsize=1)
def _ssl_context() -> Optional[ssl.SSLContext]:
    for caminho in (os.environ.get("SSL_CERT_FILE"), "/etc/ssl/cert.pem"):
        if caminho and os.path.exists(caminho):
            try:
                return ssl.create_default_context(cafile=caminho)
            except Exception:
                pass
    return None


def _connector():
    ctx = _ssl_context()
    return aiohttp.TCPConnector(ssl=ctx) if ctx else None


def _texto_do_content(content) -> str:
    """Extrai texto de um content que pode ser string ou lista de blocos."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        partes = []
        for bloco in content:
            if isinstance(bloco, dict):
                partes.append(bloco.get("text") or bloco.get("content") or "")
        return "".join(partes)
    return str(content or "")


# -----------------------------------------------------------------------------
# 1. Supervisor (Ex.07) — Responses API
# -----------------------------------------------------------------------------
async def supervisor_ask(pergunta: str, token: Optional[str]) -> Optional[str]:
    """Manda a pergunta ao Supervisor (como o usuário) e devolve o texto da resposta final."""
    if not token:
        return None
    host = config.get_workspace_host()
    url = f"{host}/serving-endpoints/{config.SUPERVISOR_ENDPOINT}/invocations"
    payload = {"input": [{"role": "user", "content": pergunta}]}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        timeout = aiohttp.ClientTimeout(total=240)
        async with aiohttp.ClientSession(timeout=timeout, connector=_connector()) as sess:
            async with sess.post(url, json=payload, headers=headers) as rr:
                txt = await rr.text()
                if rr.status != 200:
                    print(f"[supervisor] HTTP {rr.status}: {txt[:300]}")
                    return None
                data = json.loads(txt)
                return _extrair_resposta_final(data)
    except Exception as exc:
        print(f"[supervisor] indisponível: {exc}")
        return None


def _extrair_resposta_final(data: dict) -> Optional[str]:
    """A resposta final é o último item `message`/assistant cujo texto não é um eco <name>."""
    output = data.get("output") or []
    candidatos = []
    for item in output:
        if item.get("type") != "message":
            continue
        texto = _texto_do_content(item.get("content")).strip()
        if not texto or texto.startswith("<name>"):
            continue
        candidatos.append(texto)
    if candidatos:
        return candidatos[-1]
    # fallback: alguns formatos trazem texto direto
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    return None


# -----------------------------------------------------------------------------
# 2. Foundation model — chat completions (leitura dos gráficos)
# -----------------------------------------------------------------------------
async def _chat(system: str, user: str, token: Optional[str], max_tokens: int = 220,
                timeout_s: int = 45) -> Optional[str]:
    if not token:
        return None
    host = config.get_workspace_host()
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    if config.GATEWAY_MODEL:
        # Unity Gateway: API unificada (OpenAI-compatível); o model service vai no campo `model`.
        url = f"{host}/ai-gateway/mlflow/v1/chat/completions"
        payload["model"] = config.GATEWAY_MODEL
    else:
        url = f"{host}/serving-endpoints/{config.EXPLAIN_MODEL}/invocations"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with aiohttp.ClientSession(timeout=timeout, connector=_connector()) as sess:
            async with sess.post(url, json=payload, headers=headers) as rr:
                txt = await rr.text()
                if rr.status != 200:
                    print(f"[chat] HTTP {rr.status}: {txt[:300]}")
                    return None
                d = json.loads(txt)
                return _texto_do_content(d["choices"][0]["message"]["content"]).strip()
    except Exception as exc:
        print(f"[explain] indisponível: {exc}")
        return None


async def explicar_grafico(chart: str, regiao: str, dados: dict, token: Optional[str]) -> str:
    """Leitura em 1-2 frases PT-BR de um gráfico do cockpit, a partir dos dados atuais."""
    onde = "no Brasil (todas as regiões)" if regiao == "Brasil" else f"na região {regiao}"
    contexto = {
        "plano": "Churn (%) por plano de assinatura",
        "faixa": "Distribuição de clientes por faixa de risco de churn (Alto/Médio/Baixo)",
        "meses": "Cancelamentos de assinatura por mês (set/24 a ago/25)",
        "seg": "Churn (%) por segmento de cliente (Consumidor/PME/Corporativo)",
    }.get(chart, chart)
    system = (
        "Você é um analista de retenção (Customer Success) de uma empresa de telecom. "
        "Explique gráficos de churn para um gerente, em português do Brasil, de forma direta "
        "e acionável. Responda em NO MÁXIMO 2 frases curtas. Não use markdown nem listas. "
        "Cite os números mais relevantes e uma recomendação prática."
    )
    user = (
        f"Gráfico: {contexto}, {onde}.\n"
        f"Dados (JSON): {json.dumps(dados, ensure_ascii=False)}\n"
        "Escreva a leitura do gráfico."
    )
    # Folga de tokens: modelos de raciocínio (ex.: gpt-oss) gastam parte do limite pensando.
    resp = await _chat(system, user, token, max_tokens=600)
    return resp or "Não foi possível gerar a leitura da IA agora. Tente novamente."


async def redigir_email_retencao(perfil: dict, token: Optional[str]) -> Optional[str]:
    """Redige o e-mail de retenção. As OFERTAS já vêm calculadas pela UC function
    get_cliente_360 (regra de negócio em SQL); a IA só escreve o texto."""
    system = (
        "Você é um especialista em retenção de clientes de uma empresa de assinatura. "
        "Redija um e-mail profissional e empático em português do Brasil para convencer o "
        "cliente a permanecer. Ofereça EXATAMENTE as ofertas informadas, sem inventar outras "
        "e sem mudar valores. Não cite o setor da empresa. Comece pela saudação (não inclua "
        "linha de assunto) e escreva em texto simples, sem markdown: sem asteriscos, sem listas."
    )
    user = (
        f"Dados: Nome: {perfil.get('nome_cliente')}, Cidade: {perfil.get('cidade')}, "
        f"Anos de casa: {perfil.get('anos_de_casa')}. "
        f"Ofertas: (a) desconto de {perfil.get('desconto')} na mensalidade; "
        f"(b) {perfil.get('oferta_internet')}; (c) {perfil.get('oferta_fator')}. "
        "Cite o nome, a cidade e os anos de casa e mencione as três ofertas de forma natural."
    )
    return await _chat(system, user, token, max_tokens=1500, timeout_s=120)


async def ping() -> dict:
    return {
        "supervisor": config.SUPERVISOR_ENDPOINT,
        "explain_model": config.EXPLAIN_MODEL,
        "gateway_model": config.GATEWAY_MODEL or None,
    }
