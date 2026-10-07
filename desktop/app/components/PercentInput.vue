<script setup lang="ts">
/** Number input for a percentage stored as a plain number (12.3 means 12,3 %). */
withDefaults(defineProps<{ max?: number; placeholder?: string }>(), {
  max: 100,
  placeholder: undefined,
})

const model = defineModel<number | null>({ default: null })

const formatOptions: Intl.NumberFormatOptions = {
  style: 'unit',
  unit: 'percent',
  maximumFractionDigits: 2,
}
</script>

<template>
  <UInputNumber
    v-model="model"
    :format-options="formatOptions"
    locale="fr-FR"
    :min="0"
    :max="max"
    :step="0.1"
    :step-snapping="false"
    :increment="false"
    :decrement="false"
    :placeholder="placeholder"
    class="w-full"
  />
</template>
