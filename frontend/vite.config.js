import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En dev, /api est redirigé vers FastAPI ; en prod c'est nginx qui joue ce rôle.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
