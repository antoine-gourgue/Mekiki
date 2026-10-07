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
const fxFormat: Intl.NumberFormatOptions = { maximumFractionDigits: 4 }
</script>

<template>
  <UDashboardPanel id="settings">
    <template #header>
      <UDashboardNavbar title="Paramètres">
        <template #leading><UDashboardSidebarCollapse /></template>
        <template #right>
          <UButton
            label="Enregistrer"
            icon="i-lucide-save"
            :disabled="!dirty"
            :loading="saving"
            @click="save"
          />
        </template>
      </UDashboardNavbar>
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

      <div v-else-if="state" class="mx-auto w-full max-w-3xl space-y-6">
        <UCard>
          <template #header>
            <h2 class="font-medium text-highlighted">Achat au Japon</h2>
            <p class="text-sm text-muted">
              Valeurs reprises à la création d’un lot ou d’une carte.
            </p>
          </template>
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

        <UCard>
          <template #header>
            <h2 class="font-medium text-highlighted">Import</h2>
            <p class="text-sm text-muted">
              La TVA est estimée tant que la facture du transporteur n’est pas saisie.
            </p>
          </template>
          <div class="grid gap-4 sm:grid-cols-3">
            <UFormField label="TVA à l’import">
              <PercentInput v-model="state.vat_rate_percent" />
            </UFormField>
            <UFormField label="Frais de dossier" hint="par colis">
              <MoneyInput v-model="state.default_handling_fee_cents" currency="EUR" />
            </UFormField>
          </div>
        </UCard>

        <UCard>
          <template #header>
            <h2 class="font-medium text-highlighted">Revente</h2>
            <p class="text-sm text-muted">
              Les ventes déjà enregistrées gardent leurs frais et leur taux de cotisation.
            </p>
          </template>
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

          <USeparator label="Frais par plateforme" class="my-6" />

          <div class="space-y-3">
            <div
              v-for="platform in platforms"
              :key="platform"
              class="grid items-center gap-3 sm:grid-cols-[8rem_1fr_1fr_auto]"
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
                label="Port inclus"
              />
            </div>
            <p class="text-xs text-muted">
              Commission en %, frais fixes par vente, et prise en compte ou non du port facturé.
            </p>
          </div>
        </UCard>
      </div>
    </template>
  </UDashboardPanel>
</template>
