<script setup lang="ts">
/** Sign-in and sign-up pages: the brand on one side, the form on the other. */
const tabs = [
  { to: '/connexion', label: 'Se connecter' },
  { to: '/inscription', label: 'Créer un compte' },
]
</script>

<template>
  <div class="mx-auto grid w-full max-w-6xl gap-6 px-4 py-8 sm:px-6 lg:grid-cols-2 lg:py-12">
    <section
      class="hidden flex-col justify-end gap-8 rounded-2xl border border-default bg-[#121116] p-10 lg:flex"
    >
      <span
        class="text-[88px] leading-none font-bold tracking-wider text-ink-800"
        aria-hidden="true"
      >
        目利き
      </span>
      <div>
        <h1 class="text-4xl/tight font-semibold tracking-tight text-highlighted">
          Avoir l’œil, chiffres à l’appui.
        </h1>
        <p class="mt-4 text-muted">
          Votre stock, vos lots, vos cartes suivies et vos connexions Vinted et eBay vous attendent.
        </p>
      </div>
      <ul class="space-y-2.5">
        <li class="flex items-center gap-3.5 rounded-lg border border-default bg-muted p-3.5">
          <span class="flex size-9 shrink-0 items-center justify-center rounded-md bg-success/15">
            <UIcon name="i-lucide-trending-up" class="size-4 text-success" />
          </span>
          <span class="text-sm">
            <span class="block font-medium text-highlighted"
              >Les bonnes affaires dès leur parution</span
            >
            <span class="text-dimmed">le scanner suit vos cartes sur Mercari et Rakuma</span>
          </span>
        </li>
        <li class="flex items-center gap-3.5 rounded-lg border border-default bg-muted p-3.5">
          <span class="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/15">
            <UIcon name="i-lucide-package" class="size-4 text-primary" />
          </span>
          <span class="text-sm">
            <span class="block font-medium text-highlighted">Le vrai coût de chaque carte</span>
            <span class="text-dimmed">frais Neokyo, envoi et TVA répartis au centime</span>
          </span>
        </li>
      </ul>
    </section>

    <div class="flex items-center justify-center py-6">
      <div class="w-full max-w-sm space-y-6">
        <nav
          aria-label="Connexion ou inscription"
          class="grid grid-cols-2 gap-1 rounded-lg border border-default bg-muted p-1"
        >
          <NuxtLink
            v-for="tab in tabs"
            :key="tab.to"
            :to="tab.to"
            class="flex h-10 items-center justify-center rounded-md text-sm font-medium text-muted transition-colors hover:text-highlighted"
            active-class="bg-accented text-highlighted"
          >
            {{ tab.label }}
          </NuxtLink>
        </nav>
        <slot />
      </div>
    </div>
  </div>
</template>
