<script setup lang="ts" generic="T extends string">
/** A row of mutually exclusive choices, the chosen one raised; an optional count per choice. */
defineProps<{
  items: { value: T; label: string; count?: number | null }[]
  label?: string
}>()

const model = defineModel<T>({ required: true })
</script>

<template>
  <div
    role="radiogroup"
    :aria-label="label"
    class="inline-flex max-w-full gap-0.5 overflow-x-auto rounded-lg border border-default bg-muted p-[3px]"
  >
    <button
      v-for="item in items"
      :key="item.value"
      type="button"
      role="radio"
      :aria-checked="model === item.value"
      class="h-8 shrink-0 rounded-md px-3 text-[13px] font-medium whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-primary"
      :class="
        model === item.value ? 'bg-accented text-highlighted' : 'text-muted hover:text-highlighted'
      "
      @click="model = item.value"
    >
      {{ item.label }}
      <span v-if="item.count != null" class="ms-1 font-mono text-xs text-dimmed">{{
        item.count
      }}</span>
    </button>
  </div>
</template>
