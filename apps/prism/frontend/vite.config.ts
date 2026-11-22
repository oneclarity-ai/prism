/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = process.env.PRISM_BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  base: "/dashboard/",
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: { outDir: process.env.PRISM_BUILD_OUT || fileURLToPath(new URL("../app/static", import.meta.url)), emptyOutDir: true, sourcemap: false, target: "es2022", chunkSizeWarningLimit: 800 },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: false },
      "/health": { target: backend, changeOrigin: false },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
