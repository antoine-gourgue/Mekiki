<script setup lang="ts">
import type { AppSettings, SalePlatform } from '~/types/engine'

const engine = useEngine()
const showError = useErrorToast()
const toast = useToast()

const { data: saved, error, refresh } = useAsyncData('settings', () => engine.getSettings())

const state = ref<AppSettings | null>(null)
watch(saved, (value) => (state.value = value ? structuredClone(toRaw(value)) : null), {
  immediate: true,
})

const dirty = computed(() => JSON.stringify(state.value) !== JSON.stringify(saved.value))
const saving = ref(false)

async function save() {
  if (!state.value) return
  saving.value = true
  try {
    saved.value = await engine.saveSettings(state.value)
    toast.add({ title: 'Paramètres enregistrés', color: 'success' })
  } catch (failure) {
    showError(failure)
  } finally {
    saving.value = false
  }
}

const platforms = Object.keys(PLATFORM_LABELS) as SalePlatform[]
const platformItems = selectItems(PLATFORM_LABELS)
const fxFormat: Intl.NumberFormatOptions = { maximumFractionDigits: 4 }

const sections = [
  { id: 'entreprise', label: 'Entreprise' },
  { id: 'achat', label: 'Achat au Japon' },
  { id: 'import', label: 'Import' },
  { id: 'revente', label: 'Revente et cotisations' },
  { id: 'ebay', label: 'Clés eBay' },
  { id: 'scanner', label: 'Scanner' },
  { id: 'sauvegardes', label: 'Sauvegardes' },
]
// The panel body scrolls, not the window: a #hash link would not move it.
function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<template>
  <UDashboardPanel id="settings">
    <template #header>
      <PageNavbar
        title="Paramètres"
        description="Ils servent à chiffrer chaque annonce, chaque colis et chaque vente."
      >
        <template #right>
          <span v-if="dirty" class="text-sm text-error">Modifications non enregistrées</span>
          <UButton
            label="Enregistrer"
            icon="i-lucide-save"
            :disabled="!dirty"
            :loading="saving"
            @click="save"
          />
        </template>
      </PageNavbar>
    </template>

    <template #body>
      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="Impossible de charger les paramètres"
        :description="engineErrorMessage(error)"
        :actions="[{ label: 'Réessayer', onClick: () => refresh() }]"
      />

      <div v-else-if="state" class="flex items-start gap-6">
        <nav
          aria-label="Sections des paramètres"
          class="sticky top-0 hidden w-48 shrink-0 flex-col gap-0.5 text-sm lg:flex"
        >
          <button
            v-for="section in sections"
            :key="section.id"
            type="button"
            class="flex h-9 items-center rounded-md px-3 text-left text-muted transition-colors hover:bg-elevated/50 hover:text-highlighted"
            @click="scrollTo(section.id)"
          >
            {{ section.label }}
          </button>
        </nav>

        <div class="min-w-0 flex-1 space-y-4">
          <BusinessCard v-if="state.business" v-model="state.business" />

          <UCard id="achat" :ui="{ body: 'space-y-4 sm:p-5' }">
            <div>
              <h2 class="font-semibold text-highlighted">Achat au Japon</h2>
              <p class="mt-1 text-sm text-dimmed">
                Valeurs reprises à la création d’un lot ou d’une carte.
              </p>
            </div>
            <div class="grid gap-4 sm:grid-cols-3">
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
                  class="w-full"
                />
              </UFormField>
              <UFormField label="Frais de service Neokyo" hint="par article">
                <MoneyInput v-model="state.neokyo_service_fee_jpy" currency="JPY" />
              </UFormField>
              <UFormField label="Emballage Neokyo" hint="par colis">
                <MoneyInput v-model="state.neokyo_packing_fee_jpy" currency="JPY" />
              </UFormField>
            </div>
          </UCard>

          <UCard id="import" :ui="{ body: 'space-y-4 sm:p-5' }">
            <div>
              <h2 class="font-semibold text-highlighted">Import</h2>
              <p class="mt-1 text-sm text-dimmed">
                La TVA est estimée tant que la facture du transporteur n’est pas saisie.
              </p>
            </div>
            <div class="grid gap-4 sm:grid-cols-3">
              <UFormField label="TVA à l’import">
                <PercentInput v-model="state.vat_rate_percent" />
              </UFormField>
              <UFormField label="Frais de dossier" hint="par colis">
                <MoneyInput v-model="state.default_handling_fee_cents" currency="EUR" />
              </UFormField>
            </div>
          </UCard>

          <UCard id="revente" :ui="{ body: 'space-y-4 sm:p-5' }">
            <div>
              <h2 class="font-semibold text-highlighted">Revente et cotisations</h2>
              <p class="mt-1 text-sm text-dimmed">
                Les ventes déjà enregistrées gardent leurs frais et leur taux de cotisation.
              </p>
            </div>
            <div class="grid gap-4 sm:grid-cols-3">
              <UFormField label="Cotisations URSSAF" hint="sur le CA">
                <PercentInput v-model="state.contribution_rate_percent" />
              </UFormField>
              <UFormField label="Versement libératoire" hint="0 si non choisi">
                <PercentInput v-model="state.income_tax_rate_percent" />
              </UFormField>
              <UFormField label="Emballage" hint="par envoi">
                <MoneyInput v-model="state.default_packaging_cents" currency="EUR" />
              </UFormField>
            </div>

            <div class="overflow-hidden rounded-lg border border-default">
              <div
                class="grid grid-cols-[8rem_1fr_1fr_auto] gap-3 bg-default px-4 py-2.5 text-xs text-dimmed"
              >
                <span>Frais par plateforme</span>
                <span>Commission</span>
                <span>Frais fixes</span>
                <span>Port facturé</span>
              </div>
              <div
                v-for="platform in platforms"
                :key="platform"
                class="grid grid-cols-[8rem_1fr_1fr_auto] items-center gap-3 border-t border-muted px-4 py-2.5"
              >
                <span class="text-sm font-medium">{{ PLATFORM_LABELS[platform] }}</span>
                <PercentInput
                  v-model="state.platform_fees[platform].percent"
                  :aria-label="`Commission ${PLATFORM_LABELS[platform]}`"
                />
                <MoneyInput
                  v-model="state.platform_fees[platform].fixed_cents"
                  currency="EUR"
                  :aria-label="`Frais fixes ${PLATFORM_LABELS[platform]}`"
                />
                <UCheckbox
                  v-model="state.platform_fees[platform].applies_to_shipping"
                  label="Inclus"
                  :aria-label="`Commission ${PLATFORM_LABELS[platform]} sur le port facturé`"
                />
              </div>
            </div>
          </UCard>

          <EbayKeysCard />

          <UCard id="scanner" :ui="{ body: 'space-y-4 sm:p-5' }">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 class="font-semibold text-highlighted">Scanner de bonnes affaires</h2>
                <p class="mt-1 text-sm text-dimmed">
                  Cherche les cartes suivies sur les sites japonais et chiffre chaque annonce comme
                  une carte d’un colis type.
                </p>
              </div>
              <USwitch
                v-model="state.scanner.enabled"
                label="Scanner automatiquement"
                description="Tant que l’application est ouverte."
              />
            </div>
            <div class="grid gap-4 sm:grid-cols-3">
              <UFormField label="Intervalle" hint="minutes">
                <UInputNumber
                  v-model="state.scanner.interval_minutes"
                  :min="10"
                  :max="1440"
                  :step="5"
                  class="w-full"
                />
              </UFormField>
              <UFormField label="ROI visé">
                <PercentInput v-model="state.scanner.min_roi_percent" :max="1000" />
              </UFormField>
              <UFormField label="Revente sur">
                <USelect
                  v-model="state.scanner.resale_platform"
                  :items="platformItems"
                  class="w-full"
                />
              </UFormField>
              <UFormField label="Cartes par colis">
                <UInputNumber
                  v-model="state.scanner.cards_per_lot"
                  :min="1"
                  :max="500"
                  class="w-full"
                />
              </UFormField>
              <UFormField label="Envoi du colis">
                <MoneyInput v-model="state.scanner.lot_shipping_jpy" currency="JPY" />
              </UFormField>
              <UFormField label="Port au Japon" hint="si non compris">
                <MoneyInput v-model="state.scanner.domestic_shipping_jpy" currency="JPY" />
              </UFormField>
            </div>
            <UFormField label="Sites">
              <UCheckboxGroup
                v-model="state.scanner.sources"
                :items="SCANNABLE_SOURCE_ITEMS"
                variant="card"
                orientation="horizontal"
                :ui="{
                  fieldset: 'flex flex-wrap gap-2',
                  item: 'bg-default py-2.5',
                  description: 'text-xs',
                }"
              />
            </UFormField>
            <UFormField
              label="Mots exclus partout"
              help="Lots, accessoires, contrefaçons, éditions étrangères… séparés par des espaces."
            >
              <UTextarea
                v-model="state.scanner.excluded_keywords"
                :rows="2"
                autoresize
                class="w-full"
              />
            </UFormField>
          </UCard>

          <BackupsCard />
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
