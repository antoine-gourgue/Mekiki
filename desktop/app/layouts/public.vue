<script setup lang="ts">
const route = useRoute()
// The public website has no engine: it offers the installer instead of the forms.
const showcase = useRuntimeConfig().public.showcase

// The section links only make sense on the landing page.
const sections = [
  { to: '/accueil#fonctionnement', label: 'Fonctionnement' },
  { to: '/accueil#outils', label: 'Outils' },
  { to: '/accueil#vendre', label: 'Vente en Europe' },
]
</script>

<template>
  <div class="flex min-h-dvh flex-col bg-default">
    <header class="sticky top-0 z-10 border-b border-default bg-default/80 backdrop-blur">
      <div class="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <AppLogo to="/accueil" class="shrink-0" />
        <nav class="flex items-center gap-1 sm:gap-2">
          <template v-if="route.path === '/accueil'">
            <UButton
              v-for="section in sections"
              :key="section.to"
              :to="section.to"
              :label="section.label"
              color="neutral"
              variant="ghost"
              class="hidden text-muted md:inline-flex"
            />
          </template>
          <UButton
            v-if="showcase"
            :to="INSTALLER_URL"
            external
            icon="i-lucide-download"
            label="Télécharger"
          />
          <template v-else>
            <UButton
              v-if="route.path !== '/connexion'"
              label="Se connecter"
              color="neutral"
              variant="ghost"
              to="/connexion"
            />
            <UButton
              v-if="route.path !== '/inscription'"
              label="Créer un compte"
              to="/inscription"
            />
          </template>
        </nav>
      </div>
    </header>

    <main class="flex-1">
      <slot />
    </main>

    <footer class="border-t border-default">
      <div
        class="mx-auto flex max-w-6xl flex-wrap justify-between gap-3 px-4 py-7 text-sm text-dimmed sm:px-6"
      >
        <span>Mekiki · 目利き, « avoir l’œil »</span>
        <span>Mercari · Rakuma · Cardmarket · Vinted · eBay</span>
      </div>
    </footer>
  </div>
</template>
