// Aba 3 — Retenção Personalizada. Lista de risco (UC) + e-mail gerado pela UC function
// gerar_email_retencao(id). "Enviar para CRM" remove o cliente da lista (estado local do demo).
import { useEffect, useState } from "react";
import { api } from "../api";
import type { Cliente } from "../api";

export function Retencao() {
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [input, setInput] = useState("");
  const [gerando, setGerando] = useState(false);
  const [atual, setAtual] = useState<{ id: string; email: string; cliente?: Cliente } | null>(null);
  const [toast, setToast] = useState("");

  useEffect(() => {
    api.retencaoLista().then((r) => setClientes(r.clientes)).catch(() => setClientes([]));
  }, []);

  function mostraToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 3200);
  }

  async function gerar(idArg?: string) {
    const id = (idArg ?? input).trim().toUpperCase();
    if (!id) return;
    setGerando(true);
    setAtual(null);
    try {
      const r = await api.gerarEmail(id);
      if (!r.ok || !r.email) {
        mostraToast(r.erro || "ID não encontrado na lista de risco.");
      } else {
        const cliente = clientes.find((c) => c.id === r.id_cliente);
        setAtual({ id: r.id_cliente || id, email: r.email, cliente });
        setInput(r.id_cliente || id);
      }
    } catch {
      mostraToast("Falha ao gerar o e-mail. Tente novamente.");
    } finally {
      setGerando(false);
    }
  }

  function enviarCrm() {
    if (!atual) return;
    const nome = atual.cliente?.nome || atual.id;
    setClientes((cs) => cs.filter((c) => c.id !== atual.id));
    mostraToast(`E-mail de ${nome} enviado ao CRM ✓ — cliente saiu da lista de risco.`);
    setAtual(null);
    setInput("");
  }

  return (
    <div className="panel">
      <div className="search">
        <input
          value={input}
          placeholder="Cole o ID de um cliente da lista abaixo (ex.: C01575)"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && gerar()}
        />
        <button className="btn btn-primary" onClick={() => gerar()} disabled={gerando}>
          {gerando ? <><span className="spin" /> &nbsp;Gerando…</> : "🎯 Retenção Personalizada"}
        </button>
        <span className="muted" style={{ fontSize: 12 }}>Dica: você também pode clicar em uma linha da lista.</span>
      </div>

      {atual && (
        <div className="email">
          <div className="meta">
            <span><b>Para:</b> {atual.cliente?.nome || atual.id} &lt;{atual.id.toLowerCase()}@cliente.com&gt;</span>
            <span><b>Assunto:</b> Uma oferta especial para você continuar com a gente</span>
          </div>
          <pre>{atual.email}</pre>
          <div className="act">
            <button className="btn btn-crm" onClick={enviarCrm}>📤 Enviar para CRM</button>
            <span className="muted" style={{ fontSize: 12 }}>
              Ofertas de <code>get_cliente_360('{atual.id}')</code> · texto pelo Unity Gateway
            </span>
          </div>
        </div>
      )}

      <div style={{ marginTop: 18 }}>
        <h2>Clientes mais propensos a churn &nbsp;<span className="muted">({clientes.length})</span></h2>
        <table>
          <thead>
            <tr>
              <th>ID</th><th>Cliente</th><th>Cidade</th><th>Tempo</th>
              <th>Plano</th><th>Prob. churn</th><th>Motivo principal</th>
            </tr>
          </thead>
          <tbody>
            {clientes.map((c) => (
              <tr key={c.id} onClick={() => { setInput(c.id); gerar(c.id); }}>
                <td><b>{c.id}</b></td>
                <td>{c.nome}</td>
                <td>{c.cidade}/{c.uf}</td>
                <td>{c.anos} anos</td>
                <td>{c.plano}</td>
                <td><span className="pill">{c.prob}%</span></td>
                <td><span className="tag">{c.fator}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={`toast ${toast ? "show" : ""}`}>{toast}</div>
    </div>
  );
}
