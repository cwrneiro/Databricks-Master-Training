// Cliente HTTP fino. Em dev o Vite faz proxy de /api -> :8000; em produção o próprio
// FastAPI serve SPA + API, então caminhos relativos servem.

export type RegiaoDados = {
  clientes: number;
  risco: number;
  plano: number[];
  faixa: { Alto: number; "Médio": number; Baixo: number };
  seg: number[];
  meses: number[];
};
export type CockpitDados = {
  D: Record<string, RegiaoDados>;
  kpi: { churn_pct: number; risco_alto: number; mrr_risco: number; auc: string };
};
export type Cliente = {
  id: string; nome: string; cidade: string; uf: string;
  anos: number; plano: string; prob: number; fator: string;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status}: ${(await res.text()).slice(0, 200)}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<any>("/health"),
  cockpitDados: () => req<CockpitDados>("/cockpit/dados"),
  explicar: (chart: string, regiao: string, dados: any) =>
    req<{ texto: string }>("/cockpit/explicar", {
      method: "POST",
      body: JSON.stringify({ chart, regiao, dados }),
    }),
  perguntar: (pergunta: string) =>
    req<{ resposta: string; ok: boolean }>("/assistente/perguntar", {
      method: "POST",
      body: JSON.stringify({ pergunta }),
    }),
  retencaoLista: () => req<{ clientes: Cliente[] }>("/retencao/lista"),
  gerarEmail: (id_cliente: string) =>
    req<{ ok: boolean; email?: string; erro?: string; id_cliente?: string }>(
      "/retencao/email",
      { method: "POST", body: JSON.stringify({ id_cliente }) }
    ),
};

export const nf = (n: number) => n.toLocaleString("pt-BR");
export const pc = (n: number) => n.toFixed(1).replace(".", ",") + "%";
export const fmtReais = (n: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(n);
