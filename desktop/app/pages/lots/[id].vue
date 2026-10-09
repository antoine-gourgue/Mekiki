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

// A sale counts in the books: the engine refuses to delete it with its card or lot.
function refuseSold(description: string) {
  toast.add({ title: 'Suppression impossible', description, color: 'error' })
}

async function deleteLot() {
  if (!lot.value) return
  if (lot.value.sold_count) {
    refuseSold(
      lot.value.sold_count > 1
        ? `${lot.value.sold_count} cartes de ce lot sont vendues : annulez d’abord leurs ventes, qui comptent dans vos livres.`
        : 'Une carte de ce lot est vendue : annulez d’abord sa vente, qui compte dans vos livres.',
    )
    return
  }
  const confirmed = await confirm({
    title: `Supprimer « ${lot.value.label} » ?`,
    description: `Ses ${lot.value.item_count} cartes seront supprimées aussi.`,
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
  if (item.sale) {
    refuseSold('Cette carte est vendue : annulez d’abord sa vente, qui compte dans vos livres.')
    return
  }
  const confirmed = await confirm({ title: `Supprimer « ${item.name} » ?` })
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

const RIGHT = { class: { th: 'text-right', td: 'text-right' } }
const columns: TableColumn<Item>[] = [
  { accessorKey: 'name', header: 'Carte' },
  { accessorKey: 'price_jpy', header: 'Achat', meta: RIGHT },
  { id: 'landed', header: 'Coût de revient', meta: RIGHT },
  { accessorKey: 'status', header: 'Statut' },
  { id: 'net', header: 'Net', meta: RIGHT },
  { id: 'margin', header: 'Marge', meta: RIGHT },
  { id: 'actions', header: '' },
]

const soldItems = computed(() => (lot.value?.items ?? []).filter((item) => item.sale))
const soldNet = computed(() =>
  soldItems.value.reduce((sum, item) => sum + (item.sale?.breakdown.net_cents ?? 0), 0),
)
const soldMargin = computed(() =>
  soldItems.value.reduce((sum, item) => sum + (item.sale?.breakdown.margin_cents ?? 0), 0),
)

// The carrier's VAT invoice usually comes after the first sales: entering it corrects
// their margins, since the landed cost is computed on every read.
const vatInput = ref<number | null>(null)
const savingVat = ref(false)
async function saveVat() {
  if (!lot.value || vatInput.value == null) return
  savingVat.value = true
  try {
    lot.value = await engine.updateLot(lot.value.id, { import_vat_cents: vatInput.value })
    vatInput.value = null
    toast.add({
      title: 'TVA enregistrée',
      description: 'Le coût de revient et les marges du lot sont recalculés.',
      color: 'success',
    })
  } catch (failure) {
    showError(failure)
  } finally {
    savingVat.value = false
  }
}

const dates = computed(() => {
  const l = lot.value
  if (!l) return ''
  return [
    l.ordered_on ? `commandé le ${formatDate(l.ordered_on)}` : null,
    l.shipped_on ? `expédié le ${formatDate(l.shipped_on)}` : null,
    l.received_on ? `reçu le ${formatDate(l.received_on)}` : null,
    `${l.item_count} carte${l.item_count > 1 ? 's' : ''}`,
  ]
    .filter(Boolean)
    .join(' · ')
})

function lotActions(): DropdownMenuItem[] {
  return [
    {
      label: 'Supprimer le lot',
      icon: 'i-lucide-trash-2',
      color: 'error' as const,
      onSelect: () => deleteLot(),
    },
  ]
}

const statusItems = selectItems(LOT_STATUS_LABELS)
</script>

<template>
  <UDashboardPanel id="lot">
    <template #header>
      <div class="px-4 pt-5 sm:px-8 lg:px-10">
        <UButton
          to="/lots"
          icon="i-lucide-chevron-left"
          color="neutral"
          variant="link"
          size="sm"
          label="Retour aux lots"
          class="-ms-1.5 px-0 text-muted"
        />
      </div>
      <UDashboardNavbar
        :ui="{
          root: 'pt-1',
          title: 'block min-w-0 whitespace-normal',
          right: 'flex-wrap justify-end gap-2',
        }"
      >
        <template #leading
          ><UDashboardSidebarCollapse class="-ms-1.5 self-start text-dimmed"
        /></template>
        <template #title>
          <div class="flex flex-wrap items-center gap-3">
            <h1 class="truncate text-2xl font-semibold tracking-tight text-highlighted">
              {{ lot?.label ?? 'Lot' }}
            </h1>
            <UBadge
              v-if="lot"
              :color="LOT_STATUS_COLORS[lot.status]"
              variant="soft"
              :label="LOT_STATUS_LABELS[lot.status]"
            />
          </div>
          <p v-if="lot" class="mt-1 text-sm font-normal text-muted">{{ dates }}</p>
        </template>
        <template v-if="lot" #right>
          <USelect
            :model-value="lot.status"
            :items="statusItems"
            aria-label="Statut du lot"
            class="w-44"
            @update:model-value="changeStatus"
          />
          <UButton color="neutral" variant="outline" label="Modifier" @click="editingLot = true" />
          <UDropdownMenu :items="lotActions()" :content="{ align: 'end' }">
            <UButton
              icon="i-lucide-ellipsis"
              color="neutral"
              variant="outline"
              aria-label="Plus d’actions"
            />
          </UDropdownMenu>
          <UButton icon="i-lucide-plus" label="Ajouter une carte" @click="addingItem = true" />
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
        <div class="flex flex-wrap items-stretch gap-3.5">
          <UCard class="min-w-0 flex-[3_1_440px]" :ui="{ body: 'space-y-2.5 text-sm sm:p-5' }">
            <div class="flex items-baseline justify-between gap-3">
              <h2 class="font-semibold text-highlighted">Coût de revient total</h2>
              <span v-if="lot.vat_estimated" class="text-xs text-error">TVA estimée</span>
            </div>
            <p class="text-xs text-dimmed">
              Achats {{ formatYen(lot.goods_jpy) }}. Les frais sont répartis au prorata du prix des
              cartes.
            </p>
            <div v-for="fee in fees" :key="fee.label" class="flex justify-between gap-4">
              <span class="text-muted">{{ fee.label }}</span>
              <span class="text-right tabular-nums">{{ fee.value }}</span>
            </div>
            <div
              class="flex justify-between gap-4 border-t border-default pt-3 font-semibold text-highlighted"
            >
              <span>
                Total
                <span v-if="lot.item_count" class="font-normal text-muted">
                  · {{ formatCents(Math.round(lot.landed_total_cents / lot.item_count)) }} par carte
                  en moyenne
                </span>
              </span>
              <span class="tabular-nums">{{ formatCents(lot.landed_total_cents) }}</span>
            </div>
            <div
              v-if="lot.shipping_method || lot.tracking_number"
              class="flex flex-wrap items-center gap-2 pt-1 text-dimmed"
            >
              <span>
                {{ lot.shipping_method }}
                <span v-if="lot.tracking_number">· {{ lot.tracking_number }}</span>
              </span>
              <UButton
                v-if="trackingFor(lot.tracking_number)"
                size="xs"
                color="neutral"
                variant="outline"
                icon="i-lucide-truck"
                :label="`Suivre (${trackingFor(lot.tracking_number)?.carrier})`"
                @click="openExternal(trackingFor(lot.tracking_number)!.url)"
              />
            </div>
            <p v-if="lot.notes" class="text-sm whitespace-pre-line text-muted">{{ lot.notes }}</p>
          </UCard>

          <div class="flex min-w-0 flex-[2_1_320px] flex-col gap-3.5">
            <div class="grid grid-cols-3 gap-2.5">
              <InfoTile label="Vendues" :value="`${lot.sold_count}/${lot.item_count}`" />
              <InfoTile label="Net encaissé" :value="formatCents(soldNet)" />
              <InfoTile
                label="Marge"
                :value="formatSignedCents(soldMargin)"
                :value-class="signClass(soldMargin)"
              />
            </div>

            <form
              v-if="lot.vat_estimated"
              class="flex flex-1 flex-col gap-3 rounded-lg border border-error/40 bg-error/5 p-5"
              @submit.prevent="saveVat"
            >
              <div class="flex gap-3">
                <UIcon name="i-lucide-receipt" class="mt-0.5 size-5 shrink-0 text-error" />
                <div>
                  <p class="font-semibold text-highlighted">Facture de TVA reçue ?</p>
                  <p class="mt-1 text-sm text-muted">
                    Saisissez le montant réel : la marge des cartes déjà vendues sera recalculée.
                  </p>
                </div>
              </div>
              <div class="flex flex-wrap gap-2.5">
                <MoneyInput
                  v-model="vatInput"
                  currency="EUR"
                  :placeholder="formatCents(lot.applied_import_vat_cents)"
                  aria-label="TVA à l’import"
                  class="min-w-0 flex-[1_1_160px]"
                />
                <UButton
                  type="submit"
                  color="neutral"
                  label="Enregistrer"
                  :loading="savingVat"
                  :disabled="vatInput == null"
                />
              </div>
            </form>
            <UCard v-else class="flex-1" :ui="{ body: 'flex items-center gap-3 sm:p-5' }">
              <UIcon name="i-lucide-receipt" class="size-5 shrink-0 text-success" />
              <p class="text-sm text-muted">
                TVA à l’import réelle :
                <span class="text-highlighted tabular-nums">
                  {{ formatCents(lot.applied_import_vat_cents) }}
                </span>
              </p>
            </UCard>
          </div>
        </div>

        <UCard :ui="{ body: 'p-0 sm:p-0' }">
          <div class="flex items-baseline justify-between px-5 pt-4 pb-1">
            <h2 class="font-semibold text-highlighted">Cartes</h2>
            <span class="text-xs text-dimmed">le coût de chaque carte suit son prix d’achat</span>
          </div>
          <UTable
            :data="lot.items"
            :columns="columns"
            :loading="status === 'pending'"
            empty="Aucune carte dans ce lot."
          >
            <template #name-cell="{ row }">
              <p class="font-medium text-highlighted">{{ row.original.name }}</p>
              <p class="text-xs text-dimmed">
                {{
                  [
                    GAME_LABELS[row.original.game],
                    [row.original.set_code?.toUpperCase(), row.original.card_number]
                      .filter(Boolean)
                      .join(' '),
                    row.original.rarity,
                  ]
                    .filter(Boolean)
                    .join(' · ')
                }}
              </p>
            </template>
            <template #price_jpy-cell="{ row }">
              <span class="tabular-nums">{{ formatYen(row.original.price_jpy) }}</span>
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
            <template #status-cell="{ row }">
              <UBadge
                :color="ITEM_STATUS_COLORS[row.original.status]"
                variant="soft"
                :label="
                  row.original.sale
                    ? `Vendue · ${PLATFORM_LABELS[row.original.sale.platform]}`
                    : ITEM_STATUS_LABELS[row.original.status]
                "
              />
            </template>
            <template #net-cell="{ row }">
              <span class="tabular-nums" :class="{ 'text-dimmed': !row.original.sale }">
                {{ row.original.sale ? formatCents(row.original.sale.breakdown.net_cents) : '—' }}
              </span>
            </template>
            <template #margin-cell="{ row }">
              <span
                class="tabular-nums"
                :class="
                  row.original.sale
                    ? signClass(row.original.sale.breakdown.margin_cents)
                    : 'text-dimmed'
                "
              >
                {{
                  row.original.sale
                    ? formatSignedCents(row.original.sale.breakdown.margin_cents)
                    : '—'
                }}
              </span>
            </template>
            <template #actions-cell="{ row }">
              <div class="flex justify-end">
                <UDropdownMenu :items="itemActions(row.original)" :content="{ align: 'end' }">
                  <UButton
                    icon="i-lucide-ellipsis"
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
