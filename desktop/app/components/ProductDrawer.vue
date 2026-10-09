<script setup lang="ts">
import type { MarketPrice, PricePoint } from '~/types/engine'

/** Side panel of a Cardmarket product: its price guide and European resale prices. */
const props = defineProps<{ id: number }>()

const engine = useEngine()

const product = ref<MarketPrice | null>(null)
const failure = ref<string | null>(null)

async function load() {
  failure.value = null
  try {
    product.value = await engine.getProduct(props.id)
  } catch (error) {
    failure.value = engineErrorMessage(error)
  }
}
watch(() => props.id, load, { immediate: true })

const subtitle = computed(() =>
  product.value
    ? [
        GAME_LABELS[product.value.game],
        product.value.japanese ? 'japonaise' : null,
        product.value.expansion_name,
      ]
        .filter(Boolean)
        .join(' · ')
    : undefined,
)

const prices = computed(() => {
  const p = product.value
  if (!p) return []
  return [
    { field: 'avg30', label: 'Moyenne 30 jours', cents: p.avg30_cents },
    { field: 'avg7', label: 'Moyenne 7 jours', cents: p.avg7_cents },
    { field: 'avg1', label: 'Ventes de la veille', cents: p.avg1_cents },
    { field: 'avg', label: 'Prix moyen', cents: p.avg_cents },
    { field: 'trend', label: 'Tendance', cents: p.trend_cents },
    { field: 'low', label: 'Offre la plus basse', cents: p.low_cents },
  ]
})

const trackOpen = ref(false)

// Recorded each day for the cards tracked or in stock (see the engine's price import).
const history = ref<PricePoint[]>([])
watch(
  () => props.id,
  async (id) => {
    history.value = []
    try {
      history.value = await engine.productHistory(id)
    } catch {
      // The history only adds to the panel: without it, the prices above remain.
    }
  },
  { immediate: true },
)
const change = computed(() => {
  const first = history.value[0]?.cents
  const last = history.value.at(-1)?.cents
  return first && last ? (last - first) / first : null
})
</script>

<template>
  <div class="flex h-full flex-col">
    <DrawerHeader
      :title="product?.name ?? 'Carte Cardmarket'"
      :subtitle="subtitle"
      icon="i-lucide-chart-line"
    >
      <template v-if="product?.japanese" #actions>
        <UBadge color="neutral" variant="soft" label="JP" />
      </template>
    </DrawerHeader>

    <div class="flex-1 space-y-6 overflow-y-auto p-4 sm:p-6">
      <UAlert
        v-if="failure"
        color="error"
        variant="subtle"
        :title="failure"
        :actions="[{ label: 'Réessayer', onClick: () => load() }]"
      />

      <template v-else-if="product">
        <UAlert
          v-if="!product.japanese"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          title="Impression non japonaise"
          description="Sa cote ne correspond pas aux cartes achetées au Japon : cherchez la version japonaise (badge « JP » dans le catalogue)."
        />

        <section class="space-y-2.5">
          <h3 class="text-xs font-semibold tracking-[0.12em] text-dimmed uppercase">
            Faut-il l’acheter ?
          </h3>
          <CardVerdictPanel :query="{ product_id: product.id_product }" />
        </section>

        <section class="space-y-2.5">
          <h3 class="text-xs font-semibold tracking-[0.12em] text-dimmed uppercase">
            Cote Cardmarket
          </h3>
          <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <div
              v-for="price in prices"
              :key="price.field"
              class="rounded-lg px-3 py-2.5"
              :class="
                price.field === product.reference_field
                  ? 'bg-primary/10 ring-1 ring-primary/40'
                  : 'bg-elevated'
              "
            >
              <p class="text-xs text-muted">{{ price.label }}</p>
              <p class="mt-0.5 font-semibold text-highlighted tabular-nums">
                {{ formatCents(price.cents) }}
              </p>
              <p v-if="price.field === product.reference_field" class="text-[11px] text-primary">
                cote de revente
              </p>
            </div>
          </div>
          <p v-if="product.prices_date" class="text-xs text-dimmed">
            Cotes du {{ formatDate(product.prices_date) }}, toutes langues et tous états confondus.
          </p>
        </section>

        <section class="space-y-2.5">
          <div class="flex items-baseline justify-between gap-3">
            <h3 class="text-xs font-semibold tracking-[0.12em] text-dimmed uppercase">
              Évolution de la cote
            </h3>
            <span
              v-if="change != null && history.length > 1"
              class="text-xs font-semibold tabular-nums"
              :class="signClass(change)"
            >
              {{ change > 0 ? '+' : '' }}{{ formatRatio(change) }} depuis le
              {{ formatDate(history[0]?.date) }}
            </span>
          </div>
          <PriceHistoryChart v-if="history.length > 1" :points="history" />
          <p v-else class="text-sm text-muted">
            Mekiki relève la cote chaque jour pour les cartes suivies et celles de votre stock :
            suivez cette carte pour voir son évolution.
          </p>
        </section>
      </template>

      <div v-else class="flex justify-center py-12">
        <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-muted" />
      </div>
    </div>

    <div v-if="product" class="flex gap-2.5 border-t border-default px-4 py-4 sm:px-6">
      <UButton
        icon="i-lucide-external-link"
        label="Voir sur Cardmarket"
        color="neutral"
        variant="outline"
        size="xl"
        class="flex-1 justify-center"
        @click="openExternal(product.url)"
      />
      <UButton
        icon="i-lucide-eye"
        label="Suivre cette carte"
        size="xl"
        class="flex-1 justify-center"
        @click="trackOpen = true"
      />
    </div>

    <TrackedCardModal
      v-model:open="trackOpen"
      :initial="product ? { game: product.game } : null"
      :initial-product="product"
    />
  </div>
</template>
