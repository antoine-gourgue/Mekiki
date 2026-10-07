<script setup lang="ts">
import type { SaleBreakdown } from '~/types/engine'

const props = defineProps<{ sale: SaleBreakdown }>()

const lines = computed(() => [
  { label: 'Chiffre d’affaires (port compris)', cents: props.sale.revenue_cents },
  { label: 'Frais de plateforme', cents: -props.sale.platform_fee_cents },
  { label: 'Envoi', cents: -props.sale.shipping_cost_cents },
  { label: 'Emballage', cents: -props.sale.packaging_cents },
  { label: 'Cotisations', cents: -props.sale.contributions_cents },
])
</script>

<template>
  <dl class="space-y-1 text-sm">
    <div v-for="line in lines" :key="line.label" class="flex justify-between gap-6">
      <dt class="text-muted">{{ line.label }}</dt>
      <dd class="tabular-nums">{{ formatCents(line.cents) }}</dd>
    </div>
    <div class="flex justify-between gap-6 border-t border-default pt-1 font-medium">
      <dt>Net</dt>
      <dd class="tabular-nums">{{ formatCents(sale.net_cents) }}</dd>
    </div>
    <div class="flex justify-between gap-6 font-medium">
      <dt>Marge</dt>
      <dd class="tabular-nums" :class="signClass(sale.margin_cents)">
        {{ formatCents(sale.margin_cents) }}
      </dd>
    </div>
    <div class="flex justify-between gap-6 font-medium">
      <dt>ROI</dt>
      <dd class="tabular-nums" :class="signClass(sale.roi)">{{ formatRatio(sale.roi) }}</dd>
    </div>
  </dl>
</template>
