import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // The app calls /api/... on its own origin. In production a Vercel rewrite
    // (vercel.json) forwards that to the backend; in dev this proxy does the
    // same job, so both environments are same-origin and neither needs a
    // build-time backend URL or a CORS allowlist entry.
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
