<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import type {
  DiscoveryDepth,
  DiscoveryPick,
  DiscoveryRun,
  Game,
  ItemCreate,
  ListingCondition,
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
  min_condition: 'all' as ListingCondition | 'all',
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
    min_condition: request.min_condition ?? 'all',
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

const alternatives = useListingFilter(() => run.value?.alternatives ?? [])

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
      min_condition: form.min_condition === 'all' ? null : form.min_condition,
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
    { label: 'Faut-il l’acheter ?', icon: 'i-lucide-scale', onSelect: () => openPick(pick) },
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
  return [pick.card_label, pick.product.expansion_name].filter(Boolean).join(' · ')
}

const gameItems = selectItems(GAME_LABELS)
</script>

<template>
  <UDashboardPanel id="discovery">
    <template #header>
      <PageNavbar
        title="Trouver des cartes"
        description="Mekiki parcourt Mercari et Rakuma, reconnaît chaque carte, la compare à sa cote et compose le colis le plus rentable qui tient dans le budget."
      />
    </template>

    <template #body>
      <UCard :ui="{ body: 'sm:p-5' }">
        <form class="space-y-5" @submit.prevent="start">
          <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
            <UFormField label="Jeu">
              <SegmentedControl
                v-model="form.game"
                :items="gameItems"
                label="Jeu"
                class="flex w-full *:flex-1"
              />
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
            <UFormField
              label="État minimum"
              :hint="form.min_condition === 'all' ? undefined : 'sans Rakuma'"
              :help="
                form.min_condition === 'new' || form.min_condition === 'like_new'
                  ? 'Écarte environ 6 annonces Mercari sur 10 : la plupart des cartes parfaites y sont en « Bon état ».'
                  : undefined
              "
            >
              <USelect v-model="form.min_condition" :items="MIN_CONDITION_ITEMS" class="w-full" />
            </UFormField>
          </div>

          <div class="flex flex-wrap gap-4">
            <UFormField label="Profondeur" class="min-w-0 flex-[3_1_520px]">
              <URadioGroup
                v-model="form.depth"
                :items="depthItems"
                variant="card"
                orientation="horizontal"
                :ui="{
                  fieldset: 'grid gap-2.5 sm:grid-cols-3',
                  item: 'bg-default',
                  description: 'text-xs',
                }"
              />
            </UFormField>
            <UFormField label="Sites" class="min-w-0 flex-[1_1_240px]">
              <UCheckboxGroup
                v-model="form.sources"
                :items="SCANNABLE_SOURCE_ITEMS"
                variant="card"
                orientation="horizontal"
                :ui="{
                  fieldset: 'flex flex-wrap gap-2',
                  item: 'bg-default py-2.5',
                  description: 'text-xs',
                }"
              />
            </UFormField>
          </div>

          <div
            class="flex flex-wrap items-center justify-between gap-3 border-t border-default pt-4"
          >
            <p class="text-sm text-dimmed">
              Les cartes du colis sont vérifiées sur leur site avant d’être proposées : les bonnes
              affaires partent en quelques minutes.
            </p>
            <UButton
              type="submit"
              icon="i-lucide-wand-sparkles"
              label="Trouver des cartes"
              size="xl"
              :loading="running"
              :disabled="!form.budget_cents || !form.card_count || !form.sources.length"
            />
          </div>
        </form>
      </UCard>

      <UCard v-if="running && run" :ui="{ body: 'sm:p-5' }">
        <div class="space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-3 text-sm">
            <template v-if="run.verifying">
              <span class="font-medium text-highlighted">
                Vérification des annonces du colis sur leur site…
              </span>
              <span class="text-muted tabular-nums">
                {{ run.listings_checked }} vérifiée{{ run.listings_checked > 1 ? 's' : '' }} ·
                {{ run.listings_gone }} déjà vendue{{ run.listings_gone > 1 ? 's' : '' }}
              </span>
            </template>
            <template v-else>
              <span class="font-medium text-highlighted">Recherche en cours…</span>
              <span class="text-muted tabular-nums">
                {{ run.searches_done }} / {{ run.searches_total }} recherches ·
                {{ run.listings_seen.toLocaleString('fr-FR') }} annonces
              </span>
            </template>
          </div>
          <UProgress :model-value="progress" />
          <ActivityLog
            :lines="run.log ?? []"
            active
            title="Journal de la recherche"
            placeholder="Préparation de la recherche…"
            height="max-h-72"
          />
          <div class="flex justify-end">
            <UButton
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
        description="L’app cherche sur Mercari et Rakuma, reconnaît chaque carte, la compare à sa cote Cardmarket et compose le colis le plus rentable qui tient dans le budget."
      />

      <template v-else-if="run.status === 'done' || run.status === 'failed'">
        <div>
          <h2 class="text-lg font-semibold text-highlighted">
            Colis proposé
            <template v-if="run.totals">
              · {{ run.totals.card_count }} carte{{ run.totals.card_count > 1 ? 's' : '' }}
            </template>
          </h2>
          <p class="mt-1 text-sm text-dimmed">
            <UBadge
              v-if="run.stopped"
              color="neutral"
              variant="outline"
              label="Recherche arrêtée"
              class="me-1"
            />
            {{ run.listings_seen.toLocaleString('fr-FR') }} annonces lues ·
            {{ run.listings_identified }} cartes reconnues · {{ run.listings_priced }} avec une cote
            <template v-if="run.listings_checked">
              · {{ run.listings_checked }} vérifiées sur leur site<template v-if="run.listings_gone"
                >, {{ run.listings_gone }} déjà vendue{{
                  run.listings_gone > 1 ? 's' : ''
                }}
                remplacée{{ run.listings_gone > 1 ? 's' : '' }}</template
              >
            </template>
            <template v-if="run.finished_at"> · {{ formatDateTime(run.finished_at) }}</template>
          </p>
          <UCollapsible v-if="run.log?.length" class="mt-2">
            <UButton
              color="neutral"
              variant="link"
              size="sm"
              icon="i-lucide-scroll-text"
              trailing-icon="i-lucide-chevron-down"
              :label="`Journal de la recherche (${run.log.length} étapes)`"
              class="-ms-2.5 group"
              :ui="{
                trailingIcon:
                  'transition-transform duration-200 group-data-[state=open]:rotate-180',
              }"
            />
            <template #content>
              <ActivityLog
                :lines="run.log"
                title="Chaque étape, de la première recherche au colis"
                height="max-h-96"
                class="mt-2"
              />
            </template>
          </UCollapsible>
        </div>

        <div v-if="run.totals" class="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile
            label="Coût du colis"
            :value="formatCents(run.totals.landed_cents)"
            :hint="`budget ${formatCents(budget)} · ${formatYen(run.totals.purchase_jpy)} d’achats`"
          />
          <StatTile
            label="Revente attendue"
            :value="formatCents(run.totals.revenue_cents)"
            :hint="`net ${formatCents(run.totals.net_cents)} après frais et cotisations`"
          />
          <StatTile
            label="Marge attendue"
            :value="formatSignedCents(run.totals.margin_cents)"
            :value-class="signClass(run.totals.margin_cents)"
          />
          <StatTile
            label="ROI du colis"
            :value="formatRatio(run.totals.roi)"
            :value-class="signClass(run.totals.roi)"
            :hint="`minimum demandé ${formatRatio(targetRoi)}`"
          />
        </div>

        <UEmpty
          v-if="!run.picks.length"
          icon="i-lucide-search-x"
          title="Aucune carte ne remplit les conditions"
          description="Essayez un ROI minimum plus bas, un budget plus large ou moins de cartes. Les annonces changent vite : relancer dans quelques heures donne aussi d’autres résultats."
        />

        <div v-else class="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          <DealCard
            v-for="pick in run.picks"
            :key="`${pick.source}-${pick.external_id}`"
            layout="tile"
            :title="pick.title"
            :heading="pick.product.name"
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
            :condition="pick.condition"
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

        <section v-if="run.alternatives.length" class="space-y-3">
          <div>
            <h2 class="text-lg font-semibold text-highlighted">Autres annonces rentables</h2>
            <p class="mt-1 text-sm text-dimmed">
              Chiffrées comme une carte d’un colis de {{ run.request?.card_count }} : à prendre en
              plus ou à la place d’une carte du colis. Non vérifiées : leur fiche dit si elles sont
              toujours en vente.
            </p>
          </div>
          <ListingFilterBar
            v-model:min-condition="alternatives.minCondition.value"
            v-model:sort-by="alternatives.sortBy.value"
            :hidden="alternatives.hidden.value"
            :hidden-without-condition="alternatives.hiddenWithoutCondition.value"
          />
          <div class="space-y-2.5">
            <DealCard
              v-for="pick in alternatives.visible.value"
              :key="`${pick.source}-${pick.external_id}`"
              :title="pick.title"
              :heading="pick.product.name"
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
              :condition="pick.condition"
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
