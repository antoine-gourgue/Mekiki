<script setup lang="ts">
import type {
  BrowserPrices,
  BrowserSite,
  CardVerdict,
  Verdict,
  VerdictQuery,
  VerdictSignal,
} from '~/types/engine'

/**
 * "Faut-il l'acheter ?": the verdict on a card, its resale on each outlet with the most to
 * pay in Japan, warning signals, then what sells on Vinted and eBay, read in Chrome.
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

const LOOKS: Record<Verdict, { box: string; icon: string; iconClass: string }> = {
  good: {
    box: 'border-success/40 bg-success/10',
    icon: 'i-lucide-thumbs-up',
    iconClass: 'text-success',
  },
  fair: { box: 'border-default bg-elevated', icon: 'i-lucide-scale', iconClass: 'text-warning' },
  bad: {
    box: 'border-error/40 bg-error/10',
    icon: 'i-lucide-thumbs-down',
    iconClass: 'text-error',
  },
  suspicious: {
    box: 'border-error/40 bg-error/10',
    icon: 'i-lucide-shield-alert',
    iconClass: 'text-error',
  },
  unknown: {
    box: 'border-default bg-elevated',
    icon: 'i-lucide-circle-help',
    iconClass: 'text-muted',
  },
  limit: {
    box: 'border-default bg-elevated',
    icon: 'i-lucide-target',
    iconClass: 'text-primary',
  },
}

const SIGNAL_LOOKS: Record<VerdictSignal['tone'], { icon: string; class: string }> = {
  positive: { icon: 'i-lucide-trending-up', class: 'text-success' },
  warning: { icon: 'i-lucide-triangle-alert', class: 'text-warning' },
  negative: { icon: 'i-lucide-octagon-alert', class: 'text-error' },
  neutral: { icon: 'i-lucide-info', class: 'text-muted' },
}

// Vinted listings and eBay sold listings, read in Mekiki's Chrome window on demand.
const SITE_LABELS: Record<BrowserSite, string> = {
  vinted: 'Annonces Vinted',
  ebay: 'Ventes réussies eBay',
}
const market = ref<BrowserPrices[]>([])
const reading = ref(false)
const SITE_NAMES: Record<BrowserSite, string> = { vinted: 'Vinted', ebay: 'eBay' }
// A few listings at first, all of them on demand.
const SHOWN_LISTINGS = 6
const expanded = reactive<Partial<Record<BrowserSite, boolean>>>({})

function shownListings(read: BrowserPrices) {
  const relevant = read.listings.filter((listing) => listing.relevant)
  return expanded[read.site] ? relevant : relevant.slice(0, SHOWN_LISTINGS)
}

async function readMarket() {
  const current = result.value
  if (!current) return
  reading.value = true
  market.value = []
  try {
    for (const site of ['vinted', 'ebay'] as const) {
      const query = current.market_queries[site]
      if (!query) continue
      market.value = [
        ...market.value,
        await engine.sitePrices(site, {
          query,
          card_number: current.card_number,
          names: current.card_names,
        }),
      ]
    }
    await load()
  } catch (error) {
    failure.value = engineErrorMessage(error)
  } finally {
    reading.value = false
  }
}

/** The highest price worth paying in Japan, on the outlet that allows the most. */
const bestMaxBuy = computed(() => {
  // The "limit" headline already gives this price.
  if (props.query.item_id != null || result.value?.verdict === 'limit') return null
  const best = (result.value?.outlets ?? [])
    .filter((outlet) => outlet.max_buy_jpy && outlet.max_buy_jpy > 0)
    .sort((a, b) => b.max_buy_jpy! - a.max_buy_jpy!)[0]
  return best ? { jpy: best.max_buy_jpy!, platform: best.platform } : null
})

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
      <div class="flex gap-3 rounded-xl border p-4" :class="LOOKS[result.verdict].box">
        <UIcon
          :name="LOOKS[result.verdict].icon"
          class="mt-0.5 size-5 shrink-0"
          :class="LOOKS[result.verdict].iconClass"
        />
        <div class="min-w-0">
          <p class="font-semibold text-highlighted">{{ result.headline }}</p>
          <p v-if="costLine" class="mt-1 text-sm text-muted">{{ costLine }}</p>
        </div>
      </div>

      <div
        v-if="bestMaxBuy"
        class="flex items-center justify-between gap-3 rounded-xl bg-elevated px-4 py-3.5"
      >
        <div>
          <p class="text-sm text-muted">
            Payer au plus · {{ formatRatio(result.target_roi) }} de ROI
          </p>
          <p class="text-xs text-dimmed">
            port au Japon compris, revente sur {{ PLATFORM_LABELS[bestMaxBuy.platform] }}
          </p>
        </div>
        <p class="text-2xl font-semibold text-highlighted tabular-nums">
          {{ formatYen(bestMaxBuy.jpy) }}
        </p>
      </div>

      <div v-if="result.outlets.length" class="overflow-x-auto rounded-xl bg-elevated">
        <table class="w-full min-w-[420px] text-sm">
          <thead>
            <tr class="text-left text-xs text-dimmed">
              <th class="px-4 pt-3 pb-2 font-medium">Revente</th>
              <th class="px-2 pt-3 pb-2 text-right font-medium">Prix</th>
              <th class="px-2 pt-3 pb-2 text-right font-medium">Net</th>
              <th class="px-4 pt-3 pb-2 text-right font-medium">Marge</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="outlet in result.outlets"
              :key="outlet.platform"
              class="border-t border-muted"
            >
              <td class="px-4 py-2.5">
                <p class="font-medium text-highlighted">{{ PLATFORM_LABELS[outlet.platform] }}</p>
                <p class="max-w-52 truncate text-xs text-dimmed" :title="outlet.basis">
                  {{ outlet.basis }}
                </p>
              </td>
              <td class="px-2 py-2.5 text-right tabular-nums">
                {{ formatCents(outlet.sale_cents) }}
              </td>
              <td class="px-2 py-2.5 text-right tabular-nums">
                {{ formatCents(outlet.net_cents) }}
              </td>
              <td class="px-4 py-2.5 text-right">
                <p class="font-medium tabular-nums" :class="signClass(outlet.margin_cents)">
                  {{ formatSignedCents(outlet.margin_cents) }}
                </p>
                <p v-if="outlet.roi != null" class="text-xs text-dimmed">
                  ROI {{ formatRatio(outlet.roi) }}
                </p>
                <p
                  v-else-if="query.item_id == null && outlet.max_buy_jpy && outlet.max_buy_jpy > 0"
                  class="text-xs text-dimmed"
                >
                  max {{ formatYen(outlet.max_buy_jpy) }}
                </p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <ul v-if="result.signals.length" class="space-y-2">
        <li v-for="signal in result.signals" :key="signal.text" class="flex gap-2.5 text-sm">
          <UIcon
            :name="SIGNAL_LOOKS[signal.tone].icon"
            class="mt-0.5 size-4 shrink-0"
            :class="SIGNAL_LOOKS[signal.tone].class"
          />
          <span class="text-toned">{{ signal.text }}</span>
        </li>
      </ul>

      <section class="space-y-3 rounded-xl border border-default p-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p class="font-semibold text-highlighted">Ce qui se vend vraiment</p>
            <p class="text-xs text-dimmed">
              Lu dans la fenêtre Chrome de Mekiki, connectée à vos comptes.
            </p>
          </div>
          <UButton
            v-if="result.card_number"
            icon="i-lucide-scan-search"
            :label="market.length ? 'Relire' : 'Lire Vinted et eBay'"
            size="sm"
            variant="soft"
            :loading="reading"
            @click="readMarket"
          />
        </div>
        <BrowserLog :active="reading" />
        <p v-if="!result.card_number" class="text-xs text-error">
          Numéro de carte inconnu : impossible de trier les annonces Vinted et eBay de cette carte
          parmi les autres. Choisissez l’impression japonaise, ou indiquez le numéro sur la carte.
        </p>

        <div v-for="read in market" :key="read.site" class="space-y-2">
          <div class="flex flex-wrap items-baseline justify-between gap-2">
            <p class="text-xs font-semibold tracking-[0.12em] text-dimmed uppercase">
              {{ SITE_LABELS[read.site] }}
            </p>
            <p v-if="read.error" class="text-xs text-error">{{ read.error }}</p>
            <p v-else-if="read.relevant_count" class="text-xs text-muted">
              médiane
              <span class="font-semibold text-highlighted tabular-nums">
                {{ formatCents(read.median_cents) }}
              </span>
              · {{ read.relevant_count }} annonce{{ read.relevant_count > 1 ? 's' : '' }} ·
              <span class="tabular-nums">
                {{ formatCents(read.min_cents) }} à {{ formatCents(read.max_cents) }}
              </span>
            </p>
            <p v-else class="text-xs text-muted">aucune annonce de cette carte</p>
          </div>
          <p
            v-if="read.sales_30_days != null && read.relevant_count"
            class="flex items-center gap-1.5 text-xs text-muted"
          >
            <UIcon name="i-lucide-activity" class="size-3.5" />
            Fréquence de vente :
            <span class="font-semibold text-highlighted tabular-nums">
              {{ read.sales_30_days }}
            </span>
            sur 30 jours ·
            <span class="font-semibold text-highlighted tabular-nums">
              {{ read.sales_90_days }}
            </span>
            sur 90 jours
          </p>
          <ul class="space-y-1.5">
            <li v-for="listing in shownListings(read)" :key="listing.external_id">
              <button
                type="button"
                class="group flex w-full items-center gap-3 rounded-lg bg-elevated p-2 text-left text-sm transition-colors hover:bg-accented"
                :title="`Ouvrir l’annonce sur ${SITE_NAMES[read.site]}`"
                @click="openExternal(listing.url)"
              >
                <span
                  class="flex h-13 w-10 shrink-0 items-center justify-center overflow-hidden rounded-md bg-accented"
                >
                  <img
                    v-if="listing.image_url"
                    :src="listing.image_url"
                    alt=""
                    loading="lazy"
                    referrerpolicy="no-referrer"
                    class="size-full object-cover"
                  />
                  <UIcon v-else name="i-lucide-image-off" class="size-4 text-dimmed" />
                </span>
                <span class="min-w-0 flex-1">
                  <span class="line-clamp-1 text-highlighted" :title="listing.title">
                    {{ listing.title }}
                  </span>
                  <span class="block text-xs text-dimmed">
                    {{ listing.detail }}
                    <template v-if="listing.shipping_cents">
                      · + {{ formatCents(listing.shipping_cents) }} de port
                    </template>
                  </span>
                </span>
                <span class="shrink-0 font-semibold tabular-nums">
                  {{ formatCents(listing.price_cents) }}{{ listing.best_offer ? '*' : '' }}
                </span>
                <UIcon
                  name="i-lucide-arrow-up-right"
                  class="size-4 shrink-0 text-dimmed group-hover:text-highlighted"
                />
              </button>
            </li>
          </ul>
          <UButton
            v-if="read.relevant_count > SHOWN_LISTINGS"
            size="sm"
            color="neutral"
            variant="ghost"
            :label="expanded[read.site] ? 'Voir moins' : `Voir les ${read.relevant_count} annonces`"
            @click="expanded[read.site] = !expanded[read.site]"
          />
        </div>
        <p
          v-if="market.some((r) => r.listings.some((l) => l.best_offer))"
          class="text-xs text-dimmed"
        >
          * Offre acceptée : le prix réel était plus bas.
        </p>
      </section>
    </template>

    <div v-else-if="loading" class="flex justify-center py-6">
      <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-muted" />
    </div>
  </div>
</template>
