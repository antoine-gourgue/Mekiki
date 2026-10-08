<script setup lang="ts">
/** The Mekiki mark (a card under a torii), with the name when there is room for it. */
withDefaults(defineProps<{ collapsed?: boolean; to?: string }>(), { to: '/' })
</script>

<template>
  <NuxtLink :to="to" class="flex min-w-0 items-center gap-2.5" aria-label="Mekiki, accueil">
    <img src="/brand/mekiki-mark.svg" alt="" class="size-8 shrink-0" />
    <span
      v-if="!collapsed"
      class="text-lg font-semibold tracking-tight whitespace-nowrap text-highlighted"
    >
      mekiki
    </span>
  </NuxtLink>
</template>
