<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { DashboardQuery, MonthlySales } from '~/types/engine'

const engine = useEngine()

type Period = '12m' | 'year' | 'last-year' | 'all'
const periodItems: { value: Period; label: string }[] = [
  { value: '12m', label: '12 derniers mois' },
  { value: 'year', label: 'Cette année' },
  { value: 'last-year', label: 'L’année dernière' },
  { value: 'all', label: 'Depuis le début' },
]
const period = ref<Period>('12m')

const range = computed<DashboardQuery>(() => {
  const now = new Date()
  const year = now.getFullYear()
  switch (period.value) {
    case '12m':
      return { since: toIsoDate(new Date(year, now.getMonth() - 11, 1)) }
    case 'year':
      return { since: `${year}-01-01` }
    case 'last-year':
      return { since: `${year - 1}-01-01`, until: `${year - 1}-12-31` }
    default:
      return {}
  }
})

const { data, status, error, refresh } = useAsyncData(
  'dashboard',
  () => engine.dashboard(range.value),
  { watch: [range] },
)

/** Months without sales are missing from the API; a time axis needs them as zeros. */
const months = computed<MonthlySales[]>(() => {
  const monthly = data.value?.monthly ?? []
  const first = range.value.since?.slice(0, 7) ?? monthly[0]?.month
  if (!first) return []
  const last = range.value.until?.slice(0, 7) ?? toIsoDate(new Date()).slice(0, 7)
  const byMonth = new Map(monthly.map((m) => [m.month, m]))
  const filled: MonthlySales[] = []
  let [year, month] = first.split('-').map(Number) as [number, number]
  for (let key = first; key <= last;) {
    filled.push(
      byMonth.get(key) ?? {
        month: key,
        sold_count: 0,
        revenue_cents: 0,
        net_cents: 0,
        margin_cents: 0,
      },
    )
    month += 1
    if (month > 12) [year, month] = [year + 1, 1]
    key = `${year}-${String(month).padStart(2, '0')}`
  }
  return filled
})

const columns: TableColumn<MonthlySales>[] = [
  { accessorKey: 'month', header: 'Mois' },
  { accessorKey: 'sold_count', header: 'Ventes' },
  { accessorKey: 'revenue_cents', header: 'CA' },
  { accessorKey: 'net_cents', header: 'Net' },
  { accessorKey: 'margin_cents', header: 'Marge' },
]
</script>

<template>
  <UDashboardPanel id="dashboard">
    <template #header>
      <UDashboardNavbar title="Tableau de bord">
        <template #leading><UDashboardSidebarCollapse /></template>
      </UDashboardNavbar>
      <UDashboardToolbar>
        <USelect v-model="period" :items="periodItems" class="w-48" />
      </UDashboardToolbar>
    </template>

    <template #body>
      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="Impossible de charger le tableau de bord"
        :description="engineErrorMessage(error)"
        :actions="[{ label: 'Réessayer', onClick: () => refresh() }]"
      />

      <div
        v-else-if="data"
        class="space-y-6 transition-opacity"
        :class="{ 'opacity-60': status === 'pending' }"
      >
        <section>
          <h2 class="mb-3 text-sm font-medium text-muted">Stock actuel</h2>
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <StatTile icon="i-lucide-plane" label="En route" :value="String(data.incoming_count)" />
            <StatTile icon="i-lucide-boxes" label="En stock" :value="String(data.in_stock_count)" />
            <StatTile
              icon="i-lucide-tag"
              label="En vente"
              :value="String(data.listed_count)"
              :hint="`Annonces : ${formatCents(data.listed_price_cents)}`"
            />
            <StatTile
              icon="i-lucide-vault"
              label="Valeur du stock"
              :value="formatCents(data.stock_cost_cents)"
              hint="Au coût de revient"
            />
            <StatTile
              icon="i-lucide-trending-up"
              label="Marge prévue"
              :value="formatCents(data.listed_expected_margin_cents)"
              :value-class="signClass(data.listed_expected_margin_cents)"
              hint="Si les annonces se vendent au prix affiché"
            />
          </div>
        </section>

        <section>
          <h2 class="mb-3 text-sm font-medium text-muted">Ventes sur la période</h2>
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <StatTile
              icon="i-lucide-shopping-bag"
              label="Ventes"
              :value="String(data.sold_count)"
            />
            <StatTile
              icon="i-lucide-euro"
              label="Chiffre d’affaires"
              :value="formatCents(data.revenue_cents)"
              hint="Port facturé compris"
            />
            <StatTile
              icon="i-lucide-wallet"
              label="Net"
              :value="formatCents(data.net_cents)"
              hint="Après frais, envoi et cotisations"
            />
            <StatTile
              icon="i-lucide-piggy-bank"
              label="Marge"
              :value="formatCents(data.margin_cents)"
              :value-class="signClass(data.margin_cents)"
              :hint="`Coût des cartes vendues : ${formatCents(data.cost_of_sold_cents)}`"
            />
            <StatTile
              icon="i-lucide-percent"
              label="ROI"
              :value="formatRatio(data.roi)"
              :value-class="signClass(data.roi)"
            />
          </div>
        </section>

        <UCard v-if="data.sold_count > 0">
          <template #header>
            <h2 class="font-medium text-highlighted">Marge par mois</h2>
          </template>
          <MonthlyMarginChart :months="months" />
          <UTable :data="[...months].reverse()" :columns="columns" class="mt-6">
            <template #month-cell="{ row }">{{ formatMonth(row.original.month) }}</template>
            <template #revenue_cents-cell="{ row }">
              <span class="tabular-nums">{{ formatCents(row.original.revenue_cents) }}</span>
            </template>
            <template #net_cents-cell="{ row }">
              <span class="tabular-nums">{{ formatCents(row.original.net_cents) }}</span>
            </template>
            <template #margin_cents-cell="{ row }">
              <span class="tabular-nums" :class="signClass(row.original.margin_cents)">
                {{ formatCents(row.original.margin_cents) }}
              </span>
            </template>
          </UTable>
        </UCard>

        <UEmpty
          v-else
          icon="i-lucide-chart-column"
          title="Aucune vente sur la période"
          description="Les ventes enregistrées depuis le stock apparaîtront ici."
          :actions="[{ label: 'Voir le stock', to: '/stock' }]"
        />
      </div>
    </template>
  </UDashboardPanel>
</template>
