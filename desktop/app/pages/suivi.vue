<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { TrackedCard } from '~/types/engine'

const engine = useEngine()
const showError = useErrorToast()
const confirm = useConfirm()
const toast = useToast()

const {
  data: cards,
  status,
  error,
  refresh,
} = useAsyncData('tracked-cards', () => engine.listTrackedCards())
const { data: cardmarket, refresh: refreshStatus } = useAsyncData('cardmarket-status', () =>
  engine.cardmarketStatus(),
)

const editing = ref<TrackedCard | null>(null)
const modalOpen = ref(false)

function openModal(card: TrackedCard | null) {
  editing.value = card
  modalOpen.value = true
}

async function toggleActive(card: TrackedCard, active: boolean) {
  try {
    await engine.updateTrackedCard(card.id, { active })
    await refresh()
  } catch (failure) {
    showError(failure)
  }
}

async function remove(card: TrackedCard) {
  const confirmed = await confirm({
    title: `Ne plus suivre « ${card.name} » ?`,
    description: 'Les annonces trouvées pour cette carte seront supprimées.',
  })
  if (!confirmed) return
  try {
    await engine.deleteTrackedCard(card.id)
    await refresh()
  } catch (failure) {
    showError(failure)
  }
}

const updatingPrices = ref(false)

async function updatePrices() {
  updatingPrices.value = true
  try {
    cardmarket.value = await engine.refreshCardmarket()
    await refresh()
    toast.add({ title: 'Cotes Cardmarket à jour', color: 'success' })
  } catch (failure) {
    showError(failure, 'Mise à jour des cotes impossible')
    await refreshStatus()
  } finally {
    updatingPrices.value = false
  }
}

const columns: TableColumn<TrackedCard>[] = [
  { accessorKey: 'name', header: 'Carte' },
  { id: 'market', header: 'Cote' },
  { id: 'max_buy', header: 'Prix max. d’achat' },
  { id: 'listings', header: 'Annonces' },
  { accessorKey: 'last_scanned_at', header: 'Dernier scan' },
  { accessorKey: 'active', header: 'Auto' },
  { id: 'actions', header: '' },
]
</script>

<template>
  <UDashboardPanel id="tracked-cards">
    <template #header>
      <UDashboardNavbar title="Cartes suivies">
        <template #leading><UDashboardSidebarCollapse /></template>
        <template #right>
          <UButton icon="i-lucide-plus" label="Suivre une carte" @click="openModal(null)" />
        </template>
      </UDashboardNavbar>
      <UDashboardToolbar>
        <template #left>
          <p class="text-sm text-muted">
            <template v-for="(entry, index) in cardmarket ?? []" :key="entry.game">
              <span v-if="index"> · </span>
              {{ GAME_LABELS[entry.game] }} :
              <template v-if="entry.prices_date">
                cotes du {{ formatDate(entry.prices_date.slice(0, 10)) }} ({{
                  entry.priced_products.toLocaleString('fr-FR')
                }}
                produits)
              </template>
              <template v-else>cotes jamais téléchargées</template>
              <UTooltip v-if="entry.last_error" :text="entry.last_error">
                <UIcon
                  name="i-lucide-triangle-alert"
                  class="ml-1 size-4 align-text-bottom text-warning"
                />
              </UTooltip>
            </template>
          </p>
        </template>
        <template #right>
          <UButton
            icon="i-lucide-refresh-cw"
            color="neutral"
            variant="outline"
            size="sm"
            label="Mettre à jour les cotes"
            :loading="updatingPrices"
            @click="updatePrices"
          />
        </template>
      </UDashboardToolbar>
    </template>

    <template #body>
      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="Impossible de charger les cartes suivies"
        :description="engineErrorMessage(error)"
        :actions="[{ label: 'Réessayer', onClick: () => refresh() }]"
      />

      <UTable
        v-else
        :data="cards ?? []"
        :columns="columns"
        :loading="status === 'pending'"
        empty="Aucune carte suivie. Ajoutez les cartes que vous revendez souvent : le scanner les cherchera pour vous."
      >
        <template #name-cell="{ row }">
          <p class="font-medium text-highlighted">{{ row.original.name }}</p>
          <p class="text-xs text-muted">
            {{ GAME_LABELS[row.original.game] }}
            <template v-if="row.original.set_code"> · {{ row.original.set_code }}</template>
            <template v-if="row.original.card_number"> {{ row.original.card_number }}</template>
            · « {{ row.original.search_query }} »
          </p>
        </template>
        <template #market-cell="{ row }">
          <template v-if="row.original.expected_sale_cents != null">
            <span class="tabular-nums">{{ formatCents(row.original.expected_sale_cents) }}</span>
            <span class="block text-xs text-muted">
              {{
                row.original.target_price_cents != null
                  ? 'prix visé'
                  : `Cardmarket ${row.original.market?.reference_field ?? ''}`
              }}
            </span>
          </template>
          <span v-else class="text-muted">Pas de cote</span>
        </template>
        <template #max_buy-cell="{ row }">
          <span class="font-medium tabular-nums">{{
            formatYen(row.original.max_buy_price_jpy)
          }}</span>
        </template>
        <template #listings-cell="{ row }">
          <NuxtLink
            v-if="row.original.listing_count"
            :to="{ path: '/affaires', query: { carte: row.original.id } }"
            class="tabular-nums text-primary hover:underline"
          >
            {{ row.original.listing_count }}
          </NuxtLink>
          <span v-else class="text-muted">0</span>
          <span v-if="row.original.best_roi != null" class="block text-xs text-muted">
            meilleur ROI {{ formatRatio(row.original.best_roi) }}
          </span>
        </template>
        <template #last_scanned_at-cell="{ row }">
          {{ row.original.last_scanned_at ? formatDateTime(row.original.last_scanned_at) : '—' }}
        </template>
        <template #active-cell="{ row }">
          <USwitch
            :model-value="row.original.active"
            :aria-label="`Scanner ${row.original.name} automatiquement`"
            @update:model-value="(value) => toggleActive(row.original, value)"
          />
        </template>
        <template #actions-cell="{ row }">
          <div class="flex justify-end gap-1">
            <UButton
              v-if="row.original.market"
              icon="i-lucide-external-link"
              color="neutral"
              variant="ghost"
              aria-label="Voir sur Cardmarket"
              @click="openExternal(row.original.market.url)"
            />
            <UButton
              icon="i-lucide-pencil"
              color="neutral"
              variant="ghost"
              aria-label="Modifier"
              @click="openModal(row.original)"
            />
            <UButton
              icon="i-lucide-trash-2"
              color="neutral"
              variant="ghost"
              aria-label="Ne plus suivre"
              @click="remove(row.original)"
            />
          </div>
        </template>
      </UTable>

      <TrackedCardModal v-model:open="modalOpen" :card="editing" @saved="() => refresh()" />
    </template>
  </UDashboardPanel>
</template>
