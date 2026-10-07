<script setup lang="ts">
import type {
  Game,
  MarketPrice,
  ScannableSource,
  SearchResponse,
  SearchResult,
  TrackedCardCreate,
} from '~/types/engine'

const engine = useEngine()
const showError = useErrorToast()
const favorites = useFavorites()

const { data: settings } = useAsyncData('settings', () => engine.getSettings())
const targetRoi = computed(() => (settings.value?.scanner.min_roi_percent ?? 30) / 100)

const form = reactive({
  query: '',
  game: 'pokemon' as Game,
  card_number: '',
  required_keywords: '',
  excluded_keywords: '',
  sources: [...DEFAULT_SOURCES] as ScannableSource[],
  expected_sale_cents: null as number | null,
})
const product = ref<MarketPrice | null>(null)

const response = ref<SearchResponse | null>(null)
// What the shown results were searched with, to save them as favorites.
const searched = ref<{ game: Game; product: MarketPrice | null; target: number | null } | null>(
  null,
)
const searching = ref(false)
const showRejected = ref(false)

async function search() {
  if (!form.query.trim()) return
  searching.value = true
  const text = (value: string) => value.trim() || null
  try {
    response.value = await engine.search({
      query: form.query.trim(),
      game: form.game,
      sources: form.sources,
      card_number: text(form.card_number),
      required_keywords: text(form.required_keywords),
      excluded_keywords: text(form.excluded_keywords),
      cardmarket_product_id: product.value?.id_product ?? null,
      expected_sale_cents: form.expected_sale_cents,
    })
    searched.value = {
      game: form.game,
      product: product.value,
      target: product.value ? null : form.expected_sale_cents,
    }
  } catch (error) {
    showError(error, 'Recherche impossible')
  } finally {
    searching.value = false
  }
}

function toFavorite(result: SearchResult) {
  return listingToFavorite(result, {
    game: searched.value?.game ?? form.game,
    cardmarket_product_id: searched.value?.product?.id_product ?? null,
    target_price_cents: searched.value?.target ?? null,
  })
}

const visible = computed(() =>
  (response.value?.results ?? []).filter((result) => showRejected.value || result.matched),
)
const rejectedCount = computed(
  () => (response.value?.results ?? []).filter((result) => !result.matched).length,
)

// "Suivre cette carte" turns the current search into a tracked card.
const tracking = ref(false)
const trackInitial = computed<Partial<TrackedCardCreate>>(() => ({
  game: form.game,
  name: product.value?.name ?? form.query.trim(),
  card_number: form.card_number.trim() || null,
  search_query: form.query.trim(),
  required_keywords: form.required_keywords.trim() || null,
  excluded_keywords: form.excluded_keywords.trim() || null,
  target_price_cents: product.value ? null : form.expected_sale_cents,
}))

const gameItems = selectItems(GAME_LABELS)
</script>

<template>
  <UDashboardPanel id="search">
    <template #header>
      <UDashboardNavbar title="Recherche">
        <template #leading><UDashboardSidebarCollapse /></template>
        <template #right>
          <UButton
            v-if="response"
            icon="i-lucide-eye"
            color="neutral"
            variant="outline"
            label="Suivre cette carte"
            @click="tracking = true"
          />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div class="grid gap-6 xl:grid-cols-[24rem_minmax(0,1fr)]">
        <UCard>
          <form class="space-y-4" @submit.prevent="search">
            <UFormField
              label="Mots-clés"
              required
              help="En japonais ou un numéro : リザードン SAR, 201/165, OP05-119…"
            >
              <UInput
                v-model="form.query"
                autofocus
                placeholder="リザードン 201/165"
                class="w-full"
              />
            </UFormField>
            <div class="grid grid-cols-2 gap-4">
              <UFormField label="Jeu">
                <USelect v-model="form.game" :items="gameItems" class="w-full" />
              </UFormField>
              <UFormField label="Numéro exigé">
                <UInput v-model="form.card_number" placeholder="201/165" class="w-full" />
              </UFormField>
              <UFormField label="Mots obligatoires">
                <UInput v-model="form.required_keywords" placeholder="SAR" class="w-full" />
              </UFormField>
              <UFormField label="Mots exclus">
                <UInput v-model="form.excluded_keywords" placeholder="傷" class="w-full" />
              </UFormField>
            </div>
            <UFormField label="Sites">
              <UCheckboxGroup
                v-model="form.sources"
                :items="SCANNABLE_SOURCE_ITEMS"
                orientation="horizontal"
              />
            </UFormField>

            <USeparator label="Prix de revente" />
            <ProductPicker v-model="product" :game="form.game" />
            <UFormField v-if="!product" label="Ou un prix visé">
              <MoneyInput v-model="form.expected_sale_cents" currency="EUR" />
            </UFormField>

            <UButton
              type="submit"
              block
              icon="i-lucide-search"
              label="Chercher"
              :loading="searching"
              :disabled="!form.query.trim() || !form.sources.length"
            />
            <p class="text-xs text-muted">
              Une recherche interroge chaque site l’un après l’autre, en laissant quelques secondes
              entre deux requêtes.
            </p>
          </form>
        </UCard>

        <div class="space-y-3">
          <UAlert
            v-for="(message, source) in response?.errors ?? {}"
            :key="source"
            color="warning"
            variant="subtle"
            icon="i-lucide-triangle-alert"
            :title="`${SOURCE_LABELS[source as ScannableSource] ?? source} indisponible`"
            :description="message"
          />

          <div
            v-if="response && Object.keys(response.neokyo_search_urls).length"
            class="flex flex-wrap items-center gap-2 text-sm"
          >
            <span class="text-muted">Même recherche sur Neokyo :</span>
            <UButton
              v-for="(url, source) in response.neokyo_search_urls"
              :key="source"
              size="xs"
              color="neutral"
              variant="outline"
              icon="i-lucide-external-link"
              :label="SOURCE_LABELS[source as ScannableSource] ?? source"
              @click="openExternal(url)"
            />
          </div>

          <UEmpty
            v-if="!response"
            icon="i-lucide-search"
            title="Cherchez une carte sur Mercari et Yahoo"
            description="Chaque annonce est chiffrée comme une carte d’un colis type : coût de revient, revente, marge et ROI."
          />

          <template v-else>
            <div class="flex items-center justify-between gap-4">
              <p class="text-sm text-muted">
                {{ visible.length }} annonce{{ visible.length > 1 ? 's' : '' }}
                <template v-if="response.expected_sale_cents != null">
                  · revente estimée {{ formatCents(response.expected_sale_cents) }}
                </template>
                <template v-else> · indiquez un prix de revente pour voir les marges</template>
              </p>
              <USwitch
                v-if="rejectedCount"
                v-model="showRejected"
                :label="`Afficher les ${rejectedCount} écartées`"
              />
            </div>

            <div class="grid gap-3 2xl:grid-cols-2">
              <DealCard
                v-for="result in visible"
                :key="`${result.source}-${result.external_id}`"
                :title="result.title"
                :source="result.source"
                :price-jpy="result.price_jpy"
                :shipping-included="result.shipping_included"
                :url="result.url"
                :neokyo-url="result.neokyo_url"
                :thumbnail-url="result.thumbnail_url"
                :listed-at="result.listed_at"
                :ends-at="result.ends_at"
                :bids="result.bids"
                :landed-cost="result.landed_cost"
                :sale="result.sale"
                :target-roi="targetRoi"
                :muted="!result.matched"
                :note="result.matched ? null : `Écartée : ${result.reject_reason}`"
                favoritable
                :favorite="!!favorites.find(result.source, result.external_id)"
                @toggle-favorite="favorites.toggle(toFavorite(result))"
              />
            </div>
          </template>
        </div>
      </div>

      <TrackedCardModal
        v-model:open="tracking"
        :initial="trackInitial"
        :initial-product="product"
      />
    </template>
  </UDashboardPanel>
</template>
