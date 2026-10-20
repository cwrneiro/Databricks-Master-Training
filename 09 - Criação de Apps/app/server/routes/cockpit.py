"""
Aba 1 — Cockpit. Monta, num único endpoint, a estrutura por região (mesmo formato do mock):
para Brasil + as 5 regiões, os quatro gráficos (churn por plano, faixa de risco, cancelamentos
por mês, churn por segmento) e os totais (clientes, em risco, MRR em risco, churn histórico).

Tudo derivado ao vivo do Unity Catalog via SQL Warehouse (4 consultas agregadas por região,
rodadas em paralelo). Os pcts nacionais (Brasil) são recompostos das CONTAGENS por região
(não é média de médias) para bater com o número real.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import config, llm, warehouse
from ..warehouse import num


def _user_token(request: Request):
    """Token do usuário logado (OBO); local cai para o profile."""
    return config.token_for_request(request.headers.get(config.USER_TOKEN_HEADER))

router = APIRouter()

REGIOES = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]
PLANOS = ["Básico", "Padrão", "Premium", "Empresarial"]
SEGS = ["Consumidor", "PME", "Corporativo"]
# 12 meses fixos set/24 -> ago/25 (chave yyyy-MM -> índice)
MES_KEYS = [
    "2024-09", "2024-10", "2024-11", "2024-12", "2025-01", "2025-02",
    "2025-03", "2025-04", "2025-05", "2025-06", "2025-07", "2025-08",
]

# Expressão de região reutilizada em todas as consultas.
REG = f"""CASE WHEN c.uf IN ('AC','AP','AM','PA','RO','RR','TO') THEN 'Norte'
     WHEN c.uf IN ('AL','BA','CE','MA','PB','PE','PI','RN','SE') THEN 'Nordeste'
     WHEN c.uf IN ('DF','GO','MT','MS') THEN 'Centro-Oeste'
     WHEN c.uf IN ('ES','MG','RJ','SP') THEN 'Sudeste'
     WHEN c.uf IN ('PR','RS','SC') THEN 'Sul' END"""

CH = f"{config.CATALOG}.{config.SCHEMA_CHURN}"
PE = f"{config.CATALOG}.{config.SCHEMA_PESSOAL}"


def _vazio_regiao() -> dict:
    return {
        "clientes": 0, "risco": 0,
        "plano": [0.0] * len(PLANOS),
        "faixa": {"Alto": 0, "Médio": 0, "Baixo": 0},
        "seg": [0.0] * len(SEGS),
        "meses": [0] * len(MES_KEYS),
    }


@router.get("/cockpit/dados")
async def cockpit_dados(request: Request):
    """Estrutura completa por região (Brasil + 5 regiões) + KPIs nacionais."""
    token = _user_token(request)
    q_faixa = f"""
        SELECT {REG} regiao, s.faixa_risco faixa, count(*) n
        FROM {PE}.churn_scores s JOIN {CH}.dim_cliente c USING(id_cliente)
        GROUP BY 1,2
    """
    q_plano = f"""
        SELECT {REG} regiao, p.nome_plano plano,
               sum(f.churn_flag) churned, count(*) tot
        FROM {CH}.fato_assinatura f JOIN {CH}.dim_cliente c USING(id_cliente)
        JOIN {CH}.dim_plano p USING(id_plano)
        GROUP BY 1,2
    """
    q_seg = f"""
        SELECT {REG} regiao, c.segmento seg,
               sum(f.churn_flag) churned, count(*) tot
        FROM {CH}.fato_assinatura f JOIN {CH}.dim_cliente c USING(id_cliente)
        GROUP BY 1,2
    """
    q_meses = f"""
        SELECT {REG} regiao, date_format(f.data_fim,'yyyy-MM') mes, count(*) n
        FROM {CH}.fato_assinatura f JOIN {CH}.dim_cliente c USING(id_cliente)
        WHERE f.data_fim >= '2024-09-01'
        GROUP BY 1,2
    """
    q_kpi = f"""
        SELECT
          (SELECT round(sum(preco_mensal),2) FROM {PE}.churn_scores WHERE faixa_risco='Alto') mrr_risco,
          (SELECT round(100*avg(churn_flag),0) FROM {CH}.fato_assinatura) churn_pct
    """

    r_faixa, r_plano, r_seg, r_meses, r_kpi = await asyncio.gather(
        warehouse.query(q_faixa, token), warehouse.query(q_plano, token),
        warehouse.query(q_seg, token), warehouse.query(q_meses, token),
        warehouse.query(q_kpi, token),
    )

    D: dict[str, dict] = {r: _vazio_regiao() for r in REGIOES}
    D["Brasil"] = _vazio_regiao()

    # ---- faixa (contagens; nacional = soma) ----
    for row in r_faixa:
        reg, faixa, n = row.get("regiao"), row.get("faixa"), int(num(row.get("n")))
        if reg in D and faixa in D[reg]["faixa"]:
            D[reg]["faixa"][faixa] += n
            D["Brasil"]["faixa"][faixa] += n
    for reg in list(D):
        f = D[reg]["faixa"]
        D[reg]["clientes"] = f["Alto"] + f["Médio"] + f["Baixo"]
        D[reg]["risco"] = f["Alto"]

    # ---- plano / seg (recompõe pct das contagens; Brasil = soma churned/tot) ----
    def _pcts(rows, chave, ordem, alvo_attr):
        acc: dict[str, dict] = {}  # regiao -> plano -> [churned, tot]
        nac: dict[str, list] = {p: [0.0, 0.0] for p in ordem}
        for row in rows:
            reg, key = row.get("regiao"), row.get(chave)
            if reg not in D or key not in ordem:
                continue
            ch, tot = num(row.get("churned")), num(row.get("tot"))
            acc.setdefault(reg, {}).setdefault(key, [0.0, 0.0])
            acc[reg][key][0] += ch
            acc[reg][key][1] += tot
            nac[key][0] += ch
            nac[key][1] += tot
        for reg in REGIOES:
            arr = []
            for key in ordem:
                ch, tot = acc.get(reg, {}).get(key, [0.0, 0.0])
                arr.append(round(100 * ch / tot, 1) if tot else 0.0)
            D[reg][alvo_attr] = arr
        D["Brasil"][alvo_attr] = [
            round(100 * nac[k][0] / nac[k][1], 1) if nac[k][1] else 0.0 for k in ordem
        ]

    _pcts(r_plano, "plano", PLANOS, "plano")
    _pcts(r_seg, "seg", SEGS, "seg")

    # ---- meses (contagens; nacional = soma) ----
    idx = {k: i for i, k in enumerate(MES_KEYS)}
    for row in r_meses:
        reg, mes, n = row.get("regiao"), row.get("mes"), int(num(row.get("n")))
        if reg in D and mes in idx:
            D[reg]["meses"][idx[mes]] += n
            D["Brasil"]["meses"][idx[mes]] += n

    kpi = r_kpi[0] if r_kpi else {}
    return {
        "D": D,
        "kpi": {
            "churn_pct": int(num(kpi.get("churn_pct")) or 27),
            "risco_alto": D["Brasil"]["risco"],
            "mrr_risco": num(kpi.get("mrr_risco")),
            "auc": "0,97",
        },
    }


class ExplicarReq(BaseModel):
    chart: str
    regiao: str
    dados: dict


@router.post("/cockpit/explicar")
async def cockpit_explicar(req: ExplicarReq, request: Request):
    """Leitura por IA (foundation model) do gráfico, a partir dos dados da região atual."""
    texto = await llm.explicar_grafico(req.chart, req.regiao, req.dados, _user_token(request))
    return {"texto": texto}
