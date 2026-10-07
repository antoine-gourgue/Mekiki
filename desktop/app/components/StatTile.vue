<script setup lang="ts">
defineProps<{
  label: string
  value: string
  hint?: string
  icon?: string
  valueClass?: string
}>()
</script>

<template>
  <UCard :ui="{ body: 'p-4 sm:p-4' }">
    <div class="flex items-center gap-2 text-sm text-muted">
      <UIcon v-if="icon" :name="icon" class="size-4 shrink-0" />
      <span>{{ label }}</span>
    </div>
    <p class="mt-1 text-2xl font-semibold text-highlighted" :class="valueClass">{{ value }}</p>
    <p v-if="hint" class="mt-0.5 text-xs text-muted">{{ hint }}</p>
  </UCard>
</template>
