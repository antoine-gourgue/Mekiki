<script setup lang="ts">
/** The app's eye mark, with the name when there is room for it. */
defineProps<{ collapsed?: boolean }>()
</script>

<template>
  <NuxtLink to="/" class="flex min-w-0 items-center gap-2" aria-label="Mekiki, tableau de bord">
    <svg viewBox="0 0 1024 1024" class="size-7 shrink-0" aria-hidden="true">
      <rect x="64" y="64" width="896" height="896" rx="200" fill="#4f46e5" />
      <path d="M168 512 C 296 300, 728 300, 856 512 C 728 724, 296 724, 168 512 Z" fill="#ffffff" />
      <circle cx="512" cy="512" r="150" fill="#6366f1" />
      <circle cx="512" cy="512" r="72" fill="#1e1b4b" />
      <circle cx="560" cy="462" r="30" fill="#ffffff" />
    </svg>
    <span v-if="!collapsed" class="truncate font-semibold text-highlighted">
      Mekiki <span class="text-sm font-normal text-muted">目利き</span>
    </span>
  </NuxtLink>
</template>
