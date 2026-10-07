<script setup lang="ts">
import type { AlertProps } from '@nuxt/ui'
import type { CardVerdict, Verdict, VerdictQuery, VerdictSignal } from '~/types/engine'

/**
 * "Faut-il l'acheter ?": the verdict on a card, its resale on each outlet with the most to
 * pay in Japan, warning signals, then European prices (eBay, Vinted).
 */
const props = defineProps<{ query: VerdictQuery }>()

const engine = useEngine()

const result = ref<CardVerdict | null>(null)
const failure = ref<string | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  failure.value = null
  try {
    result.value = await engine.verdict(props.query)
  } catch (error) {
    failure.value = engineErrorMessage(error)
  } finally {
    loading.value = false
  }
}
watch(() => JSON.stringify(props.query), load, { immediate: true })

const LOOKS: Record<Verdict, { color: AlertProps['color']; icon: string }> = {
  good: { color: 'success', icon: 'i-lucide-thumbs-up' },
  fair: { color: 'warning', icon: 'i-lucide-scale' },
  bad: { color: 'error', icon: 'i-lucide-thumbs-down' },
  suspicious: { color: 'error', icon: 'i-lucide-shield-alert' },
  unknown: { color: 'neutral', icon: 'i-lucide-circle-help' },
  limit: { color: 'primary', icon: 'i-lucide-target' },
}

const SIGNAL_LOOKS: Record<VerdictSignal['tone'], { icon: string; class: string }> = {
  positive: { icon: 'i-lucide-trending-up', class: 'text-success' },
  warning: { icon: 'i-lucide-triangle-alert', class: 'text-warning' },
  negative: { icon: 'i-lucide-octagon-alert', class: 'text-error' },
  neutral: { icon: 'i-lucide-info', class: 'text-muted' },
}

const costLine = computed(() => {
  const r = result.value
  if (!r || r.landed_cents == null) return undefined
  const bought = r.price_jpy != null ? `${formatYen(r.price_jpy)} au Japon, ` : ''
  return `${bought}coût de revient ${formatCents(r.landed_cents)} · objectif ROI ${formatRatio(r.target_roi)}`
})
</script>

<template>
  <div class="space-y-4">
    <UAlert
      v-if="failure"
      color="error"
      variant="subtle"
      :title="failure"
      :actions="[{ label: 'Réessayer', onClick: () => load() }]"
    />

    <template v-else-if="result">
      <UAlert
        :color="LOOKS[result.verdict].color"
        :icon="LOOKS[result.verdict].icon"
        variant="subtle"
        :title="result.headline"
        :description="costLine"
        :ui="{ title: 'text-base' }"
      />

      <div v-if="result.outlets.length" class="overflow-hidden rounded-md border border-default">
        <div
          v-for="outlet in result.outlets"
          :key="outlet.platform"
          class="grid grid-cols-2 gap-x-4 gap-y-1 border-b border-default p-3 last:border-b-0"
        >
          <div class="col-span-2 flex items-baseline justify-between gap-2">
            <p class="font-medium text-highlighted">{{ PLATFORM_LABELS[outlet.platform] }}</p>
            <p class="truncate text-xs text-muted" :title="outlet.basis">{{ outlet.basis }}</p>
          </div>
          <p class="text-sm text-muted">
            Revente
            <span class="font-medium text-default tabular-nums">
              {{ formatCents(outlet.sale_cents) }}
            </span>
          </p>
          <p class="text-sm text-muted">
            Net après frais
            <span class="font-medium text-default tabular-nums">
              {{ formatCents(outlet.net_cents) }}
            </span>
          </p>
          <p v-if="outlet.margin_cents != null" class="text-sm text-muted">
            Marge
            <span class="font-medium tabular-nums" :class="signClass(outlet.margin_cents)">
              {{ formatCents(outlet.margin_cents) }}
            </span>
            <template v-if="outlet.roi != null"> · ROI {{ formatRatio(outlet.roi) }}</template>
          </p>
          <p v-if="query.item_id == null" class="text-sm text-muted">
            Prix max au Japon
            <span class="font-medium text-default tabular-nums">
              {{
                outlet.max_buy_jpy && outlet.max_buy_jpy > 0 ? formatYen(outlet.max_buy_jpy) : '—'
              }}
            </span>
          </p>
        </div>
      </div>

      <ul v-if="result.signals.length" class="space-y-1.5">
        <li v-for="signal in result.signals" :key="signal.text" class="flex gap-2 text-sm">
          <UIcon
            :name="SIGNAL_LOOKS[signal.tone].icon"
            class="mt-0.5 size-4 shrink-0"
            :class="SIGNAL_LOOKS[signal.tone].class"
          />
          <span>{{ signal.text }}</span>
        </li>
      </ul>

      <ResalePanel :query="{ q: result.prices.query }" :initial="result.prices" />
    </template>

    <div v-else-if="loading" class="flex justify-center py-6">
      <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-muted" />
    </div>
  </div>
</template>
