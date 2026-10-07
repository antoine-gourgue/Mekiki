<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { Item, Sale } from '~/types/engine'

type SoldItem = Item & { sale: Sale }

const engine = useEngine()
const showError = useErrorToast()
const confirm = useConfirm()

const {
  data: items,
  status,
  error,
  refresh,
} = useAsyncData('sales', () => engine.inventory({ status: 'sold' }))

const sales = computed(() =>
  ((items.value ?? []) as SoldItem[]).toSorted((a, b) =>
    b.sale.sold_on.localeCompare(a.sale.sold_on),
  ),
)

const totals = computed(() => {
  const sum = (pick: (item: SoldItem) => number) =>
    sales.value.reduce((total, item) => total + pick(item), 0)
  const cost = sum((item) => item.landed_cost.total_cents)
  const margin = sum((item) => item.sale.breakdown.margin_cents)
  return {
    revenue: sum((item) => item.sale.breakdown.revenue_cents),
    net: sum((item) => item.sale.breakdown.net_cents),
    margin,
    roi: cost > 0 ? margin / cost : null,
  }
})

const selected = ref<Item | null>(null)
const editing = ref(false)

async function cancelSale(item: SoldItem) {
  const confirmed = await confirm({
    title: `Annuler la vente de « ${item.name} » ?`,
    description: 'La carte retourne dans le stock.',
    confirmLabel: 'Annuler la vente',
  })
  if (!confirmed) return
  try {
    await engine.cancelSale(item.id)
    await refresh()
  } catch (failure) {
    showError(failure)
  }
}

const columns: TableColumn<SoldItem>[] = [
  { id: 'sold_on', header: 'Date' },
  { accessorKey: 'name', header: 'Carte' },
  { id: 'revenue', header: 'CA' },
  { id: 'fees', header: 'Frais et cotisations' },
  { id: 'net', header: 'Net' },
  { id: 'cost', header: 'Coût de revient' },
  { id: 'margin', header: 'Marge' },
  { id: 'actions', header: '' },
]
</script>

<template>
  <UDashboardPanel id="sales">
    <template #header>
      <UDashboardNavbar title="Ventes">
        <template #leading><UDashboardSidebarCollapse /></template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="Impossible de charger les ventes"
        :description="engineErrorMessage(error)"
        :actions="[{ label: 'Réessayer', onClick: () => refresh() }]"
      />

      <template v-else>
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile label="Chiffre d’affaires" :value="formatCents(totals.revenue)" />
          <StatTile label="Net" :value="formatCents(totals.net)" />
          <StatTile
            label="Marge"
            :value="formatCents(totals.margin)"
            :value-class="signClass(totals.margin)"
          />
          <StatTile
            label="ROI"
            :value="formatRatio(totals.roi)"
            :value-class="signClass(totals.roi)"
          />
        </div>

        <UTable
          :data="sales"
          :columns="columns"
          :loading="status === 'pending'"
          empty="Aucune vente enregistrée. Marquez une carte comme vendue depuis le stock."
        >
          <template #sold_on-cell="{ row }">
            {{ formatDate(row.original.sale.sold_on) }}
            <span class="block text-xs text-muted">
              {{ PLATFORM_LABELS[row.original.sale.platform] }}
            </span>
          </template>
          <template #name-cell="{ row }">
            <p class="font-medium text-highlighted">{{ row.original.name }}</p>
            <p class="text-xs text-muted">{{ row.original.lot_label }}</p>
          </template>
          <template #revenue-cell="{ row }">
            <span class="tabular-nums">
              {{ formatCents(row.original.sale.breakdown.revenue_cents) }}
            </span>
          </template>
          <template #fees-cell="{ row }">
            <UPopover mode="hover" :content="{ side: 'left' }">
              <span class="cursor-help tabular-nums underline decoration-dotted">
                {{
                  formatCents(
                    row.original.sale.breakdown.revenue_cents -
                      row.original.sale.breakdown.net_cents,
                  )
                }}
              </span>
              <template #content>
                <div class="w-72 p-3">
                  <SaleBreakdownList :sale="row.original.sale.breakdown" />
                  <p class="mt-2 text-xs text-muted">
                    Cotisations figées à {{ row.original.sale.contribution_rate_percent }} % au
                    moment de la vente.
                  </p>
                </div>
              </template>
            </UPopover>
          </template>
          <template #net-cell="{ row }">
            <span class="tabular-nums">{{
              formatCents(row.original.sale.breakdown.net_cents)
            }}</span>
          </template>
          <template #cost-cell="{ row }">
            <span class="tabular-nums">{{
              formatCents(row.original.landed_cost.total_cents)
            }}</span>
          </template>
          <template #margin-cell="{ row }">
            <span
              class="font-medium tabular-nums"
              :class="signClass(row.original.sale.breakdown.margin_cents)"
            >
              {{ formatCents(row.original.sale.breakdown.margin_cents) }}
            </span>
            <span class="block text-xs text-muted">
              ROI {{ formatRatio(row.original.sale.breakdown.roi) }}
            </span>
          </template>
          <template #actions-cell="{ row }">
            <div class="flex justify-end gap-1">
              <UButton
                icon="i-lucide-pencil"
                color="neutral"
                variant="ghost"
                aria-label="Modifier la vente"
                @click="((selected = row.original), (editing = true))"
              />
              <UButton
                icon="i-lucide-undo-2"
                color="neutral"
                variant="ghost"
                aria-label="Annuler la vente"
                @click="cancelSale(row.original)"
              />
            </div>
          </template>
        </UTable>
      </template>

      <SaleModal v-model:open="editing" :item="selected" @saved="() => refresh()" />
    </template>
  </UDashboardPanel>
</template>
