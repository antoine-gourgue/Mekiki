<script setup lang="ts">
import type { DropdownMenuItem, TableColumn } from '@nuxt/ui'
import type { Game, Item, ItemStatus } from '~/types/engine'

const engine = useEngine()
const showError = useErrorToast()
const confirm = useConfirm()

const statusFilter = ref<ItemStatus | 'all'>('all')
const gameFilter = ref<Game | 'all'>('all')

const statusTabs = [
  { value: 'all', label: 'Tout' },
  ...selectItems(ITEM_STATUS_LABELS).filter((item) => item.value !== 'sold'),
  { value: 'sold', label: 'Vendues' },
]
const gameItems = [{ value: 'all', label: 'Tous les jeux' }, ...selectItems(GAME_LABELS)]

const query = computed(() => ({
  status: statusFilter.value === 'all' ? undefined : statusFilter.value,
  game: gameFilter.value === 'all' ? undefined : gameFilter.value,
}))

const {
  data: items,
  status,
  error,
  refresh,
} = useAsyncData('inventory', () => engine.inventory(query.value), { watch: [query] })
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

async function deleteItem(item: Item) {
  const confirmed = await confirm({
    title: `Supprimer « ${item.name} » ?`,
    description: item.sale ? 'Sa vente sera supprimée aussi.' : undefined,
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
        { label: 'Vendue', icon: 'i-lucide-badge-euro', onSelect: () => open(item, 'sale') },
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

const columns: TableColumn<Item>[] = [
  { accessorKey: 'name', header: 'Carte' },
  { accessorKey: 'status', header: 'Statut' },
  { id: 'landed', header: 'Coût de revient' },
  { id: 'price', header: 'Prix' },
  { id: 'margin', header: 'Marge' },
  { id: 'actions', header: '' },
]

const totals = computed(() => {
  const rows = items.value ?? []
  return {
    count: rows.length,
    cost: rows.reduce((sum, item) => sum + item.landed_cost.total_cents, 0),
  }
})
</script>

<template>
  <UDashboardPanel id="stock">
    <template #header>
      <UDashboardNavbar title="Stock">
        <template #leading><UDashboardSidebarCollapse /></template>
      </UDashboardNavbar>
      <UDashboardToolbar>
        <template #left>
          <UTabs v-model="statusFilter" :items="statusTabs" :content="false" size="sm" />
        </template>
        <template #right>
          <USelect v-model="gameFilter" :items="gameItems" class="w-40" />
        </template>
      </UDashboardToolbar>
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
        <p class="text-sm text-muted">
          {{ totals.count }} carte{{ totals.count > 1 ? 's' : '' }} · coût de revient
          {{ formatCents(totals.cost) }}
        </p>

        <UTable
          :data="items ?? []"
          :columns="columns"
          :loading="status === 'pending'"
          empty="Aucune carte ne correspond à ces filtres."
        >
          <template #name-cell="{ row }">
            <p class="font-medium text-highlighted">{{ row.original.name }}</p>
            <p class="text-xs text-muted">
              {{ GAME_LABELS[row.original.game] }}
              <template v-if="row.original.set_code"> · {{ row.original.set_code }}</template>
              <template v-if="row.original.card_number"> {{ row.original.card_number }}</template>
              · {{ row.original.lot_label }}
            </p>
          </template>
          <template #status-cell="{ row }">
            <UBadge
              :color="ITEM_STATUS_COLORS[row.original.status]"
              variant="subtle"
              :label="ITEM_STATUS_LABELS[row.original.status]"
            />
          </template>
          <template #landed-cell="{ row }">
            <UPopover mode="hover" :content="{ side: 'left' }">
              <span class="cursor-help tabular-nums underline decoration-dotted">
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
              <span class="block text-xs text-muted">
                {{ PLATFORM_LABELS[row.original.sale.platform] }} ·
                {{ formatDate(row.original.sale.sold_on) }}
              </span>
            </template>
            <template v-else-if="row.original.listing_platform">
              <span class="tabular-nums">
                {{ formatCents(row.original.listing_price_cents) }}
              </span>
              <span class="block text-xs text-muted">
                {{ PLATFORM_LABELS[row.original.listing_platform] }}
              </span>
            </template>
            <span v-else class="text-muted">—</span>
          </template>
          <template #margin-cell="{ row }">
            <UPopover v-if="outlook(row.original)" mode="hover" :content="{ side: 'left' }">
              <span
                class="cursor-help font-medium tabular-nums underline decoration-dotted"
                :class="signClass(outlook(row.original)!.margin_cents)"
              >
                {{ formatCents(outlook(row.original)!.margin_cents) }}
              </span>
              <span class="block text-xs text-muted">
                {{ row.original.sale ? 'réelle' : 'prévue' }} · ROI
                {{ formatRatio(outlook(row.original)!.roi) }}
              </span>
              <template #content>
                <div class="w-72 p-3">
                  <SaleBreakdownList :sale="outlook(row.original)!" />
                </div>
              </template>
            </UPopover>
            <span v-else class="text-muted">—</span>
          </template>
          <template #actions-cell="{ row }">
            <div class="flex justify-end gap-1">
              <UButton
                v-if="row.original.status === 'in_stock'"
                size="sm"
                color="neutral"
                variant="outline"
                label="Mettre en vente"
                @click="open(row.original, 'listing')"
              />
              <UButton
                v-else-if="row.original.status === 'listed'"
                size="sm"
                color="neutral"
                variant="outline"
                label="Vendue"
                @click="open(row.original, 'sale')"
              />
              <UDropdownMenu :items="actions(row.original)" :content="{ align: 'end' }">
                <UButton
                  icon="i-lucide-ellipsis-vertical"
                  color="neutral"
                  variant="ghost"
                  aria-label="Actions"
                />
              </UDropdownMenu>
            </div>
          </template>
        </UTable>
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
