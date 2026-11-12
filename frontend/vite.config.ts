import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// ビルド成果物は FastAPI が配信する app/static/dist に出力する
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "../app/static/dist",
    emptyOutDir: true,
  },
});
