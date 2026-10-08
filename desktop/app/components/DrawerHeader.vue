<script setup lang="ts">
/** Title bar of a side panel, with back and close buttons. */
defineProps<{ title: string; subtitle?: string; icon: string }>()

const drawer = useDrawer()
</script>

<template>
  <div class="flex items-start gap-3 border-b border-default px-4 py-4 sm:px-6">
    <UButton
      v-if="drawer.stack.value.length > 1"
      icon="i-lucide-arrow-left"
      color="neutral"
      variant="ghost"
      aria-label="Retour"
      @click="drawer.back()"
    />
    <div class="min-w-0 flex-1">
      <div class="flex min-w-0 items-center gap-2.5">
        <UIcon :name="icon" class="size-4 shrink-0 text-dimmed" />
        <h2 class="truncate text-lg font-semibold text-highlighted" :title="title">{{ title }}</h2>
        <slot name="actions" />
      </div>
      <p v-if="subtitle" class="mt-0.5 truncate text-sm text-dimmed" :title="subtitle">
        {{ subtitle }}
      </p>
    </div>
    <UButton
      icon="i-lucide-x"
      color="neutral"
      variant="ghost"
      aria-label="Fermer"
      @click="drawer.close()"
    />
  </div>
</template>
