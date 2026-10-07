<script setup lang="ts">
/** Title bar of a side panel, with back and close buttons. */
defineProps<{ title: string; subtitle?: string; icon: string }>()

const drawer = useDrawer()
</script>

<template>
  <div class="flex items-center gap-3 border-b border-default px-4 py-3 sm:px-6">
    <UButton
      v-if="drawer.stack.value.length > 1"
      icon="i-lucide-arrow-left"
      color="neutral"
      variant="ghost"
      aria-label="Retour"
      @click="drawer.back()"
    />
    <div class="flex size-9 shrink-0 items-center justify-center rounded-md bg-elevated">
      <UIcon :name="icon" class="size-5 text-muted" />
    </div>
    <div class="min-w-0 flex-1">
      <p v-if="subtitle" class="truncate text-xs text-muted" :title="subtitle">{{ subtitle }}</p>
      <h2 class="truncate font-semibold text-highlighted" :title="title">{{ title }}</h2>
    </div>
    <slot name="actions" />
    <UButton
      icon="i-lucide-x"
      color="neutral"
      variant="ghost"
      aria-label="Fermer"
      @click="drawer.close()"
    />
  </div>
</template>
