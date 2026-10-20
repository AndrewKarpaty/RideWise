import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies the API and uploaded photos to uvicorn on :8000, so
// the browser only ever talks to one origin and there is no CORS in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/uploads": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
