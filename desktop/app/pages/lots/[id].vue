<script setup lang="ts">
import type { DropdownMenuItem, TableColumn } from '@nuxt/ui'
import type { Item, LotStatus } from '~/types/engine'

const route = useRoute()
const lotId = computed(() => Number(route.params.id))

const engine = useEngine()
const showError = useErrorToast()
const confirm = useConfirm()
const toast = useToast()

const {
  data: lot,
  status,
  error,
  refresh,
} = useAsyncData(`lot-${lotId.value}`, () => engine.getLot(lotId.value), { watch: [lotId] })
const { data: lots } = useAsyncData('lots', () => engine.listLots())

const editingLot = ref(false)
const addingItem = ref(false)
const editingItem = ref<Item | null>(null)
const editingItemOpen = ref(false)

async function changeStatus(next: LotStatus) {
  if (!lot.value || next === lot.value.status) return
  try {
    const patch: { status: LotStatus; received_on?: string } = { status: next }
    // Receiving a parcel is usually recorded on the day it arrives.
    if (next === 'received' && !lot.value.received_on) patch.received_on = todayIso()
    lot.value = await engine.updateLot(lot.value.id, patch)
  } catch (failure) {
    showError(failure)
  }
}

async function deleteLot() {
  if (!lot.value) return
  const confirmed = await confirm({
    title: `Supprimer « ${lot.value.label} » ?`,
    description: `Ses ${lot.value.item_count} cartes et leurs ventes seront supprimées aussi.`,
  })
  if (!confirmed) return
  try {
    await engine.deleteLot(lot.value.id)
    toast.add({ title: 'Lot supprimé', color: 'success' })
    await navigateTo('/lots')
  } catch (failure) {
    showError(failure)
  }
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

function editItem(item: Item) {
  editingItem.value = item
  editingItemOpen.value = true
}

function itemActions(item: Item): DropdownMenuItem[] {
  return [
    { label: 'Modifier', icon: 'i-lucide-pencil', onSelect: () => editItem(item) },
    ...(item.source_url
      ? [
          {
            label: 'Voir l’annonce',
            icon: 'i-lucide-external-link',
            onSelect: () => openExternal(item.source_url!),
          },
        ]
      : []),
    {
      label: 'Supprimer',
      icon: 'i-lucide-trash-2',
      color: 'error' as const,
      onSelect: () => deleteItem(item),
    },
  ]
}

const fees = computed(() => {
  if (!lot.value) return []
  const l = lot.value
  return [
    { label: 'Taux de change', value: `${l.fx_jpy_per_eur.toLocaleString('fr-FR')} ¥ pour 1 €` },
    { label: 'Emballage', value: formatYen(l.packing_fee_jpy) },
    { label: 'Envoi international', value: formatYen(l.international_shipping_jpy) },
    { label: 'Assurance', value: formatYen(l.insurance_jpy) },
    { label: 'Autres frais', value: formatYen(l.other_fees_jpy) },
    { label: 'Frais de paiement', value: formatCents(l.payment_fees_cents) },
    {
      label: l.vat_estimated ? 'TVA à l’import (estimée)' : 'TVA à l’import',
      value: formatCents(l.applied_import_vat_cents),
    },
    { label: 'Droits de douane', value: formatCents(l.customs_duty_cents) },
    { label: 'Frais de dossier', value: formatCents(l.handling_fee_cents) },
  ]
})

const columns: TableColumn<Item>[] = [
  { accessorKey: 'name', header: 'Carte' },
  { accessorKey: 'price_jpy', header: 'Prix' },
  { id: 'landed', header: 'Coût de revient' },
  { accessorKey: 'status', header: 'Statut' },
  { id: 'actions', header: '' },
]

const statusItems = selectItems(LOT_STATUS_LABELS)
</script>

<template>
  <UDashboardPanel id="lot">
    <template #header>
      <UDashboardNavbar :title="lot?.label ?? 'Lot'">
        <template #leading>
          <UDashboardSidebarCollapse />
          <UButton
            to="/lots"
            icon="i-lucide-arrow-left"
            color="neutral"
            variant="ghost"
            aria-label="Retour aux lots"
          />
        </template>
        <template v-if="lot" #right>
          <USelect
            :model-value="lot.status"
            :items="statusItems"
            class="w-40"
            @update:model-value="changeStatus"
          />
          <UButton
            icon="i-lucide-pencil"
            color="neutral"
            variant="outline"
            label="Modifier"
            @click="editingLot = true"
          />
          <UButton
            icon="i-lucide-trash-2"
            color="error"
            variant="ghost"
            aria-label="Supprimer le lot"
            @click="deleteLot"
          />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="Impossible de charger le lot"
        :description="engineErrorMessage(error)"
        :actions="[{ label: 'Retour aux lots', to: '/lots' }]"
      />

      <template v-else-if="lot">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile
            icon="i-lucide-layers"
            label="Cartes"
            :value="String(lot.item_count)"
            :hint="lot.sold_count ? `${lot.sold_count} vendue(s)` : undefined"
          />
          <StatTile icon="i-lucide-japanese-yen" label="Achats" :value="formatYen(lot.goods_jpy)" />
          <StatTile
            icon="i-lucide-landmark"
            label="TVA à l’import"
            :value="formatCents(lot.applied_import_vat_cents)"
            :hint="
              lot.vat_estimated ? 'Estimée : saisissez la facture du transporteur' : 'Montant réel'
            "
          />
          <StatTile
            icon="i-lucide-calculator"
            label="Coût de revient total"
            :value="formatCents(lot.landed_total_cents)"
          />
        </div>

        <div class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
          <UCard :ui="{ body: 'p-0 sm:p-0' }">
            <template #header>
              <div class="flex items-center justify-between gap-4">
                <h2 class="font-medium text-highlighted">Cartes du lot</h2>
                <UButton
                  icon="i-lucide-plus"
                  label="Ajouter une carte"
                  @click="addingItem = true"
                />
              </div>
            </template>

            <UTable
              :data="lot.items"
              :columns="columns"
              :loading="status === 'pending'"
              empty="Aucune carte dans ce lot."
            >
              <template #name-cell="{ row }">
                <p class="font-medium text-highlighted">{{ row.original.name }}</p>
                <p class="text-xs text-muted">
                  {{ GAME_LABELS[row.original.game] }}
                  <template v-if="row.original.set_code"> · {{ row.original.set_code }}</template>
                  <template v-if="row.original.card_number">
                    {{ row.original.card_number }}</template
                  >
                  <template v-if="row.original.rarity"> · {{ row.original.rarity }}</template>
                </p>
              </template>
              <template #price_jpy-cell="{ row }">
                <span class="tabular-nums">{{ formatYen(row.original.price_jpy) }}</span>
              </template>
              <template #landed-cell="{ row }">
                <UPopover mode="hover" :content="{ side: 'left' }">
                  <span class="cursor-help font-medium tabular-nums underline decoration-dotted">
                    {{ formatCents(row.original.landed_cost.total_cents) }}
                  </span>
                  <template #content>
                    <div class="w-72 p-3">
                      <LandedCostBreakdown :cost="row.original.landed_cost" />
                    </div>
                  </template>
                </UPopover>
              </template>
              <template #status-cell="{ row }">
                <UBadge
                  :color="ITEM_STATUS_COLORS[row.original.status]"
                  variant="subtle"
                  :label="ITEM_STATUS_LABELS[row.original.status]"
                />
              </template>
              <template #actions-cell="{ row }">
                <div class="flex justify-end">
                  <UDropdownMenu :items="itemActions(row.original)" :content="{ align: 'end' }">
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
          </UCard>

          <UCard>
            <template #header>
              <h2 class="font-medium text-highlighted">Frais du colis</h2>
              <p class="text-sm text-muted">Répartis au prorata du prix des cartes.</p>
            </template>
            <dl class="space-y-2 text-sm">
              <div v-for="fee in fees" :key="fee.label" class="flex justify-between gap-4">
                <dt class="text-muted">{{ fee.label }}</dt>
                <dd class="text-right tabular-nums">{{ fee.value }}</dd>
              </div>
            </dl>
            <template v-if="lot.tracking_number || lot.shipping_method || lot.notes" #footer>
              <p v-if="lot.shipping_method || lot.tracking_number" class="text-sm">
                {{ lot.shipping_method }}
                <span v-if="lot.tracking_number" class="text-muted"
                  >· {{ lot.tracking_number }}</span
                >
              </p>
              <p v-if="lot.notes" class="mt-2 text-sm whitespace-pre-line text-muted">
                {{ lot.notes }}
              </p>
            </template>
          </UCard>
        </div>
      </template>

      <LotFormModal v-model:open="editingLot" :lot="lot" @saved="(saved) => (lot = saved)" />
      <ItemFormModal v-model:open="addingItem" :lot-id="lotId" @saved="() => refresh()" />
      <ItemFormModal
        v-model:open="editingItemOpen"
        :item="editingItem"
        :lots="lots ?? []"
        @saved="() => refresh()"
      />
    </template>
  </UDashboardPanel>
</template>
