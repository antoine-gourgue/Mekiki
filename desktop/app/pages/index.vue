<script setup lang="ts">
import type { DashboardQuery, Item, MonthlySales } from '~/types/engine'

const engine = useEngine()

type Period = '12m' | 'year' | 'last-year' | 'all'
const periodItems: { value: Period; label: string }[] = [
  { value: '12m', label: '12 mois' },
  { value: 'year', label: 'Cette année' },
  { value: 'last-year', label: 'L’an dernier' },
  { value: 'all', label: 'Tout' },
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

// The lists under the figures; each one is optional, so a failure only empties it.
const { data: side } = useAsyncData('dashboard-side', async () => {
  const [items, lots, scan] = await Promise.allSettled([
    engine.inventory(),
    engine.listLots(),
    engine.scanStatus(),
  ])
  return {
    items: items.status === 'fulfilled' ? items.value : [],
    lots: lots.status === 'fulfilled' ? lots.value : [],
    unseenDeals: scan.status === 'fulfilled' ? scan.value.unseen_deals : 0,
  }
})

const today = new Intl.DateTimeFormat('fr-FR', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
}).format(new Date())

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

const RECENT_SALES = 5
const recentSales = computed(() =>
  (side.value?.items ?? [])
    .filter((item): item is Item & { sale: NonNullable<Item['sale']> } => item.sale !== null)
    .sort((a, b) => b.sale.sold_on.localeCompare(a.sale.sold_on))
    .slice(0, RECENT_SALES),
)

const stockSegments = computed(() => {
  const d = data.value
  if (!d) return []
  return [
    { label: 'En route', count: d.incoming_count, class: 'bg-ink-500' },
    { label: 'En stock', count: d.in_stock_count, class: 'bg-ink-100' },
    { label: 'En vente', count: d.listed_count, class: 'bg-vermilion-500' },
  ]
})
const stockTotal = computed(() => stockSegments.value.reduce((sum, s) => sum + s.count, 0))

interface Todo {
  label: string
  hint: string
  to: string
  icon: string
  tone: 'primary' | 'neutral' | 'error'
}
const todos = computed<Todo[]>(() => {
  const list: Todo[] = []
  const deals = side.value?.unseenDeals ?? 0
  if (deals) {
    list.push({
      label: `${deals} bonne${deals > 1 ? 's' : ''} affaire${deals > 1 ? 's' : ''} à regarder`,
      hint: 'trouvées par le scanner des cartes suivies',
      to: '/affaires',
      icon: 'i-lucide-tag',
      tone: 'primary',
    })
  }
  const toList = (side.value?.items ?? []).filter((item) => item.status === 'in_stock').length
  if (toList) {
    list.push({
      label: `${toList} carte${toList > 1 ? 's' : ''} à mettre en vente`,
      hint: 'en stock, sans annonce',
      to: '/stock',
      icon: 'i-lucide-upload',
      tone: 'neutral',
    })
  }
  for (const lot of side.value?.lots ?? []) {
    if (lot.status !== 'received' || !lot.vat_estimated) continue
    list.push({
      label: `${lot.label} : TVA à saisir`,
      hint: 'la marge des cartes vendues sera corrigée',
      to: `/lots/${lot.id}`,
      icon: 'i-lucide-receipt',
      tone: 'error',
    })
  }
  return list
})

const TONE_CLASSES: Record<Todo['tone'], string> = {
  primary: 'bg-primary/15 text-primary',
  neutral: 'bg-accented text-highlighted',
  error: 'bg-error/15 text-error',
}
</script>

<template>
  <UDashboardPanel id="dashboard">
    <template #header>
      <PageNavbar
        title="Tableau de bord"
        :description="today.charAt(0).toUpperCase() + today.slice(1)"
      >
        <template #right>
          <SegmentedControl v-model="period" :items="periodItems" label="Période" />
          <UButton icon="i-lucide-plus" label="Nouveau lot" to="/lots?nouveau=1" />
        </template>
      </PageNavbar>
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
        class="space-y-4 transition-opacity"
        :class="{ 'opacity-60': status === 'pending' }"
      >
        <div class="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile
            label="Chiffre d’affaires"
            :value="formatCents(data.revenue_cents)"
            :hint="`${data.sold_count} vente${data.sold_count > 1 ? 's' : ''}, port facturé compris`"
          />
          <StatTile
            label="Net"
            :value="formatCents(data.net_cents)"
            hint="après frais, envoi et cotisations"
          />
          <StatTile
            label="Marge"
            :value="formatSignedCents(data.margin_cents)"
            :value-class="signClass(data.margin_cents)"
            :hint="`coût des cartes vendues : ${formatCents(data.cost_of_sold_cents)}`"
          />
          <StatTile
            label="ROI"
            :value="formatRatio(data.roi)"
            :value-class="signClass(data.roi)"
            hint="marge rapportée au coût de revient"
          />
        </div>

        <div class="flex flex-wrap gap-3.5">
          <UCard class="min-w-0 flex-[2_1_520px]" :ui="{ body: 'sm:p-5' }">
            <div class="mb-3 flex items-baseline justify-between gap-3">
              <h2 class="font-semibold text-highlighted">Marge par mois</h2>
              <span class="text-xs text-dimmed">survolez une colonne pour le détail</span>
            </div>
            <MonthlyMarginChart v-if="data.sold_count > 0" :months="months" />
            <UEmpty
              v-else
              icon="i-lucide-chart-column"
              title="Aucune vente sur la période"
              description="Les ventes enregistrées depuis le stock apparaîtront ici."
              :actions="[
                { label: 'Voir le stock', to: '/stock', color: 'neutral', variant: 'outline' },
              ]"
              class="py-10"
            />
          </UCard>

          <UCard
            class="min-w-0 flex-[1_1_300px]"
            :ui="{ body: 'flex h-full flex-col gap-4 sm:p-5' }"
          >
            <div class="flex items-baseline justify-between gap-3">
              <h2 class="font-semibold text-highlighted">Stock</h2>
              <ULink to="/stock" class="text-sm text-primary">Voir le stock</ULink>
            </div>
            <div>
              <p class="text-sm text-muted">Valeur au coût de revient</p>
              <p class="mt-1 text-2xl font-semibold tracking-tight text-highlighted tabular-nums">
                {{ formatCents(data.stock_cost_cents) }}
              </p>
            </div>
            <div v-if="stockTotal" class="flex h-2.5 gap-0.5 overflow-hidden rounded">
              <span
                v-for="segment in stockSegments.filter((s) => s.count)"
                :key="segment.label"
                :class="segment.class"
                :style="{ flex: `${segment.count} 1 0` }"
              />
            </div>
            <ul class="space-y-2.5 text-sm">
              <li
                v-for="segment in stockSegments"
                :key="segment.label"
                class="flex items-center gap-2.5"
              >
                <span class="size-2.5 rounded-sm" :class="segment.class" />
                <span class="flex-1 text-muted">{{ segment.label }}</span>
                <span class="tabular-nums">
                  {{ segment.count }} carte{{ segment.count > 1 ? 's' : '' }}
                </span>
              </li>
            </ul>
            <div class="mt-auto flex justify-between border-t border-default pt-3.5 text-sm">
              <span class="text-muted">Marge prévue des annonces</span>
              <span
                class="font-semibold tabular-nums"
                :class="signClass(data.listed_expected_margin_cents)"
              >
                {{ formatSignedCents(data.listed_expected_margin_cents) }}
              </span>
            </div>
          </UCard>
        </div>

        <div class="flex flex-wrap gap-3.5">
          <UCard class="min-w-0 flex-[2_1_520px]" :ui="{ body: 'p-0 sm:p-0' }">
            <div class="flex items-baseline justify-between px-5 pt-4 pb-2">
              <h2 class="font-semibold text-highlighted">Dernières ventes</h2>
              <ULink to="/ventes" class="text-sm text-primary">Toutes les ventes</ULink>
            </div>
            <div class="overflow-x-auto">
              <table v-if="recentSales.length" class="w-full min-w-[480px] text-sm">
                <thead>
                  <tr class="text-left text-xs text-dimmed">
                    <th class="px-5 py-2 font-medium">Carte</th>
                    <th class="px-3 py-2 font-medium">Vendue sur</th>
                    <th class="px-3 py-2 text-right font-medium">Net</th>
                    <th class="px-5 py-2 text-right font-medium">Marge</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in recentSales" :key="item.id" class="border-t border-muted">
                    <td class="px-5 py-3">
                      <p class="font-medium text-highlighted">{{ item.name }}</p>
                      <p class="text-xs text-dimmed">
                        {{
                          [item.card_number, item.rarity, formatDate(item.sale.sold_on)]
                            .filter(Boolean)
                            .join(' · ')
                        }}
                      </p>
                    </td>
                    <td class="px-3 py-3 text-muted">{{ PLATFORM_LABELS[item.sale.platform] }}</td>
                    <td class="px-3 py-3 text-right tabular-nums">
                      {{ formatCents(item.sale.breakdown.net_cents) }}
                    </td>
                    <td
                      class="px-5 py-3 text-right tabular-nums"
                      :class="signClass(item.sale.breakdown.margin_cents)"
                    >
                      {{ formatSignedCents(item.sale.breakdown.margin_cents) }}
                    </td>
                  </tr>
                </tbody>
              </table>
              <p v-else class="px-5 pb-5 text-sm text-muted">
                Aucune vente enregistrée pour l’instant.
              </p>
            </div>
          </UCard>

          <UCard class="min-w-0 flex-[1_1_300px]" :ui="{ body: 'flex flex-col gap-2.5 sm:p-5' }">
            <h2 class="mb-1 font-semibold text-highlighted">À faire</h2>
            <NuxtLink
              v-for="todo in todos"
              :key="todo.label"
              :to="todo.to"
              class="flex items-center gap-3 rounded-lg bg-elevated p-3 transition-colors hover:bg-accented"
            >
              <span
                class="flex size-9 shrink-0 items-center justify-center rounded-md"
                :class="TONE_CLASSES[todo.tone]"
              >
                <UIcon :name="todo.icon" class="size-4" />
              </span>
              <span class="min-w-0 flex-1 text-sm text-highlighted">
                {{ todo.label }}
                <span class="mt-0.5 block text-xs text-dimmed">{{ todo.hint }}</span>
              </span>
            </NuxtLink>
            <p v-if="!todos.length" class="text-sm text-muted">
              Rien en attente : tout est à jour.
            </p>
          </UCard>
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
