// vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'  // 🆕

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')  //  mappe @ → dossier src
    }
  },
  server: {
    host: true,
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',  // l’URL de ton FastAPI
        changeOrigin: true
      }
    }
  }
})
