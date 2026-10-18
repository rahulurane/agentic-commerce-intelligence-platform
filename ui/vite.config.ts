/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite + React config for the ACIP demo UI. The dev server runs on 5173 (local mode);
// the Docker image builds the static bundle and serves it from nginx (see ui/Dockerfile).
// Vitest runs in a jsdom environment with the testing-library matchers loaded via
// vitest.setup.ts.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    css: true,
  },
});
