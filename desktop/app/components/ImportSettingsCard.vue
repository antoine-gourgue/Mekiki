<script setup lang="ts">
import type { AppSettings } from '~/types/engine'

/** What the parcel's import costs before the carrier's invoice is entered. */
const settings = defineModel<AppSettings>({ required: true })
</script>

<template>
  <UCard id="import" :ui="{ body: 'space-y-4 sm:p-5' }">
    <div>
      <h2 class="font-semibold text-highlighted">Import</h2>
      <p class="mt-1 text-sm text-dimmed">
        La TVA est estimée tant que la facture du transporteur n’est pas saisie.
      </p>
    </div>
    <div class="grid gap-4 sm:grid-cols-3">
      <UFormField label="TVA à l’import">
        <PercentInput v-model="settings.vat_rate_percent" />
      </UFormField>
      <UFormField label="Frais de dossier" hint="par colis">
        <MoneyInput v-model="settings.default_handling_fee_cents" currency="EUR" />
      </UFormField>
    </div>
  </UCard>
</template>
