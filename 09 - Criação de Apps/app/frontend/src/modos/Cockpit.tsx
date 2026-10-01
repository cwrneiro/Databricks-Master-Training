// Aba 1 — Cockpit. KPIs + mapa do Brasil + painel da região + 4 gráficos filtráveis por região.
// Cada gráfico tem um botão "✨ Explicar" que chama o foundation model com os dados atuais.
import { useEffect, useMemo, useState } from "react";
import { api, nf, pc, fmtReais } from "../api";
import type { CockpitDados, RegiaoDados } from "../api";
import { MapaBrasil } from "../components/MapaBrasil";

const PLANOS = ["Básico", "Padrão", "Premium", "Empresarial"];
const SEGS = ["Consumidor", "PME", "Corporativo"];
const MESES = ["set", "out", "nov", "dez", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago"];
const MESESF = ["set/24","out/24","nov/24","dez/24","jan/25","fev/25","mar/25","abr/25","mai/25","jun/25","jul/25","ago/25"];

const argmin = (a: number[]) => a.indexOf(Math.min(...a));

function Bars({ labels, vals }: { labels: string[]; vals: number[] }) {
  const max = 40; // escala fixa p/ comparar regiões
  const green = argmin(vals);
  return (
    <div>
      {labels.map((l, i) => {
        const w = Math.min(100, (vals[i] / max) * 100);
        return (
          <div className="hbar" key={l}>
            <div className="t"><span>{l}</span><b>{pc(vals[i])}</b></div>
            <div className="track">
              <div className={`fill ${i === green ? "g" : ""}`} style={{ width: `${w.toFixed(0)}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Donut({ faixa }: { faixa: RegiaoDados["faixa"] }) {
  const tot = faixa.Alto + faixa["Médio"] + faixa.Baixo || 1;
  const p1 = (faixa.Alto / tot) * 100;
  const p2 = ((faixa.Alto + faixa["Médio"]) / tot) * 100;
  const bg = `conic-gradient(var(--orange) 0 ${p1}%, var(--amber) ${p1}% ${p2}%, var(--green) ${p2}% 100%)`;
  return (
    <div className="donut-wrap">
      <div className="donut" style={{ background: bg }}>
        <div className="hole"><div><b>{nf(faixa.Alto)}</b><span>risco Alto</span></div></div>
      </div>
      <div className="legend">
        <div className="lg"><span className="sw" style={{ background: "var(--orange)" }} />🔴 Alto — {nf(faixa.Alto)} ({Math.round((faixa.Alto / tot) * 100)}%)</div>
        <div className="lg"><span className="sw" style={{ background: "var(--amber)" }} />🟡 Médio — {nf(faixa["Médio"])} ({Math.round((faixa["Médio"] / tot) * 100)}%)</div>
        <div className="lg"><span className="sw" style={{ background: "var(--green)" }} />🟢 Baixo — {nf(faixa.Baixo)} ({Math.round((faixa.Baixo / tot) * 100)}%)</div>
      </div>
    </div>
  );
}

function Line({ data }: { data: number[] }) {
  const W = 480, H = 160, padX = 26, padT = 16, padB = 26;
  const max = Math.max(...data, 1);
  const x = (i: number) => padX + (i * (W - 2 * padX)) / (data.length - 1);
  const y = (v: number) => padT + (1 - v / max) * (H - padT - padB);
  const pts = data.map((v, i) => [x(i), y(v)] as [number, number]);
  const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const area = line + ` L ${x(data.length - 1).toFixed(1)} ${H - padB} L ${x(0).toFixed(1)} ${H - padB} Z`;
  const peak = data.indexOf(max);
  return (
    <svg className="line-chart" viewBox="0 0 480 160" role="img">
      <defs>
        <linearGradient id="ar" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#FF3621" stopOpacity=".18" />
          <stop offset="1" stopColor="#FF3621" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#ar)" />
      <path d={line} fill="none" stroke="#FF3621" strokeWidth={2.2} strokeLinejoin="round" />
      {pts.map((p, i) => (
        <circle key={i} cx={p[0].toFixed(1)} cy={p[1].toFixed(1)} r={i === peak ? 4 : 2.5}
          fill={i === peak ? "#FF3621" : "#fff"} stroke="#FF3621" strokeWidth={2} />
      ))}
      <text x={x(peak).toFixed(1)} y={(y(max) - 9).toFixed(1)} fontSize={10} fontWeight={700} fill="#FF3621" textAnchor="middle">{max}</text>
      {MESES.map((l, i) => (
        <text key={l} x={x(i).toFixed(1)} y={H - 8} fontSize={9} fill="#9AA0AA" textAnchor="middle">{l}</text>
      ))}
    </svg>
  );
}

type ChartId = "plano" | "faixa" | "meses" | "seg";

function VizCard({
  tag, titulo, chart, regiao, dadosIA, children,
}: {
  tag: "retro" | "prev"; titulo: string; chart: ChartId; regiao: string; dadosIA: any; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [texto, setTexto] = useState("");

  // ao trocar de região, invalida a leitura; se aberto, recarrega.
  useEffect(() => {
    setTexto("");
    if (open) fetchTexto();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regiao]);

  async function fetchTexto() {
    setLoading(true);
    try {
      const r = await api.explicar(chart, regiao, dadosIA);
      setTexto(r.texto);
    } catch {
      setTexto("Não foi possível gerar a leitura da IA agora.");
    } finally {
      setLoading(false);
    }
  }

  function toggle() {
    const novo = !open;
    setOpen(novo);
    if (novo && !texto && !loading) fetchTexto();
  }

  return (
    <div className="viz">
      <div className="viz-hd">
        <div>
          <span className={`viz-tag ${tag}`}>{tag === "retro" ? "Retrospectiva" : "Previsão"}</span>
          <h3>{titulo}</h3>
        </div>
        <button className={`ai-btn ${open ? "on" : ""}`} onClick={toggle}>
          {open ? "✨ Ocultar" : "✨ Explicar"}
        </button>
      </div>
      {children}
      {open && (
        <div className="ai-exp">
          <div className="who">✨ Leitura da IA</div>
          <span>{loading ? <><span className="spin" /> &nbsp;gerando leitura…</> : texto}</span>
        </div>
      )}
    </div>
  );
}

export function Cockpit() {
  const [dados, setDados] = useState<CockpitDados | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [reg, setReg] = useState("Brasil");

  useEffect(() => {
    api.cockpitDados().then(setDados).catch((e) => setErro(String(e)));
  }, []);

  const d: RegiaoDados | null = useMemo(() => (dados ? dados.D[reg] : null), [dados, reg]);

  if (erro) return <div className="panel"><p className="muted">Erro ao carregar os dados: {erro}</p></div>;
  if (!dados || !d) return <div className="panel"><p className="muted"><span className="spin" /> &nbsp;Carregando panorama de churn…</p></div>;

  const kpi = dados.kpi;
  const taxa = d.clientes ? (d.risco / d.clientes) * 100 : 0;
  const nomeReg = reg === "Brasil" ? "Brasil — todas as regiões" : `Região ${reg}`;

  return (
    <div className="panel">
      <div className="cockpit-hd">
        <h2>Panorama de Churn</h2>
        <p>Selecione uma região no mapa para ver os números e filtrar os gráficos. Cada gráfico tem uma leitura por IA ✨.</p>
      </div>

      <div className="kpi-grid">
        <div className="kpi" style={{ ["--accent" as any]: "var(--orange)", ["--soft" as any]: "#FFF0ED" }}>
          <div className="ic">📉</div><div className="lbl">Churn histórico</div>
          <div className="val">{kpi.churn_pct}%</div>
          <div className="foot">{nf(2000)} assinaturas <span className="chip up">nacional</span></div>
        </div>
        <div className="kpi" style={{ ["--accent" as any]: "var(--orange)", ["--soft" as any]: "#FFF0ED" }}>
          <div className="ic">⚠️</div><div className="lbl">Em risco Alto</div>
          <div className="val">{nf(kpi.risco_alto)}</div>
          <div className="foot">prob. média 82%</div>
        </div>
        <div className="kpi" style={{ ["--accent" as any]: "var(--amber)", ["--soft" as any]: "#FFF6E6" }}>
          <div className="ic">💰</div><div className="lbl">MRR em risco</div>
          <div className="val">{fmtReais(kpi.mrr_risco)}</div>
          <div className="foot">receita mensal em jogo</div>
        </div>
        <div className="kpi" style={{ ["--accent" as any]: "var(--green)", ["--soft" as any]: "#E7F5EF" }}>
          <div className="ic">🎯</div><div className="lbl">Qualidade do modelo</div>
          <div className="val">AUC {kpi.auc}</div>
          <div className="foot">Previsão de Churn (Ex.06) <span className="chip ok">bom</span></div>
        </div>
      </div>

      <div className="map-row">
        <div className="map-card">
          <h3>Clientes por região</h3>
          <MapaBrasil D={dados.D} selecionada={reg} onSelect={setReg} />
          <div className="map-scale">
            <span>menos</span>
            <i style={{ background: "#FED2C9" }} /><i style={{ background: "#FCB4A6" }} />
            <i style={{ background: "#F98C79" }} /><i style={{ background: "#F2604A" }} />
            <i style={{ background: "#E8412B" }} />
            <span>+ em risco</span>
          </div>
        </div>
        <div className="region-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>Região selecionada</h3>
            <button className="reset" onClick={() => setReg("Brasil")}>🇧🇷 Brasil (todas)</button>
          </div>
          <div className="big">{nomeReg}</div>
          <div className="rstat">
            <div><div className="n">{nf(d.clientes)}</div><div className="k">clientes</div></div>
            <div><div className="n red">{nf(d.risco)}</div><div className="k">em risco Alto</div></div>
            <div><div className="n">{pc(taxa)}</div><div className="k">taxa de risco</div></div>
          </div>
          <p className="muted" style={{ fontSize: 12, margin: "12px 0 0" }}>
            {reg === "Brasil"
              ? "Os quatro gráficos abaixo mostram o Brasil inteiro. Clique numa região do mapa para filtrar."
              : `Os quatro gráficos abaixo estão filtrados para a região ${reg}.`}
          </p>
        </div>
      </div>

      <p className="filter-cap">
        Mostrando: <b>{reg === "Brasil" ? "Brasil — todas as regiões" : reg}</b>
        {reg !== "Brasil" && (
          <button className="reset" onClick={() => setReg("Brasil")}>✕ limpar filtro</button>
        )}
      </p>

      <div className="viz-grid">
        <VizCard tag="retro" titulo="Churn por plano" chart="plano" regiao={reg}
          dadosIA={{ planos: PLANOS, churn_pct: d.plano }}>
          <Bars labels={PLANOS} vals={d.plano} />
        </VizCard>

        <VizCard tag="prev" titulo="Clientes por faixa de risco" chart="faixa" regiao={reg}
          dadosIA={d.faixa}>
          <Donut faixa={d.faixa} />
        </VizCard>

        <VizCard tag="retro" titulo="Cancelamentos por mês" chart="meses" regiao={reg}
          dadosIA={{ meses: MESESF, cancelamentos: d.meses }}>
          <Line data={d.meses} />
        </VizCard>

        <VizCard tag="retro" titulo="Churn por segmento" chart="seg" regiao={reg}
          dadosIA={{ segmentos: SEGS, churn_pct: d.seg }}>
          <Bars labels={SEGS} vals={d.seg} />
        </VizCard>
      </div>
    </div>
  );
}
