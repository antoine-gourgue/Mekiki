<script setup lang="ts">
import type { ResalePrices, ResaleQuery } from '~/types/engine'

/**
 * What a card sells for in Europe: live eBay listings when the engine has eBay keys, and
 * links to eBay's sold listings and to Vinted, which only the user's browser may open.
 */
const props = defineProps<{
  query: ResaleQuery
  /** Prices already fetched with the query (by a verdict): shown without a new request. */
  initial?: ResalePrices | null
}>()

const engine = useEngine()

const search = ref('')
const prices = ref<ResalePrices | null>(null)
const failure = ref<string | null>(null)
const loading = ref(false)

async function load(query: ResaleQuery) {
  loading.value = true
  failure.value = null
  try {
    prices.value = await engine.resalePrices(query)
    search.value = prices.value.query
  } catch (error) {
    failure.value = engineErrorMessage(error)
  } finally {
    loading.value = false
  }
}

// Parents pass a fresh object on every render: only a different search reloads.
watch(
  () => JSON.stringify(props.query),
  () => {
    if (props.initial && !prices.value) {
      prices.value = props.initial
      search.value = props.initial.query
    } else {
      void load(props.query)
    }
  },
  { immediate: true },
)

function submit() {
  const q = search.value.trim()
  if (q) void load({ q })
}

const ebay = computed(() => prices.value?.ebay)
const SHOWN_LISTINGS = 8
</script>

<template>
  <div class="space-y-4">
    <form class="flex gap-2" @submit.prevent="submit">
      <UInput
        v-model="search"
        icon="i-lucide-search"
        placeholder="Nom et numéro de la carte"
        class="flex-1"
        :disabled="loading && !prices"
      />
      <UButton type="submit" label="Chercher" :loading="loading" :disabled="!search.trim()" />
    </form>

    <UAlert
      v-if="failure"
      color="error"
      variant="subtle"
      icon="i-lucide-circle-alert"
      :title="failure"
    />

    <template v-if="prices">
      <div class="grid gap-2 sm:grid-cols-2">
        <UButton
          color="neutral"
          variant="outline"
          size="md"
          icon="i-lucide-badge-euro"
          label="Ventes réussies sur eBay"
          trailing-icon="i-lucide-external-link"
          block
          @click="openExternal(prices.links.ebay_sold)"
        />
        <UButton
          color="neutral"
          variant="outline"
          size="md"
          icon="i-lucide-chart-column"
          label="Historique Terapeak (90 jours)"
          trailing-icon="i-lucide-external-link"
          block
          @click="openExternal(prices.links.ebay_research)"
        />
        <UButton
          color="neutral"
          variant="outline"
          size="md"
          icon="i-lucide-tag"
          label="En vente sur eBay"
          trailing-icon="i-lucide-external-link"
          block
          @click="openExternal(prices.links.ebay_listings)"
        />
        <UButton
          color="neutral"
          variant="outline"
          size="md"
          icon="i-lucide-shirt"
          label="En vente sur Vinted"
          trailing-icon="i-lucide-external-link"
          block
          @click="openExternal(prices.links.vinted)"
        />
      </div>
      <p class="text-xs text-dimmed">
        eBay et Vinted n’ouvrent pas leurs ventes passées aux logiciels : ces pages s’ouvrent dans
        votre navigateur (les ventes réussies eBay demandent d’être connecté).
      </p>

      <UAlert
        v-if="ebay?.configured && ebay.error"
        color="warning"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="eBay n’a pas répondu"
        :description="ebay.error"
      />
      <template v-else-if="ebay?.configured">
        <div class="grid grid-cols-3 gap-2">
          <StatTile label="Prix médian" :value="formatCents(ebay.median_cents)" />
          <StatTile label="Moins cher" :value="formatCents(ebay.min_cents)" />
          <StatTile label="Plus cher" :value="formatCents(ebay.max_cents)" />
        </div>
        <p class="text-xs text-muted">
          {{ ebay.listings.length }} annonces à prix fixe en euros analysées sur {{ ebay.total }} en
          vente sur eBay, port non compris.
        </p>
        <ul v-if="ebay.listings.length" class="divide-y divide-default">
          <li v-for="listing in ebay.listings.slice(0, SHOWN_LISTINGS)" :key="listing.item_id">
            <button
              type="button"
              class="flex w-full items-center gap-3 py-2 text-left hover:bg-elevated/50"
              @click="openExternal(listing.url)"
            >
              <img
                v-if="listing.image_url"
                :src="listing.image_url"
                :alt="listing.title"
                loading="lazy"
                referrerpolicy="no-referrer"
                class="size-10 shrink-0 rounded object-cover"
              />
              <span class="line-clamp-2 min-w-0 flex-1 text-sm">{{ listing.title }}</span>
              <span class="shrink-0 text-right text-sm">
                <span class="font-medium tabular-nums">{{ formatCents(listing.price_cents) }}</span>
                <span v-if="listing.shipping_cents" class="block text-xs text-muted">
                  + {{ formatCents(listing.shipping_cents) }} de port
                </span>
              </span>
            </button>
          </li>
        </ul>
      </template>
    </template>
    <div v-else-if="loading" class="flex justify-center py-6">
      <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-muted" />
    </div>
  </div>
</template>
