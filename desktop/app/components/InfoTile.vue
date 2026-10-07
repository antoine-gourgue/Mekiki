<script setup lang="ts">
/** One labelled value in a side panel's grid. */
defineProps<{ label: string; value: string; hint?: string; valueClass?: string }>()
</script>

<template>
  <div class="rounded-md border border-default px-3 py-2">
    <p class="text-xs text-muted">{{ label }}</p>
    <p class="truncate font-semibold text-highlighted tabular-nums" :class="valueClass">
      {{ value }}
    </p>
    <p v-if="hint" class="truncate text-xs text-muted" :title="hint">{{ hint }}</p>
  </div>
</template>
