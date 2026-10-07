<script setup lang="ts">
/** Number input bound to an amount in minor units: euro cents or yen. */
const props = withDefaults(
  defineProps<{
    currency: 'EUR' | 'JPY'
    placeholder?: string
    autofocus?: boolean
  }>(),
  { placeholder: undefined, autofocus: false },
)

const model = defineModel<number | null>({ default: null })

const factor = computed(() => (props.currency === 'EUR' ? 100 : 1))

const value = computed<number | null>({
  get: () => (model.value == null ? null : model.value / factor.value),
  set: (input) => {
    model.value = input == null || Number.isNaN(input) ? null : Math.round(input * factor.value)
  },
})

const formatOptions = computed<Intl.NumberFormatOptions>(() => ({
  style: 'currency',
  currency: props.currency,
  currencyDisplay: 'narrowSymbol',
  minimumFractionDigits: props.currency === 'EUR' ? 2 : 0,
}))
</script>

<template>
  <UInputNumber
    v-model="value"
    :format-options="formatOptions"
    locale="fr-FR"
    :min="0"
    :step="currency === 'EUR' ? 0.01 : 1"
    :increment="false"
    :decrement="false"
    :placeholder="placeholder"
    :autofocus="autofocus"
    class="w-full"
  />
</template>
