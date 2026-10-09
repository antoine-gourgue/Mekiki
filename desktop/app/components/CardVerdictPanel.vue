<script setup lang="ts">
import type {
  BrowserPrices,
  CardVerdict,
  Verdict,
  VerdictQuery,
  VerdictSignal,
} from '~/types/engine'

/**
 * "Faut-il l'acheter ?": the verdict on a card, its resale on each outlet with the most to
 * pay in Japan, warning signals, then its eBay sales (read in Chrome when the card opens) and
 * its live eBay listings.
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

// A few listings at first, all of them on demand.
const SHOWN_LISTINGS = 6

// eBay's sold listings, read in Mekiki's Chrome window when the card opens. The engine keeps
// them six hours: opening the card again loads nothing.
const sold = ref<BrowserPrices | null>(null)
const soldFailure = ref<string | null>(null)
const readingSold = ref(false)
const soldExpanded = ref(false)
const shownSold = computed(() => {
  const relevant = sold.value?.listings.filter((listing) => listing.relevant) ?? []
  return soldExpanded.value ? relevant : relevant.slice(0, SHOWN_LISTINGS)
})

// Another card may open while the previous one is still read: its results are dropped.
let opened = 0

const soldError = computed(() => soldFailure.value ?? sold.value?.error ?? null)
// eBay shows its sold listings to signed-in visitors only.
const needsSignIn = computed(() => /connectez-vous/i.test(soldError.value ?? ''))

async function signInToEbay() {
  try {
    await engine.openSite('ebay')
  } catch (error) {
    soldFailure.value = engineErrorMessage(error)
  }
}

async function readSold() {
  const current = result.value
  const query = current?.market_queries.ebay
  if (!current?.card_number || !query) return
  const card = opened
  readingSold.value = true
  soldFailure.value = null
  try {
    const read = await engine.ebaySold({
      query,
      card_number: current.card_number,
      names: current.card_names,
    })
    if (card !== opened) return
    sold.value = read
    // The verdict now counts these sales.
    if (!read.error) result.value = await engine.verdict(props.query)
  } catch (error) {
    if (card === opened) soldFailure.value = engineErrorMessage(error)
  } finally {
    if (card === opened) readingSold.value = false
  }
}

watch(
  () => JSON.stringify(props.query),
  async () => {
    opened += 1
    sold.value = null
    soldFailure.value = null
    soldExpanded.value = false
    readingSold.value = false
    await load()
    void readSold()
  },
  { immediate: true },
)

// eBay's own listings, read with the account's eBay keys when it has some.
const ebayLive = computed(() =>
  result.value?.prices.ebay.configured ? result.value.prices.ebay : null,
)
const ebayExpanded = ref(false)
const shownEbay = computed(() => {
  const listings = ebayLive.value?.listings ?? []
  return ebayExpanded.value ? listings : listings.slice(0, SHOWN_LISTINGS)
})

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

      <section class="space-y-2.5 rounded-xl border border-default p-4">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <p class="font-semibold text-highlighted">Ventes réussies sur eBay</p>
          <p v-if="sold?.relevant_count" class="text-xs text-muted">
            médiane
            <span class="font-semibold text-highlighted tabular-nums">
              {{ formatCents(sold.median_cents) }}
            </span>
            · {{ sold.relevant_count }} vente{{ sold.relevant_count > 1 ? 's' : '' }} ·
            <span class="tabular-nums">
              {{ formatCents(sold.min_cents) }} à {{ formatCents(sold.max_cents) }}
            </span>
          </p>
        </div>
        <p class="text-xs text-dimmed">
          Ce que la carte s’est vraiment vendue,
          {{
            sold?.source === 'api'
              ? 'lu par l’API d’eBay (90 derniers jours).'
              : 'lu dans la fenêtre Chrome de Mekiki.'
          }}
        </p>
        <p v-if="!result.card_number" class="text-sm text-muted">
          Numéro de carte inconnu : impossible de trier les ventes eBay de cette carte parmi les
          autres. Choisissez l’impression japonaise, ou indiquez le numéro sur la carte.
        </p>
        <BrowserLog v-else-if="readingSold" active />
        <div v-else-if="soldError" class="flex flex-wrap items-center gap-2">
          <p class="flex-1 text-sm" :class="needsSignIn ? 'text-muted' : 'text-error'">
            {{
              needsSignIn
                ? 'Connectez-vous à eBay dans la fenêtre Chrome de Mekiki pour voir les ventes réussies.'
                : soldError
            }}
          </p>
          <UButton
            v-if="needsSignIn"
            size="sm"
            icon="i-lucide-log-in"
            label="Se connecter à eBay"
            @click="signInToEbay"
          />
          <UButton
            size="sm"
            color="neutral"
            variant="outline"
            icon="i-lucide-rotate-cw"
            label="Réessayer"
            @click="readSold"
          />
        </div>
        <template v-else-if="sold">
          <p v-if="!sold.relevant_count" class="text-sm text-muted">
            Aucune vente de cette carte trouvée sur eBay.
          </p>
          <p
            v-if="sold.sales_30_days != null && sold.relevant_count"
            class="flex items-center gap-1.5 text-xs text-muted"
          >
            <UIcon name="i-lucide-activity" class="size-3.5" />
            Fréquence de vente :
            <span class="font-semibold text-highlighted tabular-nums">
              {{ sold.sales_30_days }}
            </span>
            sur 30 jours ·
            <span class="font-semibold text-highlighted tabular-nums">
              {{ sold.sales_90_days }}
            </span>
            sur 90 jours
          </p>
          <ul class="space-y-1.5">
            <li v-for="listing in shownSold" :key="listing.external_id">
              <ListingRow
                :url="listing.url"
                :title="listing.title"
                :image-url="listing.image_url"
                :detail="listing.detail"
                :price-cents="listing.price_cents"
                :shipping-cents="listing.shipping_cents"
                :best-offer="listing.best_offer"
                site="eBay"
              />
            </li>
          </ul>
          <UButton
            v-if="sold.relevant_count > SHOWN_LISTINGS"
            size="sm"
            color="neutral"
            variant="ghost"
            :label="soldExpanded ? 'Voir moins' : `Voir les ${sold.relevant_count} ventes`"
            @click="soldExpanded = !soldExpanded"
          />
          <p v-if="shownSold.some((listing) => listing.best_offer)" class="text-xs text-dimmed">
            * Offre acceptée : le prix réel était plus bas.
          </p>
        </template>
      </section>

      <section v-if="ebayLive" class="space-y-2.5 rounded-xl border border-default p-4">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <p class="font-semibold text-highlighted">En vente sur eBay</p>
          <p v-if="ebayLive.median_cents != null" class="text-xs text-muted">
            médiane
            <span class="font-semibold text-highlighted tabular-nums">
              {{ formatCents(ebayLive.median_cents) }}
            </span>
            · {{ ebayLive.listings.length }} annonce{{ ebayLive.listings.length > 1 ? 's' : '' }}
            ·
            <span class="tabular-nums">
              {{ formatCents(ebayLive.min_cents) }} à {{ formatCents(ebayLive.max_cents) }}
            </span>
          </p>
        </div>
        <p class="text-xs text-dimmed">
          Prix demandés en ce moment, lus avec vos clés eBay : une vente se conclut souvent plus
          bas.
        </p>
        <p v-if="ebayLive.error" class="text-sm text-error">{{ ebayLive.error }}</p>
        <p v-else-if="!ebayLive.listings.length" class="text-sm text-muted">
          Aucune annonce eBay de cette carte en ce moment.
        </p>
        <ul class="space-y-1.5">
          <li v-for="listing in shownEbay" :key="listing.item_id">
            <ListingRow
              :url="listing.url"
              :title="listing.title"
              :image-url="listing.image_url"
              :detail="[listing.condition, listing.country].filter(Boolean).join(' · ')"
              :price-cents="listing.price_cents"
              :shipping-cents="listing.shipping_cents"
              site="eBay"
            />
          </li>
        </ul>
        <UButton
          v-if="ebayLive.listings.length > SHOWN_LISTINGS"
          size="sm"
          color="neutral"
          variant="ghost"
          :label="ebayExpanded ? 'Voir moins' : `Voir les ${ebayLive.listings.length} annonces`"
          @click="ebayExpanded = !ebayExpanded"
        />
      </section>
    </template>

    <div v-else-if="loading" class="flex justify-center py-6">
      <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-muted" />
    </div>
  </div>
</template>
