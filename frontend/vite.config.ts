import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build the React app directly into Flask's static dir so the existing
// Python (gunicorn) buildpack serves it with no extra buildpack required.
// During local dev, proxy API calls to the Flask server on :5001.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/analyze": "http://127.0.0.1:5001",
      "/scan": "http://127.0.0.1:5001",
      "/backtest": "http://127.0.0.1:5001",
    },
  },
});
