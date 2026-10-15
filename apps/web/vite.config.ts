import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

/**
 * @fontsource lists each subset as woff2 plus a legacy woff fallback. Every browser this app
 * supports reads woff2, so drop the woff sources and keep the bundled font files to half the size.
 */
function fontsourceWoff2Only(): Plugin {
  return {
    name: "fontsource-woff2-only",
    enforce: "pre",
    transform(code, id) {
      if (!id.includes("@fontsource") || !id.endsWith(".css")) return null;
      return { code: code.replace(/,\s*url\([^)]+\.woff\)\s*format\('woff'\)/g, ""), map: null };
    },
  };
}

export default defineConfig({
  plugins: [fontsourceWoff2Only(), react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
});
