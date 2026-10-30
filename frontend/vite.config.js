import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

const API = process.env.API_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg', 'hust-logo.png'],
      manifest: {
        name: 'Nội thất Khanh Vân — Bán hàng & Kho',
        short_name: 'Khanh Vân',
        description: 'Bán hàng tại quầy, kho đa xưởng, công nợ và hóa đơn điện tử',
        lang: 'vi',
        start_url: '/',
        display: 'standalone',
        background_color: '#FFFFFF',
        theme_color: '#C51A1B',
        icons: [
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'maskable' },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/ws/, /^\/files\//, /^\/docs/],
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.origin === 'https://fonts.googleapis.com' || url.origin === 'https://fonts.gstatic.com',
            handler: 'CacheFirst',
            options: { cacheName: 'phong-chu', expiration: { maxEntries: 20, maxAgeSeconds: 60 * 60 * 24 * 365 } },
          },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': API,
      '/files': API,
      '/ws': { target: API.replace('http', 'ws'), ws: true },
    },
  },
  test: { environment: 'node' },
})
