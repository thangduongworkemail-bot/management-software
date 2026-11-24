import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

const API = process.env.API_URL || 'http://localhost:8000'

// Biểu tượng PNG do `npm run icons` sinh từ public/icon.svg (iPhone không nhận biểu tượng SVG)
const icon = (src, sizes, purpose = 'any') => ({ src, sizes, type: 'image/png', purpose })
const phimTat = (name, url) => ({ name, short_name: name, url, icons: [icon('pwa-192x192.png', '192x192')] })

export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: false, // main.js tự đăng ký, và bỏ qua khi chạy trong app gốc Android/iOS
      includeAssets: ['icon.svg', 'hust-logo.png', 'apple-touch-icon.png', 'day-thong-bao.js'],
      manifest: {
        id: '/',
        name: 'Nội thất Khanh Vân — Bán hàng & Kho',
        short_name: 'Khanh Vân',
        description: 'Bán hàng tại quầy, kho đa xưởng, công nợ và hóa đơn điện tử',
        lang: 'vi',
        dir: 'ltr',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'any',
        background_color: '#FFFFFF',
        theme_color: '#C51A1B',
        categories: ['business', 'productivity', 'shopping'],
        icons: [
          icon('pwa-192x192.png', '192x192'),
          icon('pwa-512x512.png', '512x512'),
          icon('maskable-512x512.png', '512x512', 'maskable'),
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
        ],
        // Nhấn giữ biểu tượng app trên Android để vào thẳng chức năng
        shortcuts: [phimTat('Bán hàng', '/ban-hang'), phimTat('Đơn hàng', '/don-hang'), phimTat('Kho & Xưởng', '/kho')],
      },
      workbox: {
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/ws/, /^\/files\//, /^\/docs/],
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        importScripts: ['day-thong-bao.js'], // nhận và bấm vào thông báo đẩy
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
