import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [tailwindcss(), react()],
  server: {
    host: true,
    port: 8031,
    proxy: {
      '/run': 'http://localhost:8030',
      '/jobs': 'http://localhost:8030',
      '/files': 'http://localhost:8030',
    },
  },
});
