<script setup lang="ts">
const route = useRoute()
</script>

<template>
  <div class="flex min-h-dvh flex-col bg-default">
    <header class="sticky top-0 z-10 border-b border-default bg-default/80 backdrop-blur">
      <UContainer class="flex h-14 items-center justify-between gap-4">
        <AppLogo to="/accueil" class="shrink-0" />
        <div class="flex items-center gap-2">
          <UButton
            v-if="route.path !== '/connexion'"
            label="Se connecter"
            color="neutral"
            variant="ghost"
            to="/connexion"
            class="hidden sm:inline-flex"
          />
          <UButton v-if="route.path !== '/inscription'" label="Créer un compte" to="/inscription" />
        </div>
      </UContainer>
    </header>

    <main class="flex-1">
      <slot />
    </main>

    <footer class="border-t border-default py-6 text-center text-sm text-muted">
      Mekiki · achat au Japon, revente en Europe. Les achats restent toujours manuels.
    </footer>
  </div>
</template>
