<script setup lang="ts">
import type { MarketPrice } from '~/types/engine'

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
</script>

<template>
  <div class="flex h-full flex-col">
    <DrawerHeader
      :title="product?.name ?? 'Carte Cardmarket'"
      :subtitle="subtitle"
      icon="i-lucide-chart-line"
    />

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
          color="warning"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          title="Impression non japonaise"
          description="Sa cote ne correspond pas aux cartes achetées au Japon : cherchez la version japonaise (badge « JP » dans le catalogue)."
        />
        <div class="grid grid-cols-2 gap-2">
          <UButton icon="i-lucide-eye" label="Suivre cette carte" block @click="trackOpen = true" />
          <UButton
            icon="i-lucide-external-link"
            label="Voir sur Cardmarket"
            color="neutral"
            variant="subtle"
            block
            @click="openExternal(product.url)"
          />
        </div>

        <section class="space-y-2">
          <h3 class="text-xs font-semibold tracking-wider text-muted uppercase">
            Faut-il l’acheter ?
          </h3>
          <CardVerdictPanel :query="{ product_id: product.id_product }" />
        </section>

        <section class="space-y-2">
          <h3 class="text-xs font-semibold tracking-wider text-muted uppercase">Cote Cardmarket</h3>
          <div class="grid grid-cols-2 gap-2">
            <InfoTile
              v-for="price in prices"
              :key="price.field"
              :label="price.label"
              :value="formatCents(price.cents)"
              :hint="
                price.field === product.reference_field ? 'Cote de revente utilisée' : undefined
              "
              :value-class="price.field === product.reference_field ? 'text-primary' : undefined"
            />
          </div>
          <p v-if="product.prices_date" class="text-xs text-muted">
            Cotes du {{ formatDate(product.prices_date) }}, toutes langues et tous états confondus.
          </p>
        </section>
      </template>

      <div v-else class="flex justify-center py-12">
        <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-muted" />
      </div>
    </div>

    <TrackedCardModal
      v-model:open="trackOpen"
      :initial="product ? { game: product.game } : null"
      :initial-product="product"
    />
  </div>
</template>
