import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const djangoOrigin = 'http://127.0.0.1:8000'

export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/static/app/' : '/dev-app/',
  plugins: [react()],
  build: {
    outDir: '../twodapp/static/app',
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        entryFileNames: 'app.js',
        chunkFileNames: 'app-[name].js',
        assetFileNames: (assetInfo) => {
          const name = assetInfo.name ?? ''
          if (name.endsWith('.css')) return 'app.css'
          if (name.endsWith('.woff2')) return 'assets/fonts/[name][extname]'
          return 'assets/[name][extname]'
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': djangoOrigin,
      '/static': djangoOrigin,
      '/media': djangoOrigin,
      '/app': djangoOrigin,
      '/login': djangoOrigin,
      '/logout': djangoOrigin,
      '/bet': djangoOrigin,
      '/records': djangoOrigin,
      '/ledger': djangoOrigin,
      '/limit': djangoOrigin,
      '/operator': djangoOrigin,
      '/chat': djangoOrigin,
      '/settings': djangoOrigin,
      '/robots.txt': djangoOrigin,
      '/sw.js': djangoOrigin
    }
  }
}))
