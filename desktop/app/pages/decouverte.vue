<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import type {
  DiscoveryDepth,
  DiscoveryPick,
  DiscoveryRun,
  Game,
  ItemCreate,
  ScannableSource,
} from '~/types/engine'

const engine = useEngine()
const showError = useErrorToast()
const favorites = useFavorites()

const { data: settings } = useAsyncData('settings', () => engine.getSettings())
const { data: lots } = useAsyncData('lots', () => engine.listLots())

const form = reactive({
  game: 'pokemon' as Game,
  budget_cents: 50000 as number | null,
  card_count: 10 as number | null,
  min_roi_percent: null as number | null,
  sources: [...DEFAULT_SOURCES] as ScannableSource[],
  depth: 'quick' as DiscoveryDepth,
})

const depthItems: { value: DiscoveryDepth; label: string; description: string }[] = [
  { value: 'quick', label: 'Rapide', description: '~1 500 annonces, 1 à 2 min' },
  { value: 'deep', label: 'Approfondie', description: '~5 000 annonces, ~5 min' },
  { value: 'max', label: 'Maximale', description: '10 000+ annonces, ~15 min' },
]
// The ROI target defaults to the scanner's one, shown as the field's starting value.
watch(
  settings,
  (value) => {
    if (value && form.min_roi_percent == null) form.min_roi_percent = value.scanner.min_roi_percent
  },
  { immediate: true },
)

const run = ref<DiscoveryRun | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined

// The form starts from the last search, so a new one only changes what needs changing.
let prefilled = false
function prefill(current: DiscoveryRun | null) {
  if (prefilled || !current?.request) return
  prefilled = true
  const request = current.request
  Object.assign(form, {
    game: request.game,
    budget_cents: request.budget_cents,
    card_count: request.card_count,
    min_roi_percent: request.min_roi_percent ?? form.min_roi_percent,
    sources: request.sources?.length ? [...request.sources] : form.sources,
    depth: request.depth ?? form.depth,
  })
}

async function poll() {
  clearTimeout(timer)
  try {
    run.value = await engine.discovery()
    prefill(run.value)
  } catch (error) {
    showError(error)
  }
  if (run.value?.status === 'running') timer = setTimeout(poll, 1500)
}
onMounted(poll)
onBeforeUnmount(() => clearTimeout(timer))

const running = computed(() => run.value?.status === 'running')

async function start() {
  if (!form.budget_cents || !form.card_count) return
  try {
    run.value = await engine.startDiscovery({
      game: form.game,
      budget_cents: form.budget_cents,
      card_count: form.card_count,
      min_roi_percent: form.min_roi_percent,
      sources: form.sources,
      depth: form.depth,
    })
    void poll()
  } catch (error) {
    showError(error, 'Recherche impossible')
  }
}

async function stop() {
  try {
    run.value = await engine.stopDiscovery()
  } catch (error) {
    showError(error)
  }
}

const progress = computed(() => {
  const current = run.value
  if (!current?.searches_total) return 0
  return Math.round((current.searches_done / current.searches_total) * 100)
})
const targetRoi = computed(
  () => (run.value?.request?.min_roi_percent ?? form.min_roi_percent ?? 30) / 100,
)
const budget = computed(() => run.value?.request?.budget_cents ?? form.budget_cents ?? 0)

// "Acheté" opens the card form pre-filled, to put the card straight into a lot.
const buying = ref(false)
const purchase = ref<Partial<ItemCreate> | null>(null)

function bought(pick: DiscoveryPick) {
  purchase.value = {
    game: run.value?.request?.game ?? 'pokemon',
    name: pick.product.name ?? pick.card_label,
    card_number: pick.card_label.split(' · ')[0] ?? null,
    source_platform: pick.source,
    source_url: pick.url,
    price_jpy: pick.price_jpy,
    domestic_shipping_jpy: pick.shipping_included
      ? 0
      : (settings.value?.scanner.domestic_shipping_jpy ?? 0),
    cardmarket_product_id: pick.product.id_product,
  }
  buying.value = true
}

const showResale = useResaleModal()
const drawer = useDrawer()

function openPick(pick: DiscoveryPick) {
  drawer.open({
    kind: 'listing',
    listing: {
      ...pick,
      game: run.value?.request?.game ?? 'pokemon',
      product_id: pick.product.id_product,
      label: pick.card_label,
    },
  })
}

function menu(pick: DiscoveryPick): DropdownMenuItem[] {
  return [
    {
      label: 'Prix en Europe (eBay, Vinted)',
      icon: 'i-lucide-euro',
      onSelect: () =>
        showResale(pick.card_label, {
          product_id: pick.product.id_product,
          label: pick.card_label,
        }),
    },
    {
      label: 'Voir la cote sur Cardmarket',
      icon: 'i-lucide-chart-line',
      onSelect: () => openExternal(pick.product.url),
    },
    {
      label: 'Acheté : ajouter au stock',
      icon: 'i-lucide-package-plus',
      onSelect: () => bought(pick),
    },
  ]
}

function toFavorite(pick: DiscoveryPick) {
  return listingToFavorite(pick, {
    game: run.value?.request?.game ?? 'pokemon',
    card_label: pick.card_label,
    cardmarket_product_id: pick.product.id_product,
  })
}

function subtitle(pick: DiscoveryPick) {
  const product = pick.product.expansion_name
    ? `${pick.product.name} (${pick.product.expansion_name})`
    : pick.product.name
  return `${pick.card_label} · ${product}`
}

const gameItems = selectItems(GAME_LABELS)
</script>

<template>
  <UDashboardPanel id="discovery">
    <template #header>
      <UDashboardNavbar title="Trouver des cartes">
        <template #leading><UDashboardSidebarCollapse /></template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UCard>
        <form class="grid items-end gap-4 sm:grid-cols-2 xl:grid-cols-6" @submit.prevent="start">
          <UFormField label="Jeu">
            <USelect v-model="form.game" :items="gameItems" class="w-full" />
          </UFormField>
          <UFormField label="Budget du colis" hint="tout compris">
            <MoneyInput v-model="form.budget_cents" currency="EUR" />
          </UFormField>
          <UFormField label="Nombre de cartes">
            <UInputNumber v-model="form.card_count" :min="1" :max="50" class="w-full" />
          </UFormField>
          <UFormField label="ROI minimum">
            <PercentInput v-model="form.min_roi_percent" :max="1000" />
          </UFormField>
          <UFormField label="Profondeur" class="xl:col-span-2">
            <USelect
              v-model="form.depth"
              :items="depthItems"
              class="w-full"
              :ui="{ itemDescription: 'text-xs' }"
            />
          </UFormField>
          <UFormField label="Sites" class="xl:col-span-2">
            <UCheckboxGroup
              v-model="form.sources"
              :items="SCANNABLE_SOURCE_ITEMS"
              orientation="horizontal"
            />
          </UFormField>
          <div class="flex flex-wrap items-center gap-4 sm:col-span-2 xl:col-span-6">
            <UButton
              type="submit"
              icon="i-lucide-wand-sparkles"
              label="Trouver des cartes"
              :loading="running"
              :disabled="!form.budget_cents || !form.card_count || !form.sources.length"
            />
            <p class="text-xs text-muted">
              Parcourt les annonces récentes, reconnaît les cartes et compose le colis le plus
              rentable. Compter une à deux minutes : les sites sont interrogés sans les brusquer.
            </p>
          </div>
        </form>
      </UCard>

      <UCard v-if="running && run">
        <div class="space-y-2">
          <div class="flex justify-between text-sm">
            <span>Recherche en cours…</span>
            <span class="text-muted tabular-nums">
              {{ run.searches_done }} / {{ run.searches_total }} recherches ·
              {{ run.listings_seen.toLocaleString('fr-FR') }} annonces parcourues
            </span>
          </div>
          <UProgress :model-value="progress" />
          <div class="flex justify-end">
            <UButton
              size="xs"
              color="neutral"
              variant="outline"
              icon="i-lucide-square"
              label="Arrêter et voir les résultats"
              @click="stop"
            />
          </div>
        </div>
      </UCard>

      <UAlert
        v-for="message in run?.errors ?? []"
        :key="message"
        color="warning"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        :description="message"
      />

      <UEmpty
        v-if="!run || run.status === 'idle'"
        icon="i-lucide-wand-sparkles"
        title="Indiquez un budget et un nombre de cartes"
        description="L’app cherche sur Mercari et Yahoo, reconnaît chaque carte, la compare à sa cote Cardmarket et compose le colis le plus rentable qui tient dans le budget."
      />

      <template v-else-if="run.status === 'done' || run.status === 'failed'">
        <p class="text-sm text-muted">
          <UBadge
            v-if="run.stopped"
            color="neutral"
            variant="outline"
            label="Recherche arrêtée"
            class="mr-1"
          />
          {{ run.listings_seen.toLocaleString('fr-FR') }} annonces parcourues ·
          {{ run.listings_identified }} cartes reconnues · {{ run.listings_priced }} avec une cote
          <template v-if="run.finished_at"> · {{ formatDateTime(run.finished_at) }}</template>
        </p>

        <div v-if="run.totals" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <StatTile
            icon="i-lucide-layers"
            label="Cartes"
            :value="`${run.totals.card_count} / ${run.request?.card_count ?? run.totals.card_count}`"
            :hint="`${formatYen(run.totals.purchase_jpy)} d’achats`"
          />
          <StatTile
            icon="i-lucide-wallet"
            label="Coût du colis"
            :value="formatCents(run.totals.landed_cents)"
            :hint="`Budget ${formatCents(budget)}, tout compris`"
          />
          <StatTile
            icon="i-lucide-euro"
            label="Revente attendue"
            :value="formatCents(run.totals.revenue_cents)"
            :hint="`Net ${formatCents(run.totals.net_cents)} après frais et cotisations`"
          />
          <StatTile
            icon="i-lucide-piggy-bank"
            label="Marge attendue"
            :value="formatCents(run.totals.margin_cents)"
            :value-class="signClass(run.totals.margin_cents)"
          />
          <StatTile
            icon="i-lucide-percent"
            label="ROI du colis"
            :value="formatRatio(run.totals.roi)"
            :value-class="signClass(run.totals.roi)"
          />
        </div>

        <UEmpty
          v-if="!run.picks.length"
          icon="i-lucide-search-x"
          title="Aucune carte ne remplit les conditions"
          description="Essayez un ROI minimum plus bas, un budget plus large ou moins de cartes. Les annonces changent vite : relancer dans quelques heures donne aussi d’autres résultats."
        />

        <section v-else class="space-y-3">
          <h2 class="font-medium text-highlighted">Le colis proposé</h2>
          <div class="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
            <DealCard
              v-for="pick in run.picks"
              :key="`${pick.source}-${pick.external_id}`"
              :title="pick.title"
              :subtitle="subtitle(pick)"
              :source="pick.source"
              :price-jpy="pick.price_jpy"
              :shipping-included="pick.shipping_included"
              :url="pick.url"
              :neokyo-url="pick.neokyo_url"
              :thumbnail-url="pick.thumbnail_url"
              :listed-at="pick.listed_at"
              :ends-at="pick.ends_at"
              :bids="pick.bids"
              :landed-cost="pick.landed_cost"
              :sale="pick.sale"
              :target-roi="targetRoi"
              :note="pick.warning ?? (pick.confidence === 'medium' ? pick.confidence_note : null)"
              :menu="menu(pick)"
              favoritable
              :favorite="!!favorites.find(pick.source, pick.external_id)"
              @toggle-favorite="favorites.toggle(toFavorite(pick))"
              @open="openPick(pick)"
            />
          </div>
        </section>

        <section v-if="run.alternatives.length" class="space-y-3">
          <h2 class="font-medium text-highlighted">Autres annonces rentables</h2>
          <p class="text-sm text-muted">
            Chiffrées comme une carte d’un colis de {{ run.request?.card_count }} : à prendre en
            plus ou à la place d’une carte du colis.
          </p>
          <div class="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
            <DealCard
              v-for="pick in run.alternatives"
              :key="`${pick.source}-${pick.external_id}`"
              :title="pick.title"
              :subtitle="subtitle(pick)"
              :source="pick.source"
              :price-jpy="pick.price_jpy"
              :shipping-included="pick.shipping_included"
              :url="pick.url"
              :neokyo-url="pick.neokyo_url"
              :thumbnail-url="pick.thumbnail_url"
              :listed-at="pick.listed_at"
              :ends-at="pick.ends_at"
              :bids="pick.bids"
              :landed-cost="pick.landed_cost"
              :sale="pick.sale"
              :target-roi="targetRoi"
              :note="pick.warning ?? (pick.confidence === 'medium' ? pick.confidence_note : null)"
              :menu="menu(pick)"
              favoritable
              :favorite="!!favorites.find(pick.source, pick.external_id)"
              @toggle-favorite="favorites.toggle(toFavorite(pick))"
              @open="openPick(pick)"
            />
          </div>
        </section>
      </template>

      <ItemFormModal v-model:open="buying" :initial="purchase" :lots="lots ?? []" />
    </template>
  </UDashboardPanel>
</template>
