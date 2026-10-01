import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: Vite na 5173 com proxy de /api para o FastAPI na 8000.
// Build: sai em dist/ (servido pelo FastAPI em produção).
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
});
