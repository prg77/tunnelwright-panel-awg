import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В dev-режиме API и данные дашборда идут в локально запущенный panel-api (порт 8700)
const panelApi = { target: "http://127.0.0.1:8700", changeOrigin: true };

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": panelApi,
      "^/(stats|config|limits|meta|client-usage|traffic-history)\\.json$": panelApi,
      "^/(save-limits|save-meta|save-traffic-history|reset-client-usage|client-usage|save-tg-config|save-portal-name|send-tg|send-tg-doc|send-tg-photo)$": panelApi,
    },
  },
  build: { outDir: "dist" },
});
