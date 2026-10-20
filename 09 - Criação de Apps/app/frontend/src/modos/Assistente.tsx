// Aba 2 — Assistente. Chat que chama o Supervisor (Ex.07) via /api/assistente/perguntar.
import { useEffect, useRef, useState } from "react";
import { api } from "../api";

type Msg = { de: "u" | "a"; texto: string; who?: string };

export function Assistente() {
  const [msgs, setMsgs] = useState<Msg[]>([
    { de: "a", who: "Assistente", texto: "Posso ajudar com dúvidas sobre faturamento e suporte dos clientes. O que você quer saber?" },
  ]);
  const [input, setInput] = useState("");
  const [carregando, setCarregando] = useState(false);
  const fimRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, carregando]);

  async function enviar() {
    const v = input.trim();
    if (!v || carregando) return;
    setMsgs((m) => [...m, { de: "u", texto: v }]);
    setInput("");
    setCarregando(true);
    try {
      const r = await api.perguntar(v);
      setMsgs((m) => [...m, { de: "a", who: "Assistente · Supervisor", texto: r.resposta }]);
    } catch (e) {
      setMsgs((m) => [...m, { de: "a", who: "Assistente", texto: "Falha ao consultar o Supervisor. Tente novamente." }]);
    } finally {
      setCarregando(false);
    }
  }

  return (
    <div className="panel">
      <div className="chat" style={{ marginBottom: 12 }}>
        <div className="hd">
          <span className="dot" /> Conectado ao <b>&nbsp;Supervisor (Ex.07)</b> &nbsp;·&nbsp;
          endpoint <code>mas-3d713414-endpoint</code> &nbsp;·&nbsp; roteia entre os Genies de Faturamento e Suporte
        </div>
        <div className="msgs">
          {msgs.map((m, i) => (
            <div className={`msg ${m.de}`} key={i}>
              {m.who && <div className="who">{m.who}</div>}
              {m.texto}
            </div>
          ))}
          {carregando && (
            <div className="msg a">
              <div className="who">Assistente · roteando…</div>
              <span className="spin" /> &nbsp;consultando os Genies (Faturamento / Suporte)…
            </div>
          )}
          <div ref={fimRef} />
        </div>
        <div className="in">
          <input
            value={input}
            placeholder="Pergunte algo (ex.: NPS médio por canal, faturas em aberto)…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && enviar()}
            disabled={carregando}
          />
          <button className="btn btn-primary" onClick={enviar} disabled={carregando}>Enviar</button>
        </div>
      </div>
      <p className="muted" style={{ fontSize: 12 }}>
        Cada mensagem chama o endpoint do Supervisor criado no Ex.07
        (<code>/serving-endpoints/mas-3d713414-endpoint/invocations</code>).
      </p>
    </div>
  );
}
