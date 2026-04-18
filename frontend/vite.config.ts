import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// GitHub Pages serves the site from /<repo-name>/ so we need a matching
// base path. Locally we serve from /. VITE_BASE_PATH is injected by the
// deploy-pages workflow; anywhere else it falls back to "/".
export default defineConfig(() => ({
  plugins: [react()],
  base: process.env.VITE_BASE_PATH ?? "/",
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
}));
