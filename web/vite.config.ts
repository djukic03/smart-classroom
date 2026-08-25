import { fileURLToPath, URL } from 'node:url'

import tailwind from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const proxyTarget = env.VITE_DEV_PROXY_TARGET || 'http://localhost:8000'

  return {
    plugins: [
      react(),
      tailwind(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['favicon.svg', 'icons/apple-touch-icon.png'],
        workbox: {
          globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
          // Measurements are live data: never serve them from the cache.
          navigateFallbackDenylist: [/^\/api/, /^\/health/],
          runtimeCaching: [
            {
              urlPattern: /^.*\/api\/v1\/classrooms(\?.*)?$/,
              handler: 'NetworkFirst',
              options: {
                cacheName: 'classrooms',
                networkTimeoutSeconds: 4,
                expiration: { maxEntries: 8, maxAgeSeconds: 60 * 60 * 24 },
              },
            },
          ],
        },
        manifest: {
          name: 'Pametna učionica',
          short_name: 'Učionica',
          description:
            'Praćenje mikroklimatskih uslova i popunjenosti učionice uživo.',
          lang: 'sr-Latn-RS',
          dir: 'ltr',
          start_url: '/',
          scope: '/',
          display: 'standalone',
          orientation: 'portrait-primary',
          theme_color: '#EEF1F0',
          background_color: '#EEF1F0',
          categories: ['education', 'utilities', 'productivity'],
          icons: [
            { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
            { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
            {
              src: '/icons/maskable-512.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'maskable',
            },
          ],
        },
      }),
    ],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      proxy: {
        '/api': { target: proxyTarget, changeOrigin: true },
        '/health': { target: proxyTarget, changeOrigin: true },
      },
    },
    build: {
      target: 'es2022',
      cssTarget: 'chrome111',
      sourcemap: false,
    },
  }
})
