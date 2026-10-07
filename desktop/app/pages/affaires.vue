<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import type { Deal, ItemCreate, ListingTriage, ScanStatus, TrackedCard } from '~/types/engine'

const route = useRoute()
const router = useRouter()
const engine = useEngine()
const showError = useErrorToast()
const favorites = useFavorites()
const toast = useToast()

const cardFilter = computed<number | 'all'>({
  get: () => (route.query.carte ? Number(route.query.carte) : 'all'),
  set: (value) => router.replace({ query: value === 'all' ? {} : { carte: String(value) } }),
})
const goodOnly = ref(true)
const showDismissed = ref(false)

const { data: settings } = useAsyncData('settings', () => engine.getSettings())
const { data: cards } = useAsyncData('tracked-cards', () => engine.listTrackedCards())
const { data: lots } = useAsyncData('lots', () => engine.listLots())

const targetRoi = computed(() => (settings.value?.scanner.min_roi_percent ?? 30) / 100)

const query = computed(() => ({
  tracked_card_id: cardFilter.value === 'all' ? undefined : cardFilter.value,
  triage: showDismissed.value ? ('dismissed' as const) : undefined,
  min_roi_percent: goodOnly.value && !showDismissed.value ? targetRoi.value * 100 : undefined,
}))

const {
  data: deals,
  status,
  error,
  refresh,
} = useAsyncData('deals', () => engine.listDeals(query.value), { watch: [query] })

const cardItems = computed(() => [
  { value: 'all' as const, label: 'Toutes les cartes' },
  ...(cards.value ?? []).map((card) => ({ value: card.id, label: card.name })),
])
const cardsById = computed(() => new Map((cards.value ?? []).map((card) => [card.id, card])))

// Scan progress: polled quickly while a scan runs, then the deals are reloaded.
const scan = ref<ScanStatus | null>(null)
let scanTimer: ReturnType<typeof setTimeout> | undefined

async function pollScan() {
  clearTimeout(scanTimer)
  try {
    const wasRunning = scan.value?.running
    scan.value = await engine.scanStatus()
    if (wasRunning && !scan.value.running) {
      await refresh()
      toast.add({
        title: 'Scan terminé',
        description: `${scan.value.new_deals} nouvelle(s) bonne(s) affaire(s), ${scan.value.new_listings} annonce(s) au total.`,
        color: scan.value.last_error ? 'warning' : 'success',
      })
    }
  } catch {
    // The layout already reports an unreachable engine.
  }
  scanTimer = setTimeout(pollScan, scan.value?.running ? 2000 : 15000)
}
onMounted(pollScan)
onBeforeUnmount(() => clearTimeout(scanTimer))

async function runScan() {
  try {
    scan.value = await engine.runScan()
    void pollScan()
  } catch (failure) {
    showError(failure, 'Scan impossible')
  }
}

async function setTriage(deal: Deal, triage: ListingTriage) {
  try {
    const updated = await engine.updateDeal(deal.id, triage)
    deals.value = (deals.value ?? []).map((d) => (d.id === deal.id ? updated : d))
  } catch (failure) {
    showError(failure)
  }
}

async function markAllSeen() {
  try {
    await engine.markDealsSeen()
    await refresh()
  } catch (failure) {
    showError(failure)
  }
}

// "Bought" opens the card form pre-filled, to put it straight into a lot.
const buying = ref(false)
const purchase = ref<Partial<ItemCreate> | null>(null)

function bought(deal: Deal) {
  const card: TrackedCard | undefined = cardsById.value.get(deal.tracked_card_id)
  purchase.value = {
    game: card?.game ?? 'pokemon',
    name: deal.card_name,
    set_code: card?.set_code ?? null,
    card_number: card?.card_number ?? null,
    rarity: card?.rarity ?? null,
    grading: card?.grading ?? null,
    source_platform: deal.source,
    source_url: deal.url,
    price_jpy: deal.price_jpy,
    domestic_shipping_jpy: deal.shipping_included
      ? 0
      : (settings.value?.scanner.domestic_shipping_jpy ?? 0),
    cardmarket_product_id: card?.cardmarket_product_id ?? null,
  }
  buying.value = true
  void setTriage(deal, 'bought')
}

function toFavorite(deal: Deal) {
  return listingToFavorite(deal, {
    game: deal.game,
    card_label: deal.card_name,
    cardmarket_product_id: deal.cardmarket_product_id,
    target_price_cents: deal.target_price_cents,
  })
}

const showResale = useResaleModal()

function menu(deal: Deal): DropdownMenuItem[] {
  return [
    {
      label: 'Prix en Europe (eBay, Vinted)',
      icon: 'i-lucide-euro',
      onSelect: () =>
        showResale(
          deal.card_name,
          deal.cardmarket_product_id
            ? { product_id: deal.cardmarket_product_id, label: deal.card_name }
            : { q: deal.card_name },
        ),
    },
    {
      label: 'Acheté : ajouter au stock',
      icon: 'i-lucide-package-plus',
      onSelect: () => bought(deal),
    },
    deal.triage === 'dismissed'
      ? { label: 'Rétablir', icon: 'i-lucide-undo-2', onSelect: () => setTriage(deal, 'seen') }
      : {
          label: 'Ignorer',
          icon: 'i-lucide-eye-off',
          onSelect: () => setTriage(deal, 'dismissed'),
        },
  ]
}

const newCount = computed(() => (deals.value ?? []).filter((d) => d.triage === 'new').length)
</script>

<template>
  <UDashboardPanel id="deals">
    <template #header>
      <UDashboardNavbar title="Bonnes affaires">
        <template #leading><UDashboardSidebarCollapse /></template>
        <template #right>
          <span v-if="scan" class="hidden text-xs text-muted md:inline">
            <template v-if="scan.running">Scan en cours…</template>
            <template v-else-if="scan.last_finished_at">
              Dernier scan {{ formatDateTime(scan.last_finished_at) }}
            </template>
            <template v-if="scan.enabled && scan.next_run_at && !scan.running">
              · prochain {{ formatDateTime(scan.next_run_at) }}
            </template>
          </span>
          <UButton
            icon="i-lucide-radar"
            label="Scanner maintenant"
            :loading="scan?.running"
            :disabled="!cards?.length"
            @click="runScan"
          />
        </template>
      </UDashboardNavbar>
      <UDashboardToolbar>
        <template #left>
          <USelect v-model="cardFilter" :items="cardItems" class="w-56" />
          <USwitch
            v-model="goodOnly"
            :disabled="showDismissed"
            :label="`ROI ≥ ${Math.round(targetRoi * 100)} %`"
          />
          <USwitch v-model="showDismissed" label="Ignorées" />
        </template>
        <template #right>
          <UButton
            v-if="newCount"
            color="neutral"
            variant="ghost"
            size="sm"
            :label="`Tout marquer comme vu (${newCount})`"
            @click="markAllSeen"
          />
        </template>
      </UDashboardToolbar>
    </template>

    <template #body>
      <UAlert
        v-if="scan?.last_error"
        color="warning"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Le dernier scan a rencontré un problème"
        :description="scan.last_error"
      />
      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="Impossible de charger les affaires"
        :description="engineErrorMessage(error)"
        :actions="[{ label: 'Réessayer', onClick: () => refresh() }]"
      />

      <UEmpty
        v-else-if="cards && !cards.length"
        icon="i-lucide-eye"
        title="Aucune carte suivie"
        description="Choisissez les cartes à surveiller : le scanner les cherche sur Mercari et Yahoo et calcule la marge de chaque annonce."
        :actions="[{ label: 'Suivre des cartes', to: '/suivi' }]"
      />

      <UEmpty
        v-else-if="deals && !deals.length && status !== 'pending'"
        icon="i-lucide-radar"
        :title="goodOnly ? 'Aucune bonne affaire pour l’instant' : 'Aucune annonce'"
        :description="
          goodOnly
            ? 'Aucune annonce n’atteint le ROI visé. Désactivez le filtre pour voir toutes les annonces trouvées.'
            : 'Lancez un scan pour chercher les cartes suivies.'
        "
      />

      <div
        v-else
        class="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3"
        :class="{ 'opacity-60': status === 'pending' }"
      >
        <DealCard
          v-for="deal in deals ?? []"
          :key="deal.id"
          :title="deal.title"
          :subtitle="deal.card_name"
          :source="deal.source"
          :price-jpy="deal.price_jpy"
          :shipping-included="deal.shipping_included"
          :url="deal.url"
          :neokyo-url="deal.neokyo_url"
          :thumbnail-url="deal.thumbnail_url"
          :listed-at="deal.listed_at"
          :ends-at="deal.ends_at"
          :bids="deal.bids"
          :landed-cost="deal.landed_cost"
          :sale="deal.sale"
          :target-roi="targetRoi"
          :is-new="deal.triage === 'new'"
          :offline="!deal.online"
          :muted="deal.triage === 'dismissed' || deal.triage === 'bought'"
          :menu="menu(deal)"
          favoritable
          :favorite="!!favorites.find(deal.source, deal.external_id)"
          @toggle-favorite="favorites.toggle(toFavorite(deal))"
        />
      </div>

      <ItemFormModal v-model:open="buying" :initial="purchase" :lots="lots ?? []" />
    </template>
  </UDashboardPanel>
</template>
