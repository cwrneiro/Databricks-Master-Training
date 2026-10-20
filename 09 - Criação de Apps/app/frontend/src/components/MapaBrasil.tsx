// Mapa do Brasil (Leaflet + tiles escuros ArcGIS World_Dark_Gray_Base, igual à demo Cargill).
// Uma bolha por região: tamanho pelo nº de clientes, cor pela intensidade de risco, número =
// clientes em risco Alto. Tooltip "Região — X clientes · Y em risco". Clique seleciona a região.
import { useEffect, useRef } from "react";
import L from "leaflet";
import type { RegiaoDados } from "../api";
import { nf } from "../api";

const GEO: Record<string, [number, number]> = {
  Norte: [-4.5, -63],
  Nordeste: [-9, -40.5],
  "Centro-Oeste": [-15.5, -54.5],
  Sudeste: [-20, -45],
  Sul: [-27, -51.5],
};
// Sombra por região (mais escuro = mais em risco), calibrada no mock.
const SHADE: Record<string, string> = {
  Nordeste: "#E8412B",
  Sudeste: "#F2604A",
  Sul: "#F98C79",
  Norte: "#FCB4A6",
  "Centro-Oeste": "#FED2C9",
};

type Props = {
  D: Record<string, RegiaoDados>;
  selecionada: string;
  onSelect: (reg: string) => void;
};

export function MapaBrasil({ D, selecionada, onSelect }: Props) {
  const elRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<Record<string, L.Marker>>({});
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  function bolhaIcon(reg: string, sel: boolean) {
    const d = D[reg];
    const size = Math.round(30 + (d.clientes - 150) / 500 * 36);
    return L.divIcon({
      className: "",
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
      html: `<div class="bolha ${sel ? "bolha-sel" : ""}" style="width:${size}px;height:${size}px;background:${SHADE[reg]};position:relative"><span style="font-size:${size > 46 ? 13 : 11}px">${d.risco}</span></div>`,
    });
  }

  // init do mapa (uma vez)
  useEffect(() => {
    if (!elRef.current || mapRef.current) return;
    const lmap = L.map(elRef.current, {
      zoomControl: false,
      attributionControl: false,
      scrollWheelZoom: false,
    }).setView([-15, -54], 3);
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 16 }
    ).addTo(lmap);
    lmap.fitBounds([
      [6, -74],
      [-34, -35],
    ]);
    mapRef.current = lmap;
    return () => {
      lmap.remove();
      mapRef.current = null;
      markersRef.current = {};
    };
  }, []);

  // (re)cria bolhas quando os dados chegam
  useEffect(() => {
    const lmap = mapRef.current;
    if (!lmap || !D || !D["Norte"]) return;
    Object.values(markersRef.current).forEach((m) => m.remove());
    markersRef.current = {};
    Object.keys(GEO).forEach((reg) => {
      const m = L.marker(GEO[reg], { icon: bolhaIcon(reg, reg === selecionada) }).addTo(lmap);
      m.bindTooltip(
        `<b>${reg}</b><br>${nf(D[reg].clientes)} clientes · ${nf(D[reg].risco)} em risco`,
        { direction: "top", offset: [0, -6] }
      );
      m.on("click", () => onSelectRef.current(reg));
      markersRef.current[reg] = m;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [D]);

  // realça a região selecionada
  useEffect(() => {
    Object.keys(markersRef.current).forEach((reg) =>
      markersRef.current[reg].setIcon(bolhaIcon(reg, reg === selecionada))
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selecionada, D]);

  return <div id="brmap" ref={elRef} />;
}
