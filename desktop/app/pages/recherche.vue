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

const drawer = useDrawer()

function openResult(result: SearchResult) {
  drawer.open({
    kind: 'listing',
    listing: {
      ...result,
      game: searched.value?.game ?? form.game,
      product_id: searched.value?.product?.id_product ?? null,
      label: searched.value?.product?.name ?? null,
    },
  })
}

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
// Labels only: the Yahoo descriptions would crowd a single line of checkboxes.
const sourceItems = SCANNABLE_SOURCE_ITEMS.map(({ value, label }) => ({ value, label }))
</script>

<template>
  <UDashboardPanel id="search">
    <template #header>
      <PageNavbar
        title="Recherche"
        description="Chaque annonce est chiffrée comme une carte d’un colis type : coût de revient, revente, marge et ROI."
      >
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
      </PageNavbar>
    </template>

    <template #body>
      <UCard :ui="{ body: 'sm:p-5' }">
        <form class="space-y-4" @submit.prevent="search">
          <div class="flex flex-wrap gap-2.5">
            <UInput
              v-model="form.query"
              autofocus
              size="xl"
              icon="i-lucide-search"
              placeholder="Dracaufeu ex 201/165, リザードン SAR, OP05-119…"
              aria-label="Mots-clés"
              class="min-w-0 flex-[1_1_420px]"
            />
            <USelect
              v-model="form.game"
              :items="gameItems"
              size="xl"
              class="w-40"
              aria-label="Jeu"
            />
            <UButton
              type="submit"
              size="xl"
              label="Chercher"
              :loading="searching"
              :disabled="!form.query.trim() || !form.sources.length"
            />
          </div>
          <p class="text-xs text-dimmed">
            Un nom en français ou en anglais est cherché en japonais. Chaque site est interrogé l’un
            après l’autre, quelques secondes entre deux requêtes.
          </p>

          <div class="grid gap-4 border-t border-default pt-4 sm:grid-cols-3">
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

          <div class="grid gap-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <ProductPicker v-model="product" :game="form.game" />
            <UFormField v-if="!product" label="Ou un prix de revente visé">
              <MoneyInput v-model="form.expected_sale_cents" currency="EUR" />
            </UFormField>
          </div>

          <UFormField label="Sites">
            <UCheckboxGroup
              v-model="form.sources"
              :items="sourceItems"
              orientation="horizontal"
              :ui="{ fieldset: 'flex-wrap gap-x-5 gap-y-2' }"
            />
          </UFormField>
        </form>
      </UCard>

      <UAlert
        v-for="(message, source) in response?.errors ?? {}"
        :key="source"
        color="warning"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        :title="`${SOURCE_LABELS[source as ScannableSource] ?? source} indisponible`"
        :description="message"
      />

      <UEmpty
        v-if="!response"
        icon="i-lucide-search"
        title="Cherchez une carte sur Mercari et Rakuma"
        description="Tapez un nom en français, en anglais ou en japonais, avec son numéro si vous le connaissez."
      />

      <template v-else>
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="min-w-0">
            <p class="font-semibold text-highlighted">
              {{ visible.length }} annonce{{ visible.length > 1 ? 's' : '' }}
              <span v-if="response.expected_sale_cents != null" class="font-normal text-muted">
                · revente estimée {{ formatCents(response.expected_sale_cents) }}
              </span>
            </p>
            <p
              v-if="response.searched_query && response.searched_query !== form.query.trim()"
              class="mt-1 flex items-center gap-2 text-sm text-muted"
            >
              Cherché en japonais
              <span class="rounded-md bg-accented px-2 py-0.5 text-highlighted">
                {{ response.searched_query }}
              </span>
            </p>
            <p v-else-if="response.expected_sale_cents == null" class="mt-1 text-sm text-muted">
              Indiquez un prix de revente pour voir les marges.
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <UButton
              v-for="(url, source) in response.neokyo_search_urls"
              :key="source"
              color="neutral"
              variant="ghost"
              trailing-icon="i-lucide-arrow-up-right"
              :label="`${SOURCE_LABELS[source as ScannableSource] ?? source} sur Neokyo`"
              @click="openExternal(url)"
            />
            <UButton
              v-if="rejectedCount"
              color="neutral"
              :variant="showRejected ? 'soft' : 'outline'"
              :label="
                showRejected
                  ? `Masquer les ${rejectedCount} écartées`
                  : `Afficher les ${rejectedCount} écartées`
              "
              @click="showRejected = !showRejected"
            />
            <UButton
              v-if="searched?.product"
              color="neutral"
              variant="outline"
              icon="i-lucide-scale"
              label="Faut-il l’acheter ?"
              @click="drawer.open({ kind: 'product', id: searched.product.id_product })"
            />
          </div>
        </div>

        <div class="space-y-2.5">
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
            @open="openResult(result)"
          />
        </div>
      </template>

      <TrackedCardModal
        v-model:open="tracking"
        :initial="trackInitial"
        :initial-product="product"
      />
    </template>
  </UDashboardPanel>
</template>
