/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/dashboard/', // Served at /dashboard by Go
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:9867',
      '/health': 'http://localhost:9867',
      '/metrics': 'http://localhost:9867',
    },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-ui': ['recharts'],
          'vendor-react': ['react', 'react-dom', 'react-router-dom', 'zustand'],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
