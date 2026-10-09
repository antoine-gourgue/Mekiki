<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { Item, Sale, SalePlatform } from '~/types/engine'

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

// Each platform keeps its color whatever the others do; the legend names them.
const PLATFORM_SWATCHES: Record<SalePlatform, string> = {
  vinted: 'bg-vermilion-500',
  cardmarket: 'bg-ink-100',
  ebay: 'bg-ink-500',
  leboncoin: 'bg-ink-300',
  other: 'bg-ink-700',
}

const byPlatform = computed(() => {
  const totalsByPlatform = new Map<SalePlatform, { net: number; count: number }>()
  for (const item of sales.value) {
    const entry = totalsByPlatform.get(item.sale.platform) ?? { net: 0, count: 0 }
    entry.net += item.sale.breakdown.net_cents
    entry.count += 1
    totalsByPlatform.set(item.sale.platform, entry)
  }
  return [...totalsByPlatform]
    .map(([platform, entry]) => ({ platform, ...entry }))
    .sort((a, b) => b.net - a.net)
})

const RIGHT = { class: { th: 'text-right', td: 'text-right' } }
const columns: TableColumn<SoldItem>[] = [
  { accessorKey: 'name', header: 'Carte' },
  { id: 'sold_on', header: 'Vendue' },
  { id: 'revenue', header: 'Prix', meta: RIGHT },
  { id: 'fees', header: 'Frais et cotisations', meta: RIGHT },
  { id: 'net', header: 'Net', meta: RIGHT },
  { id: 'cost', header: 'Coût de revient', meta: RIGHT },
  { id: 'margin', header: 'Marge', meta: RIGHT },
  { id: 'actions', header: '' },
]
</script>

<template>
  <UDashboardPanel id="sales">
    <template #header>
      <PageNavbar
        title="Ventes"
        description="Frais et cotisations sont figés à la vente ; le coût de revient suit les factures."
      />
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
        <div class="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile
            label="Chiffre d’affaires"
            :value="formatCents(totals.revenue)"
            :hint="`${sales.length} vente${sales.length > 1 ? 's' : ''}`"
          />
          <StatTile
            label="Net"
            :value="formatCents(totals.net)"
            hint="après frais et cotisations"
          />
          <StatTile
            label="Marge"
            :value="formatSignedCents(totals.margin)"
            :value-class="signClass(totals.margin)"
            hint="net moins coût de revient"
          />
          <StatTile
            label="ROI"
            :value="formatRatio(totals.roi)"
            :value-class="signClass(totals.roi)"
            hint="marge rapportée au coût de revient"
          />
        </div>

        <UCard v-if="byPlatform.length" :ui="{ body: 'space-y-3.5 sm:p-5' }">
          <div class="flex items-baseline justify-between gap-3">
            <h2 class="font-semibold text-highlighted">Net par plateforme</h2>
            <span class="text-xs text-dimmed">{{ formatCents(totals.net) }} au total</span>
          </div>
          <div
            class="flex h-3.5 gap-0.5 overflow-hidden rounded"
            role="img"
            :aria-label="
              byPlatform
                .map((p) => `${PLATFORM_LABELS[p.platform]} ${formatCents(p.net)}`)
                .join(', ')
            "
          >
            <span
              v-for="entry in byPlatform.filter((p) => p.net > 0)"
              :key="entry.platform"
              :class="PLATFORM_SWATCHES[entry.platform]"
              :style="{ flex: `${entry.net} 1 0` }"
            />
          </div>
          <div class="flex flex-wrap gap-x-7 gap-y-2 text-sm">
            <span v-for="entry in byPlatform" :key="entry.platform" class="flex items-center gap-2">
              <span class="size-2.5 rounded-sm" :class="PLATFORM_SWATCHES[entry.platform]" />
              {{ PLATFORM_LABELS[entry.platform] }}
              <span class="text-muted tabular-nums">
                {{ formatCents(entry.net) }} · {{ entry.count }} vente{{
                  entry.count > 1 ? 's' : ''
                }}
              </span>
            </span>
          </div>
        </UCard>

        <UCard :ui="{ body: 'p-0 sm:p-0' }">
          <UTable
            :data="sales"
            :columns="columns"
            :loading="status === 'pending'"
            empty="Aucune vente enregistrée. Marquez une carte comme vendue depuis le stock."
          >
            <template #name-cell="{ row }">
              <p class="font-medium text-highlighted">{{ row.original.name }}</p>
              <p class="text-xs text-dimmed">
                {{ [row.original.card_number, row.original.lot_label].filter(Boolean).join(' · ') }}
              </p>
            </template>
            <template #sold_on-cell="{ row }">
              <p>{{ PLATFORM_LABELS[row.original.sale.platform] }}</p>
              <p class="text-xs text-dimmed">{{ formatDate(row.original.sale.sold_on) }}</p>
              <UBadge
                v-if="!row.original.sale.shipped_on"
                label="À expédier"
                color="warning"
                variant="soft"
                size="sm"
                class="mt-1"
              />
            </template>
            <template #revenue-cell="{ row }">
              <span class="tabular-nums">
                {{ formatCents(row.original.sale.breakdown.revenue_cents) }}
              </span>
            </template>
            <template #fees-cell="{ row }">
              <UPopover mode="hover" :content="{ side: 'left' }">
                <span
                  class="cursor-help text-muted tabular-nums underline decoration-dotted underline-offset-2"
                >
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
              <span class="tabular-nums">
                {{ formatCents(row.original.sale.breakdown.net_cents) }}
              </span>
            </template>
            <template #cost-cell="{ row }">
              <span class="text-muted tabular-nums">
                {{ formatCents(row.original.landed_cost.total_cents) }}
              </span>
            </template>
            <template #margin-cell="{ row }">
              <span
                class="font-medium tabular-nums"
                :class="signClass(row.original.sale.breakdown.margin_cents)"
              >
                {{ formatSignedCents(row.original.sale.breakdown.margin_cents) }}
              </span>
              <span class="block text-xs text-dimmed">
                ROI {{ formatRatio(row.original.sale.breakdown.roi) }}
              </span>
            </template>
            <template #actions-cell="{ row }">
              <div class="flex justify-end gap-1">
                <UButton
                  v-if="trackingFor(row.original.sale.tracking_number)"
                  icon="i-lucide-truck"
                  size="sm"
                  color="neutral"
                  variant="ghost"
                  :aria-label="`Suivre le colis sur ${trackingFor(row.original.sale.tracking_number)?.carrier}`"
                  @click="openExternal(trackingFor(row.original.sale.tracking_number)!.url)"
                />
                <UButton
                  icon="i-lucide-pencil"
                  size="sm"
                  color="neutral"
                  variant="ghost"
                  aria-label="Modifier la vente"
                  @click="((selected = row.original), (editing = true))"
                />
                <UButton
                  icon="i-lucide-undo-2"
                  size="sm"
                  color="neutral"
                  variant="ghost"
                  aria-label="Annuler la vente"
                  @click="cancelSale(row.original)"
                />
              </div>
            </template>
          </UTable>
        </UCard>
      </template>

      <SaleModal v-model:open="editing" :item="selected" @saved="() => refresh()" />
    </template>
  </UDashboardPanel>
</template>
