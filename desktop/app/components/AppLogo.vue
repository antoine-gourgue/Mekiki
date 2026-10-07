<script setup lang="ts">
/** The Mekiki seal, with the name when there is room for it. */
withDefaults(defineProps<{ collapsed?: boolean; to?: string }>(), { to: '/' })
</script>

<template>
  <NuxtLink :to="to" class="flex min-w-0 items-center gap-2.5" aria-label="Mekiki, accueil">
    <img src="/brand/mekiki-seal.svg" alt="" class="size-7 shrink-0" />
    <span v-if="!collapsed" class="flex min-w-0 items-baseline gap-2">
      <span class="font-semibold tracking-[0.18em] whitespace-nowrap text-highlighted">MEKIKI</span>
      <span class="hidden text-xs tracking-[0.3em] whitespace-nowrap text-muted sm:inline">
        目利き
      </span>
    </span>
  </NuxtLink>
</template>
