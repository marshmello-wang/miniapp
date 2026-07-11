import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const BACKEND = "http://localhost:8790";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3790,
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
      "/sdk": { target: BACKEND, changeOrigin: true },
      "/ws": { target: BACKEND, ws: true, changeOrigin: true },
    },
  },
});
