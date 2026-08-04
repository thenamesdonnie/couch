import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// A build stamp, shown in the theme sheet, so we can confirm the phone is
// actually running the latest build (not a stale cached one).
const BUILD = new Date().toISOString().slice(0, 16).replace('T', ' ')

export default defineConfig({
  define: { __BUILD__: JSON.stringify(BUILD) },
  plugins: [svelte()],
  server: {
    proxy: {
      '/api': 'http://localhost:8790',
      '/ws': { target: 'ws://localhost:8790', ws: true },
    },
  },
})
