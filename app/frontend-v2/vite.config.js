import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base './' → the same build works at /v2 (Enterprise) and /v3 (Premium); the edition is picked at runtime
// from the URL. In dev, /api is proxied to the local RecoverIQ backend.
export default defineConfig({
  base: './',
  plugins: [react()],
  server: { port: 5173, proxy: Object.fromEntries(['/api', '/uploads', '/assets', '/downloads', '/v2/classic'].map(p => [p, 'http://127.0.0.1:8000'])) },
  build: { outDir: 'dist', chunkSizeWarningLimit: 1200 },
});
