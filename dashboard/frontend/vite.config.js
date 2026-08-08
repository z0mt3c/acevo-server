import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

// Output goes straight into dashboard/static, which app.py serves: "/" returns
// index.html from there and "/static/*" the assets — hence base "/static/".
export default defineConfig({
  base: "/static/",
  plugins: [svelte(), tailwindcss()],
  build: {
    outDir: "../static",
    emptyOutDir: true,
  },
  server: {
    // `npm run dev` against a real dashboard: point at the container.
    proxy: {
      "/api": {
        target: process.env.ACEVO_DEV_TARGET || "https://acevo.rock.w0rk.de",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
