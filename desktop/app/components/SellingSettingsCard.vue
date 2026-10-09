<script setup lang="ts">
import type { AppSettings, SalePlatform } from '~/types/engine'

/** URSSAF contributions, packaging and each platform's fees, frozen on each sale. */
const settings = defineModel<AppSettings>({ required: true })

const platforms = Object.keys(PLATFORM_LABELS) as SalePlatform[]
</script>

<template>
  <UCard id="revente" :ui="{ body: 'space-y-4 sm:p-5' }">
    <div>
      <h2 class="font-semibold text-highlighted">Revente et cotisations</h2>
      <p class="mt-1 text-sm text-dimmed">
        Les ventes déjà enregistrées gardent leurs frais et leur taux de cotisation.
      </p>
    </div>
    <div class="grid gap-4 sm:grid-cols-3">
      <UFormField label="Cotisations URSSAF" hint="sur le CA">
        <PercentInput v-model="settings.contribution_rate_percent" />
      </UFormField>
      <UFormField label="Versement libératoire" hint="0 si non choisi">
        <PercentInput v-model="settings.income_tax_rate_percent" />
      </UFormField>
      <UFormField label="Emballage" hint="par envoi">
        <MoneyInput v-model="settings.default_packaging_cents" currency="EUR" />
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
          v-model="settings.platform_fees[platform].percent"
          :aria-label="`Commission ${PLATFORM_LABELS[platform]}`"
        />
        <MoneyInput
          v-model="settings.platform_fees[platform].fixed_cents"
          currency="EUR"
          :aria-label="`Frais fixes ${PLATFORM_LABELS[platform]}`"
        />
        <UCheckbox
          v-model="settings.platform_fees[platform].applies_to_shipping"
          label="Inclus"
          :aria-label="`Commission ${PLATFORM_LABELS[platform]} sur le port facturé`"
        />
      </div>
    </div>
  </UCard>
</template>
