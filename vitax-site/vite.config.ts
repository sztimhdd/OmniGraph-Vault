import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import {defineConfig} from 'vite';

// The reader talks to the same-origin read API from `vitax.api`; in `vite dev`
// that API runs separately on localhost, so requests are proxied to it.
const apiTarget = process.env.VITAX_API_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {target: apiTarget, changeOrigin: false},
    },
  },
});
