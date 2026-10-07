<script setup lang="ts">
import type { Game, MarketPrice } from '~/types/engine'

/** Picks a product in the Cardmarket catalog; its price guide gives the resale price. */
const props = defineProps<{ game: Game }>()
const product = defineModel<MarketPrice | null>({ default: null })

const engine = useEngine()
const showError = useErrorToast()

const query = ref('')
const results = ref<MarketPrice[]>([])
const searching = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

watch([query, () => props.game], ([text]) => {
  clearTimeout(timer)
  if (text.trim().length < 2) {
    results.value = []
    return
  }
  timer = setTimeout(async () => {
    searching.value = true
    try {
      results.value = await engine.searchProducts(props.game, text.trim())
    } catch (error) {
      showError(error, 'Recherche Cardmarket impossible')
    } finally {
      searching.value = false
    }
  }, 300)
})

function pick(picked: MarketPrice) {
  product.value = picked
  results.value = []
  query.value = ''
}
</script>

<template>
  <div class="space-y-2">
    <div
      v-if="product"
      class="flex items-center justify-between gap-4 rounded-md border border-default p-3"
    >
      <div class="min-w-0">
        <p class="truncate font-medium">{{ product.name }}</p>
        <p class="text-sm text-muted">
          {{ formatCents(product.reference_cents) }}
          <template v-if="product.reference_field">({{ product.reference_field }})</template>
          <template v-if="product.expansion_name"> · {{ product.expansion_name }}</template>
          · n° {{ product.id_product }}
        </p>
      </div>
      <div class="flex shrink-0 gap-1">
        <UButton
          color="neutral"
          variant="ghost"
          icon="i-lucide-external-link"
          aria-label="Voir sur Cardmarket"
          @click="openExternal(product.url)"
        />
        <UButton
          color="neutral"
          variant="ghost"
          icon="i-lucide-x"
          aria-label="Retirer le produit"
          @click="product = null"
        />
      </div>
    </div>
    <UInput
      v-model="query"
      icon="i-lucide-search"
      :loading="searching"
      placeholder="Chercher dans le catalogue Cardmarket (nom français, anglais ou n° de produit)"
      class="w-full"
    />
    <ul
      v-if="results.length"
      class="max-h-64 divide-y divide-default overflow-y-auto rounded-md border border-default"
    >
      <li v-for="result in results" :key="result.id_product">
        <button
          type="button"
          class="flex w-full items-center justify-between gap-4 px-3 py-2 text-left text-sm hover:bg-elevated"
          @click="pick(result)"
        >
          <span class="min-w-0">
            <span class="flex items-center gap-2">
              <span class="truncate">{{ result.name }}</span>
              <UBadge v-if="result.japanese" label="JP" size="sm" variant="subtle" />
            </span>
            <span class="block truncate text-xs text-muted">
              {{ result.expansion_name ?? 'Extension inconnue' }} · n° {{ result.id_product }}
            </span>
          </span>
          <span class="shrink-0 text-muted tabular-nums">
            {{ formatCents(result.reference_cents) }}
          </span>
        </button>
      </li>
    </ul>
    <p v-else-if="query.trim().length >= 2 && !searching" class="text-xs text-muted">
      Aucun produit. Essayez le nom anglais, français ou le numéro de produit Cardmarket.
    </p>
  </div>
</template>
