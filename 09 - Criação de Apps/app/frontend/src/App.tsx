// Central de Retenção — shell com 3 abas: Cockpit, Assistente, Retenção Personalizada.
import { useState } from "react";
import { Cockpit } from "./modos/Cockpit";
import { Assistente } from "./modos/Assistente";
import { Retencao } from "./modos/Retencao";

type Aba = "cockpit" | "assistente" | "retencao";

const ABAS: { id: Aba; rotulo: string }[] = [
  { id: "cockpit", rotulo: "📊 Cockpit" },
  { id: "assistente", rotulo: "💬 Assistente" },
  { id: "retencao", rotulo: "🎯 Retenção Personalizada" },
];

export default function App() {
  const [aba, setAba] = useState<Aba>("cockpit");
  return (
    <div>
      <header className="app-header">
        <div className="logo">CR</div>
        <h1>Central de Retenção</h1>
        <span className="sub">Master Training · Análise de Churn</span>
      </header>

      <div className="tabs">
        {ABAS.map((a) => (
          <button key={a.id} className={`tab ${aba === a.id ? "active" : ""}`} onClick={() => setAba(a.id)}>
            {a.rotulo}
          </button>
        ))}
      </div>

      <main>
        {aba === "cockpit" && <Cockpit />}
        {aba === "assistente" && <Assistente />}
        {aba === "retencao" && <Retencao />}
      </main>
    </div>
  );
}
