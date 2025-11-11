import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import process from 'process';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load .env from project root (parent directory)
  const rootDir = path.resolve(__dirname, '..');
  const env = loadEnv(mode, rootDir, '');
  return {
    preview: {
      port: 5173,
      strictPort: true,
    },
    base: '/smartchatbot/',
    server: {
      port: 5173,
      allowedHosts: ['new.lib.miamioh.edu'],
      host: true,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
        '/health': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/readiness': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/metrics': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/ask': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/socket.io': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          ws: true,
        },
        '/smartchatbot/socket.io': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          ws: true,
        },
      },
    },
    define: {
      'process.env.SOME_KEY': JSON.stringify(env.SOME_KEY)
    },
    plugins: [react()],
  }
})

