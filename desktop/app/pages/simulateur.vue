<script setup lang="ts">
import type { SalePlatform, SimulationRequest, SimulationResult } from '~/types/engine'

const engine = useEngine()

interface SimulatorForm {
  price_jpy: number | null
  domestic_shipping_jpy: number | null
  sale_price_cents: number | null
  platform: SalePlatform
  shipping_charged_cents: number | null
  shipping_cost_cents: number | null
  cards_in_lot: number | null
  lot_shipping_jpy: number | null
  target_roi_percent: number | null
  fx_jpy_per_eur: number | null
}

const state = reactive<SimulatorForm>({
  price_jpy: null,
  domestic_shipping_jpy: 0,
  sale_price_cents: null,
  platform: 'cardmarket',
  shipping_charged_cents: 0,
  shipping_cost_cents: 0,
  cards_in_lot: 10,
  lot_shipping_jpy: 4000,
  target_roi_percent: 30,
  // Left empty, the engine uses the rate from the settings.
  fx_jpy_per_eur: null,
})

const result = ref<SimulationResult | null>(null)
const failure = ref<string | null>(null)
const loading = ref(false)

const request = computed<SimulationRequest | null>(() => {
  if (state.price_jpy == null || state.sale_price_cents == null) return null
  return {
    price_jpy: state.price_jpy,
    domestic_shipping_jpy: state.domestic_shipping_jpy ?? 0,
    sale_price_cents: state.sale_price_cents,
    platform: state.platform,
    shipping_charged_cents: state.shipping_charged_cents ?? 0,
    shipping_cost_cents: state.shipping_cost_cents ?? 0,
    cards_in_lot: Math.max(1, state.cards_in_lot ?? 1),
    lot_shipping_jpy: state.lot_shipping_jpy ?? 0,
    target_roi_percent: state.target_roi_percent,
    fx_jpy_per_eur: state.fx_jpy_per_eur,
  }
})

// Recomputed as you type, so an ad can be judged in a few seconds.
let debounce: ReturnType<typeof setTimeout> | undefined
let latest = 0
watch(
  request,
  (body) => {
    clearTimeout(debounce)
    if (!body) {
      result.value = null
      return
    }
    debounce = setTimeout(async () => {
      const call = ++latest
      loading.value = true
      try {
        const response = await engine.simulate(body)
        if (call === latest) {
          result.value = response
          failure.value = null
        }
      } catch (error) {
        if (call === latest) failure.value = engineErrorMessage(error)
      } finally {
        if (call === latest) loading.value = false
      }
    }, 250)
  },
  { deep: true },
)

const verdict = computed(() => {
  const sale = result.value?.sale
  if (!sale || sale.roi == null) return null
  const target = (state.target_roi_percent ?? 0) / 100
  if (sale.margin_cents < 0) return { label: 'À perte', color: 'error' as const }
  if (sale.roi >= target) return { label: 'Bonne affaire', color: 'success' as const }
  return { label: 'Marge trop faible', color: 'warning' as const }
})

const platformItems = selectItems(PLATFORM_LABELS)
const fxFormat: Intl.NumberFormatOptions = { maximumFractionDigits: 4 }
</script>

<template>
  <UDashboardPanel id="simulator">
    <template #header>
      <UDashboardNavbar title="Simulateur">
        <template #leading><UDashboardSidebarCollapse /></template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <UCard>
          <template #header>
            <h2 class="font-medium text-highlighted">L’annonce</h2>
            <p class="text-sm text-muted">Une carte achetée dans un colis de cartes identiques.</p>
          </template>

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Prix de l’annonce">
              <MoneyInput v-model="state.price_jpy" currency="JPY" autofocus />
            </UFormField>
            <UFormField label="Port au Japon">
              <MoneyInput v-model="state.domestic_shipping_jpy" currency="JPY" />
            </UFormField>
            <UFormField label="Prix de revente visé">
              <MoneyInput v-model="state.sale_price_cents" currency="EUR" />
            </UFormField>
            <UFormField label="Plateforme">
              <USelect v-model="state.platform" :items="platformItems" class="w-full" />
            </UFormField>
          </div>

          <USeparator label="Colis et objectif" class="my-6" />

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="Cartes dans le colis">
              <UInputNumber v-model="state.cards_in_lot" :min="1" :max="500" class="w-full" />
            </UFormField>
            <UFormField label="Envoi du colis" hint="assurance comprise">
              <MoneyInput v-model="state.lot_shipping_jpy" currency="JPY" />
            </UFormField>
            <UFormField label="ROI visé">
              <PercentInput v-model="state.target_roi_percent" :max="1000" />
            </UFormField>
            <UFormField label="Taux de change" hint="¥ pour 1 €">
              <UInputNumber
                v-model="state.fx_jpy_per_eur"
                :format-options="fxFormat"
                locale="fr-FR"
                :min="0.0001"
                :step="0.0001"
                :step-snapping="false"
                :increment="false"
                :decrement="false"
                :placeholder="
                  result ? `${result.fx_jpy_per_eur} (paramètres)` : 'Taux des paramètres'
                "
                class="w-full"
              />
            </UFormField>
            <UFormField label="Port payé par l’acheteur">
              <MoneyInput v-model="state.shipping_charged_cents" currency="EUR" />
            </UFormField>
            <UFormField label="Coût réel de l’envoi">
              <MoneyInput v-model="state.shipping_cost_cents" currency="EUR" />
            </UFormField>
          </div>
        </UCard>

        <div class="space-y-6">
          <UAlert v-if="failure" color="error" variant="subtle" :description="failure" />

          <UEmpty
            v-if="!result"
            icon="i-lucide-calculator"
            title="Entrez un prix d’achat et un prix de revente"
            description="Le coût de revient, la marge et le prix maximum s’affichent aussitôt."
          />

          <template v-else>
            <UCard :class="{ 'opacity-60': loading }">
              <div class="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p class="text-sm text-muted">Marge</p>
                  <p class="text-4xl font-semibold" :class="signClass(result.sale.margin_cents)">
                    {{ formatCents(result.sale.margin_cents) }}
                  </p>
                  <p class="mt-1 text-sm text-muted">
                    ROI {{ formatRatio(result.sale.roi) }} · net
                    {{ formatCents(result.sale.net_cents) }}
                  </p>
                </div>
                <UBadge
                  v-if="verdict"
                  :color="verdict.color"
                  variant="subtle"
                  size="lg"
                  :label="verdict.label"
                />
              </div>

              <USeparator class="my-4" />

              <p class="text-sm">
                <template v-if="result.max_price_jpy != null">
                  Prix maximum pour {{ state.target_roi_percent }} % de ROI :
                  <strong class="text-highlighted">{{ formatYen(result.max_price_jpy) }}</strong>
                  <span v-if="state.price_jpy != null" class="text-muted">
                    ({{ result.max_price_jpy >= state.price_jpy ? 'marge de' : 'dépassé de' }}
                    {{ formatYen(Math.abs(result.max_price_jpy - state.price_jpy)) }})
                  </span>
                </template>
                <template v-else-if="state.target_roi_percent != null">
                  Aucun prix d’achat n’atteint {{ state.target_roi_percent }} % de ROI à ce prix de
                  revente.
                </template>
              </p>
            </UCard>

            <div class="grid gap-6 sm:grid-cols-2">
              <UCard>
                <template #header>
                  <h3 class="font-medium text-highlighted">Coût de revient</h3>
                </template>
                <LandedCostBreakdown :cost="result.landed_cost" />
              </UCard>
              <UCard>
                <template #header>
                  <h3 class="font-medium text-highlighted">Vente</h3>
                </template>
                <SaleBreakdownList :sale="result.sale" />
              </UCard>
            </div>
          </template>
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
