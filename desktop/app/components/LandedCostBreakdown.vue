<script setup lang="ts">
import type { LandedCost } from '~/types/engine'

const props = defineProps<{ cost: LandedCost }>()

const lines = computed(() => [
  { label: 'Prix d’achat (+ port au Japon)', cents: props.cost.purchase_cents },
  { label: 'Frais du proxy', cents: props.cost.proxy_fees_cents },
  { label: 'Envoi international', cents: props.cost.shipping_cents },
  {
    label: props.cost.vat_estimated ? 'Taxes à l’import (TVA estimée)' : 'Taxes à l’import',
    cents: props.cost.import_taxes_cents,
  },
])
</script>

<template>
  <dl class="space-y-1 text-sm">
    <div v-for="line in lines" :key="line.label" class="flex justify-between gap-6">
      <dt class="text-muted">{{ line.label }}</dt>
      <dd class="tabular-nums">{{ formatCents(line.cents) }}</dd>
    </div>
    <div class="flex justify-between gap-6 border-t border-default pt-1 font-medium">
      <dt>Coût de revient</dt>
      <dd class="tabular-nums">{{ formatCents(cost.total_cents) }}</dd>
    </div>
  </dl>
</template>
