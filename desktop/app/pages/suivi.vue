<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
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
    const statuses = await engine.refreshCardmarket()
    cardmarket.value = statuses
    await refresh()
    // A download that failed leaves the previous prices: the engine answers all the same.
    const problems = statuses.flatMap((entry) =>
      [entry.last_error, entry.index_error]
        .filter((text): text is string => !!text)
        .map((text) => `${GAME_LABELS[entry.game]} : ${text}`),
    )
    if (problems.length) {
      toast.add({
        title: 'Cotes pas toutes mises à jour',
        description: problems.join(' · '),
        color: 'warning',
      })
    } else {
      toast.add({ title: 'Cotes Cardmarket à jour', color: 'success' })
    }
  } catch (failure) {
    showError(failure, 'Mise à jour des cotes impossible')
    await refreshStatus()
  } finally {
    updatingPrices.value = false
  }
}

function menu(card: TrackedCard): DropdownMenuItem[] {
  return [
    ...(card.market
      ? [
          {
            label: 'Voir sur Cardmarket',
            icon: 'i-lucide-external-link',
            onSelect: () => openExternal(card.market!.url),
          },
        ]
      : []),
    { label: 'Modifier', icon: 'i-lucide-pencil', onSelect: () => openModal(card) },
    {
      label: 'Ne plus suivre',
      icon: 'i-lucide-trash-2',
      color: 'error' as const,
      onSelect: () => remove(card),
    },
  ]
}
</script>

<template>
  <UDashboardPanel id="tracked-cards">
    <template #header>
      <PageNavbar
        title="Cartes suivies"
        description="Le scanner ne garde que l’impression exacte : extension, numéro, miroir, parallèle ou manga."
      >
        <template #right>
          <UButton
            icon="i-lucide-refresh-cw"
            color="neutral"
            variant="outline"
            label="Mettre à jour les cotes"
            :loading="updatingPrices"
            @click="updatePrices"
          />
          <UButton icon="i-lucide-plus" label="Suivre une carte" @click="openModal(null)" />
        </template>
      </PageNavbar>
    </template>

    <template #body>
      <p class="text-sm text-dimmed">
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
          <UTooltip
            v-if="entry.last_error || entry.index_error"
            :text="[entry.last_error, entry.index_error].filter(Boolean).join(' · ')"
          >
            <UIcon
              name="i-lucide-triangle-alert"
              class="ml-1 size-4 align-text-bottom text-warning"
            />
          </UTooltip>
        </template>
      </p>

      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="Impossible de charger les cartes suivies"
        :description="engineErrorMessage(error)"
        :actions="[{ label: 'Réessayer', onClick: () => refresh() }]"
      />

      <UEmpty
        v-else-if="cards && !cards.length"
        icon="i-lucide-eye"
        title="Aucune carte suivie"
        description="Ajoutez les cartes que vous revendez souvent, par leur nom en français, en anglais ou en japonais : le scanner les cherchera pour vous."
        :actions="[
          { label: 'Suivre une carte', icon: 'i-lucide-plus', onClick: () => openModal(null) },
        ]"
      />

      <div
        v-else
        class="grid gap-3.5 md:grid-cols-2 2xl:grid-cols-3"
        :class="{ 'opacity-60': status === 'pending' }"
      >
        <article
          v-for="card in cards ?? []"
          :key="card.id"
          class="flex flex-col gap-3.5 rounded-lg border border-default bg-muted p-4"
        >
          <div class="flex items-start gap-3">
            <div class="min-w-0 flex-1">
              <p class="truncate font-semibold text-highlighted">{{ card.name }}</p>
              <p class="mt-0.5 truncate text-sm text-muted" :title="card.search_query">
                {{ card.search_query }}
              </p>
              <div class="mt-2 flex flex-wrap gap-1.5">
                <span class="rounded-md bg-accented px-1.5 py-0.5 font-mono text-[11px]">
                  {{ GAME_LABELS[card.game] }}
                </span>
                <span
                  v-if="card.set_code || card.card_number"
                  class="rounded-md bg-accented px-1.5 py-0.5 font-mono text-[11px]"
                >
                  {{ [card.set_code?.toUpperCase(), card.card_number].filter(Boolean).join(' ') }}
                </span>
              </div>
            </div>
            <UDropdownMenu :items="menu(card)" :content="{ align: 'end' }">
              <UButton
                icon="i-lucide-ellipsis"
                color="neutral"
                variant="ghost"
                :aria-label="`Actions pour ${card.name}`"
              />
            </UDropdownMenu>
          </div>

          <div class="grid grid-cols-3 gap-2">
            <div class="rounded-md bg-elevated p-2.5">
              <p class="text-[11px] text-muted">
                {{ card.target_price_cents != null ? 'Prix visé' : 'Cote' }}
              </p>
              <p class="mt-0.5 truncate text-sm font-semibold text-highlighted tabular-nums">
                {{ card.expected_sale_cents != null ? formatCents(card.expected_sale_cents) : '—' }}
              </p>
            </div>
            <div class="rounded-md bg-elevated p-2.5">
              <p class="text-[11px] text-muted">Payer au plus</p>
              <p class="mt-0.5 truncate text-sm font-semibold text-highlighted tabular-nums">
                {{ formatYen(card.max_buy_price_jpy) }}
              </p>
            </div>
            <div class="rounded-md bg-elevated p-2.5">
              <p class="text-[11px] text-muted">Meilleur ROI</p>
              <p
                class="mt-0.5 truncate text-sm font-semibold tabular-nums"
                :class="signClass(card.best_roi)"
              >
                {{ formatRatio(card.best_roi) }}
              </p>
            </div>
          </div>

          <div class="mt-auto flex items-center justify-between gap-3 text-sm">
            <USwitch
              :model-value="card.active"
              label="Scanner automatiquement"
              :ui="{ label: 'text-muted font-normal' }"
              @update:model-value="(value) => toggleActive(card, value)"
            />
            <NuxtLink
              v-if="card.listing_count"
              :to="{ path: '/affaires', query: { carte: card.id } }"
              class="text-primary hover:underline"
            >
              {{ card.listing_count }} annonce{{ card.listing_count > 1 ? 's' : '' }}
            </NuxtLink>
            <span v-else class="text-dimmed">aucune annonce</span>
          </div>
          <p class="-mt-2 text-xs text-dimmed">
            {{
              card.last_scanned_at
                ? `scannée ${formatDateTime(card.last_scanned_at)}`
                : 'jamais scannée'
            }}
          </p>
        </article>
      </div>

      <TrackedCardModal v-model:open="modalOpen" :card="editing" @saved="() => refresh()" />
    </template>
  </UDashboardPanel>
</template>
