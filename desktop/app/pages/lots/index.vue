<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { LotSummary } from '~/types/engine'

const engine = useEngine()
const { data: lots, status, error, refresh } = useAsyncData('lots', () => engine.listLots())

const creating = ref(false)

const columns: TableColumn<LotSummary>[] = [
  { accessorKey: 'label', header: 'Lot' },
  { accessorKey: 'status', header: 'Statut' },
  { accessorKey: 'ordered_on', header: 'Commandé le' },
  { accessorKey: 'item_count', header: 'Cartes' },
  { accessorKey: 'goods_jpy', header: 'Achats' },
  { accessorKey: 'applied_import_vat_cents', header: 'TVA' },
  { accessorKey: 'landed_total_cents', header: 'Coût de revient' },
]
</script>

<template>
  <UDashboardPanel id="lots">
    <template #header>
      <UDashboardNavbar title="Lots">
        <template #leading><UDashboardSidebarCollapse /></template>
        <template #right>
          <UButton icon="i-lucide-plus" label="Nouveau lot" @click="creating = true" />
        </template>
      </UDashboardNavbar>
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

      <UTable
        v-else
        :data="lots ?? []"
        :columns="columns"
        :loading="status === 'pending'"
        empty="Aucun lot pour l’instant. Un lot correspond à un colis Neokyo."
        @select="(_event, row) => navigateTo(`/lots/${row.original.id}`)"
      >
        <template #label-cell="{ row }">
          <span class="font-medium text-highlighted">{{ row.original.label }}</span>
        </template>
        <template #status-cell="{ row }">
          <UBadge
            :color="LOT_STATUS_COLORS[row.original.status]"
            variant="subtle"
            :label="LOT_STATUS_LABELS[row.original.status]"
          />
        </template>
        <template #ordered_on-cell="{ row }">{{ formatDate(row.original.ordered_on) }}</template>
        <template #item_count-cell="{ row }">
          <span class="tabular-nums">
            {{ row.original.item_count }}
            <span v-if="row.original.sold_count" class="text-muted">
              ({{ row.original.sold_count }} vendue{{ row.original.sold_count > 1 ? 's' : '' }})
            </span>
          </span>
        </template>
        <template #goods_jpy-cell="{ row }">
          <span class="tabular-nums">{{ formatYen(row.original.goods_jpy) }}</span>
        </template>
        <template #applied_import_vat_cents-cell="{ row }">
          <span class="tabular-nums">{{ formatCents(row.original.applied_import_vat_cents) }}</span>
          <UBadge
            v-if="row.original.vat_estimated"
            color="neutral"
            variant="outline"
            size="sm"
            label="estimée"
            class="ml-2"
          />
        </template>
        <template #landed_total_cents-cell="{ row }">
          <span class="font-medium tabular-nums">
            {{ formatCents(row.original.landed_total_cents) }}
          </span>
        </template>
      </UTable>

      <LotFormModal v-model:open="creating" @saved="(lot) => navigateTo(`/lots/${lot.id}`)" />
    </template>
  </UDashboardPanel>
</template>
