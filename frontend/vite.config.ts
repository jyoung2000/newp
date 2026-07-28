import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The build is served by the FastAPI backend from backend/app/static.
// Dev proxies /api and /ws to the backend on port 1456.
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: '../backend/app/static',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:1456', changeOrigin: true },
      '/ws': { target: 'http://localhost:1456', ws: true, changeOrigin: true },
    },
  },
})
