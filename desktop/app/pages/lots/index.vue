<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { LotStatus, LotSummary } from '~/types/engine'

const engine = useEngine()
const route = useRoute()
const { data: lots, status, error, refresh } = useAsyncData('lots', () => engine.listLots())

// "Nouveau lot" on the dashboard lands here with ?nouveau=1.
const creating = ref(route.query.nouveau === '1')

type Filter = 'all' | LotStatus
const filter = ref<Filter>('all')
const filterItems = computed(() => {
  const count = (value: LotStatus) => (lots.value ?? []).filter((l) => l.status === value).length
  return [
    { value: 'all' as Filter, label: 'Tous', count: lots.value?.length ?? null },
    { value: 'purchasing' as Filter, label: 'Achat en cours', count: count('purchasing') },
    { value: 'shipped' as Filter, label: 'Expédiés', count: count('shipped') },
    { value: 'received' as Filter, label: 'Reçus', count: count('received') },
  ]
})
const shown = computed(() =>
  (lots.value ?? []).filter((lot) => filter.value === 'all' || lot.status === filter.value),
)

const totals = computed(() => {
  const list = lots.value ?? []
  return {
    lots: list.length,
    onTheWay: list.filter((l) => l.status === 'shipped').length,
    cards: list.reduce((sum, l) => sum + l.item_count, 0),
    sold: list.reduce((sum, l) => sum + l.sold_count, 0),
    invested: list.reduce((sum, l) => sum + l.landed_total_cents, 0),
    vatToEnter: list.filter((l) => l.status === 'received' && l.vat_estimated).length,
  }
})

const columns: TableColumn<LotSummary>[] = [
  { accessorKey: 'label', header: 'Lot' },
  { accessorKey: 'status', header: 'Statut' },
  {
    accessorKey: 'goods_jpy',
    header: 'Achats',
    meta: { class: { th: 'text-right', td: 'text-right' } },
  },
  {
    accessorKey: 'landed_total_cents',
    header: 'Coût de revient',
    meta: { class: { th: 'text-right', td: 'text-right' } },
  },
  { accessorKey: 'sold_count', header: 'Vendues', meta: { class: { th: 'w-56' } } },
]
</script>

<template>
  <UDashboardPanel id="lots">
    <template #header>
      <PageNavbar
        title="Lots"
        description="Un lot par colis Neokyo : ses frais sont répartis sur chacune de ses cartes."
      >
        <template #right>
          <UButton icon="i-lucide-plus" label="Nouveau lot" @click="creating = true" />
        </template>
      </PageNavbar>
    </template>

    <template #body>
      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="Impossible de charger les lots"
        :description="engineErrorMessage(error)"
        :actions="[{ label: 'Réessayer', onClick: () => refresh() }]"
      />

      <template v-else>
        <div class="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile
            label="Lots"
            :value="String(totals.lots)"
            :hint="
              totals.onTheWay
                ? `dont ${totals.onTheWay} expédié${totals.onTheWay > 1 ? 's' : ''}`
                : undefined
            "
          />
          <StatTile
            label="Cartes achetées"
            :value="String(totals.cards)"
            :hint="`${totals.sold} vendue${totals.sold > 1 ? 's' : ''}`"
          />
          <StatTile
            label="Investi"
            :value="formatCents(totals.invested)"
            hint="coût de revient total"
          />
          <StatTile
            label="TVA à saisir"
            :value="String(totals.vatToEnter)"
            :value-class="totals.vatToEnter ? 'text-error' : undefined"
            hint="lots reçus dont la TVA est estimée"
          />
        </div>

        <SegmentedControl
          v-model="filter"
          :items="filterItems"
          label="Statut des lots"
          class="self-start"
        />

        <UCard :ui="{ body: 'p-0 sm:p-0' }">
          <UTable
            :data="shown"
            :columns="columns"
            :loading="status === 'pending'"
            empty="Aucun lot pour l’instant. Un lot correspond à un colis Neokyo."
            :ui="{ tr: 'cursor-pointer', td: 'py-3.5' }"
            @select="(_event, row) => navigateTo(`/lots/${row.original.id}`)"
          >
            <template #label-cell="{ row }">
              <p class="font-semibold text-highlighted">{{ row.original.label }}</p>
              <p class="text-xs text-dimmed">
                {{
                  [
                    row.original.ordered_on
                      ? `commandé le ${formatDate(row.original.ordered_on)}`
                      : null,
                    `${row.original.item_count} carte${row.original.item_count > 1 ? 's' : ''}`,
                  ]
                    .filter(Boolean)
                    .join(' · ')
                }}
              </p>
            </template>
            <template #status-cell="{ row }">
              <UBadge
                :color="LOT_STATUS_COLORS[row.original.status]"
                variant="soft"
                :label="LOT_STATUS_LABELS[row.original.status]"
                class="rounded-full"
              />
            </template>
            <template #goods_jpy-cell="{ row }">
              <span class="tabular-nums">{{ formatYen(row.original.goods_jpy) }}</span>
            </template>
            <template #landed_total_cents-cell="{ row }">
              <p class="font-medium text-highlighted tabular-nums">
                {{ formatCents(row.original.landed_total_cents) }}
              </p>
              <p v-if="row.original.vat_estimated" class="text-xs text-error">TVA estimée</p>
            </template>
            <template #sold_count-cell="{ row }">
              <div class="flex items-center gap-3">
                <span class="h-1.5 flex-1 overflow-hidden rounded-full bg-accented">
                  <span
                    class="block h-full rounded-full bg-ink-100"
                    :style="{
                      width: `${row.original.item_count ? (100 * row.original.sold_count) / row.original.item_count : 0}%`,
                    }"
                  />
                </span>
                <span class="w-12 text-right text-xs text-muted tabular-nums">
                  {{ row.original.sold_count }}/{{ row.original.item_count }}
                </span>
              </div>
            </template>
          </UTable>
        </UCard>
      </template>

      <LotFormModal v-model:open="creating" @saved="(lot) => navigateTo(`/lots/${lot.id}`)" />
    </template>
  </UDashboardPanel>
</template>
