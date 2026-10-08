// Tauri serves static files: the app is a pure SPA, generated with `nuxt generate`.
export default defineNuxtConfig({
  modules: ['@nuxt/ui', '@nuxt/eslint'],

  ssr: false,

  devtools: { enabled: false },

  app: {
    head: {
      htmlAttrs: { lang: 'fr' },
      title: 'Mekiki',
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
        { rel: 'icon', sizes: '32x32', href: '/favicon.ico' },
      ],
    },
  },

  css: ['~/assets/css/main.css'],

  // The interface is designed dark only. A key of its own ignores the "system" choice
  // stored by earlier versions.
  colorMode: {
    preference: 'dark',
    fallback: 'dark',
    storageKey: 'mekiki-color-mode',
  },

  runtimeConfig: {
    public: {
      // Overridden with NUXT_PUBLIC_ENGINE_URL; must match the port the engine listens on.
      engineUrl: 'http://127.0.0.1:18421',
      // The public website (NUXT_PUBLIC_SHOWCASE=true on Vercel) has no engine to talk to:
      // it presents the app and offers the installer instead of the sign-in forms.
      showcase: false,
    },
  },

  // The desktop app must work offline: icons are bundled instead of fetched from Iconify.
  icon: {
    provider: 'none',
    fallbackToApi: false,
    clientBundle: { scan: true },
  },

  // The dev server bundles icons once at start-up; icons added while it runs come from
  // Iconify instead of rendering blank.
  $development: {
    icon: { provider: 'iconify', fallbackToApi: true },
  },

  // Tauri expects a fixed port in dev and does not need the Nuxt dev server on the network.
  devServer: { host: 'localhost', port: 3000 },

  vite: {
    clearScreen: false,
    envPrefix: ['VITE_', 'TAURI_'],
    server: { strictPort: true },
  },

  compatibilityDate: '2026-10-01',
})
