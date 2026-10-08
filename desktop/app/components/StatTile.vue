<script setup lang="ts">
/** A headline figure in a card: label, value in tabular digits, optional hint below. */
defineProps<{
  label: string
  value: string
  hint?: string
  icon?: string
  valueClass?: string
}>()
</script>

<template>
  <UCard :ui="{ body: 'px-5 py-4 sm:px-5 sm:py-4' }">
    <div class="flex items-center gap-2 text-sm text-muted">
      <UIcon v-if="icon" :name="icon" class="size-4 shrink-0" />
      <span>{{ label }}</span>
    </div>
    <p
      class="mt-1.5 font-mono text-2xl font-semibold tracking-tight text-highlighted tabular-nums"
      :class="valueClass"
    >
      {{ value }}
    </p>
    <p v-if="hint" class="mt-1 text-xs text-dimmed">{{ hint }}</p>
  </UCard>
</template>
