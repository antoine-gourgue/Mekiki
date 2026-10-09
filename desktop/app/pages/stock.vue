<script setup lang="ts">
import type { DropdownMenuItem, TableColumn } from '@nuxt/ui'
import type { Game, Item, ItemStatus } from '~/types/engine'

const engine = useEngine()
const showError = useErrorToast()
const confirm = useConfirm()

const statusFilter = ref<ItemStatus | 'all'>('all')
const gameFilter = ref<Game | 'all'>('all')

const term = ref('')
const gameItems = [{ value: 'all', label: 'Tous les jeux' }, ...selectItems(GAME_LABELS)]

const query = computed(() => ({
  game: gameFilter.value === 'all' ? undefined : gameFilter.value,
}))

// The whole stock is loaded once: filtering it here gives the count of every status.
const {
  data: all,
  status,
  error,
  refresh,
} = useAsyncData('inventory', () => engine.inventory(query.value), { watch: [query] })

const statusTabs = computed(() => {
  const rows = all.value ?? []
  const count = (value: ItemStatus) => rows.filter((item) => item.status === value).length
  return [
    { value: 'all' as const, label: 'Toutes', count: rows.length },
    ...selectItems(ITEM_STATUS_LABELS)
      .filter((item) => item.value !== 'sold')
      .map((item) => ({ ...item, count: count(item.value) })),
    { value: 'sold' as const, label: 'Vendues', count: count('sold') },
  ]
})

const items = computed(() => {
  const needle = term.value.trim().toLowerCase()
  return (all.value ?? []).filter(
    (item) =>
      (statusFilter.value === 'all' || item.status === statusFilter.value) &&
      (!needle ||
        [item.name, item.card_number, item.set_code, item.lot_label]
          .filter(Boolean)
          .some((text) => text!.toLowerCase().includes(needle))),
  )
})
const { data: lots } = useAsyncData('lots', () => engine.listLots())

const selected = ref<Item | null>(null)
const listingOpen = ref(false)
const saleOpen = ref(false)
const editOpen = ref(false)

function open(item: Item, modal: 'listing' | 'sale' | 'edit') {
  selected.value = item
  listingOpen.value = modal === 'listing'
  saleOpen.value = modal === 'sale'
  editOpen.value = modal === 'edit'
}

/** "SV2A 201/165 · SAR" */
function cardLine(item: Item) {
  const number = [item.set_code?.toUpperCase(), item.card_number].filter(Boolean).join(' ')
  return [number, item.rarity].filter(Boolean).join(' · ') || GAME_LABELS[item.game]
}

// The side panel walks through the cards in the order shown.
const drawer = useDrawer()
function showItem(item: Item) {
  drawer.open({ kind: 'item', id: item.id, siblings: (items.value ?? []).map((row) => row.id) })
}

async function deleteItem(item: Item) {
  const confirmed = await confirm({
    title: `Supprimer « ${item.name} » ?`,
    // A sold card stays in the books: the engine refuses until its sale is cancelled.
    description: item.sale
      ? 'Elle est vendue : annulez d’abord sa vente, qui reste sinon dans la comptabilité.'
      : undefined,
  })
  if (!confirmed) return
  try {
    await engine.deleteItem(item.id)
    await refresh()
  } catch (failure) {
    showError(failure)
  }
}

function actions(item: Item): DropdownMenuItem[][] {
  const selling: DropdownMenuItem[] = item.sale
    ? [{ label: 'Modifier la vente', icon: 'i-lucide-receipt', onSelect: () => open(item, 'sale') }]
    : [
        {
          label: item.listing_platform ? 'Modifier l’annonce' : 'Mettre en vente',
          icon: 'i-lucide-tag',
          onSelect: () => open(item, 'listing'),
        },
        {
          label: 'Enregistrer la vente',
          icon: 'i-lucide-badge-euro',
          onSelect: () => open(item, 'sale'),
        },
      ]
  return [
    selling,
    [
      { label: 'Modifier la carte', icon: 'i-lucide-pencil', onSelect: () => open(item, 'edit') },
      { label: 'Voir le lot', icon: 'i-lucide-package', to: `/lots/${item.lot_id}` },
      {
        label: 'Supprimer',
        icon: 'i-lucide-trash-2',
        color: 'error',
        onSelect: () => deleteItem(item),
      },
    ],
  ]
}

/** The margin that matters for a card: its sale if sold, else its listing's projection. */
function outlook(item: Item) {
  return item.sale?.breakdown ?? item.listing_projection
}

const RIGHT = { class: { th: 'text-right', td: 'text-right' } }
const columns: TableColumn<Item>[] = [
  { accessorKey: 'name', header: 'Carte' },
  { accessorKey: 'lot_label', header: 'Lot' },
  { id: 'landed', header: 'Coût de revient', meta: RIGHT },
  { id: 'price', header: 'Prix', meta: RIGHT },
  { id: 'margin', header: 'Marge', meta: RIGHT },
  { accessorKey: 'status', header: 'Statut' },
  { id: 'actions', header: '' },
]

const totals = computed(() => {
  const rows = (all.value ?? []).filter((item) => item.status !== 'sold')
  return {
    count: rows.length,
    cost: rows.reduce((sum, item) => sum + item.landed_cost.total_cents, 0),
  }
})
</script>

<template>
  <UDashboardPanel id="stock">
    <template #header>
      <PageNavbar
        title="Stock"
        :description="`${totals.count} carte${totals.count > 1 ? 's' : ''} non vendue${totals.count > 1 ? 's' : ''} · ${formatCents(totals.cost)} au coût de revient`"
      >
        <template #right>
          <UInput
            v-model="term"
            icon="i-lucide-search"
            placeholder="Filtrer par nom ou numéro"
            aria-label="Filtrer le stock"
            class="w-64"
          />
          <USelect v-model="gameFilter" :items="gameItems" aria-label="Jeu" class="w-40" />
        </template>
      </PageNavbar>
    </template>

    <template #body>
      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="Impossible de charger le stock"
        :description="engineErrorMessage(error)"
        :actions="[{ label: 'Réessayer', onClick: () => refresh() }]"
      />

      <template v-else>
        <SegmentedControl
          v-model="statusFilter"
          :items="statusTabs"
          label="Statut des cartes"
          class="self-start"
        />

        <UCard :ui="{ body: 'p-0 sm:p-0' }">
          <UTable
            :data="items"
            :columns="columns"
            :loading="status === 'pending'"
            empty="Aucune carte ne correspond à ces filtres."
            :ui="{ tr: 'cursor-pointer' }"
            @select="(_event, row) => showItem(row.original)"
          >
            <template #name-cell="{ row }">
              <p class="font-medium text-highlighted">{{ row.original.name }}</p>
              <p class="text-xs text-dimmed">{{ cardLine(row.original) }}</p>
            </template>
            <template #lot_label-cell="{ row }">
              <span class="text-muted">{{ row.original.lot_label }}</span>
            </template>
            <template #status-cell="{ row }">
              <UBadge
                :color="ITEM_STATUS_COLORS[row.original.status]"
                variant="soft"
                :label="
                  row.original.status === 'listed' && row.original.listing_platform
                    ? `En vente · ${PLATFORM_LABELS[row.original.listing_platform]}`
                    : ITEM_STATUS_LABELS[row.original.status]
                "
              />
            </template>
            <template #landed-cell="{ row }">
              <UPopover mode="hover" :content="{ side: 'left' }">
                <span
                  class="cursor-help tabular-nums underline decoration-dotted underline-offset-2"
                >
                  {{ formatCents(row.original.landed_cost.total_cents) }}
                </span>
                <template #content>
                  <div class="w-72 p-3">
                    <LandedCostBreakdown :cost="row.original.landed_cost" />
                  </div>
                </template>
              </UPopover>
            </template>
            <template #price-cell="{ row }">
              <template v-if="row.original.sale">
                <span class="tabular-nums">{{
                  formatCents(row.original.sale.sale_price_cents)
                }}</span>
                <span class="block text-xs text-dimmed">
                  {{ PLATFORM_LABELS[row.original.sale.platform] }} ·
                  {{ formatDate(row.original.sale.sold_on) }}
                </span>
              </template>
              <template v-else-if="row.original.listing_platform">
                <span class="tabular-nums">{{
                  formatCents(row.original.listing_price_cents)
                }}</span>
                <span class="block text-xs text-dimmed">
                  {{ PLATFORM_LABELS[row.original.listing_platform] }}
                </span>
              </template>
              <span v-else class="text-dimmed">—</span>
            </template>
            <template #margin-cell="{ row }">
              <UPopover v-if="outlook(row.original)" mode="hover" :content="{ side: 'left' }">
                <span
                  class="cursor-help font-medium tabular-nums underline decoration-dotted underline-offset-2"
                  :class="signClass(outlook(row.original)!.margin_cents)"
                >
                  {{ formatSignedCents(outlook(row.original)!.margin_cents) }}
                </span>
                <span class="block text-xs text-dimmed">
                  {{ row.original.sale ? 'réelle' : 'prévue' }} · ROI
                  {{ formatRatio(outlook(row.original)!.roi) }}
                </span>
                <template #content>
                  <div class="w-72 p-3">
                    <SaleBreakdownList :sale="outlook(row.original)!" />
                  </div>
                </template>
              </UPopover>
              <span v-else class="text-dimmed">—</span>
            </template>
            <template #actions-cell="{ row }">
              <div class="flex justify-end gap-1" @click.stop>
                <UButton
                  v-if="row.original.status === 'in_stock'"
                  size="sm"
                  variant="soft"
                  label="Mettre en vente"
                  @click="open(row.original, 'listing')"
                />
                <UButton
                  v-else-if="row.original.status === 'listed'"
                  size="sm"
                  color="neutral"
                  variant="outline"
                  label="Marquer vendue"
                  @click="open(row.original, 'sale')"
                />
                <UDropdownMenu :items="actions(row.original)" :content="{ align: 'end' }">
                  <UButton
                    icon="i-lucide-ellipsis"
                    size="sm"
                    color="neutral"
                    variant="ghost"
                    aria-label="Actions"
                  />
                </UDropdownMenu>
              </div>
            </template>
          </UTable>
        </UCard>
      </template>

      <ListingModal
        v-model:open="listingOpen"
        :item="selected"
        @saved="() => refresh()"
        @photos-changed="() => refresh()"
      />
      <SaleModal v-model:open="saleOpen" :item="selected" @saved="() => refresh()" />
      <ItemFormModal
        v-model:open="editOpen"
        :item="selected"
        :lots="lots ?? []"
        @saved="() => refresh()"
      />
    </template>
  </UDashboardPanel>
</template>
