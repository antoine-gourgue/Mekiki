<script setup lang="ts">
import type { AppSettings } from '~/types/engine'

/** What buying in Japan costs: exchange rate and Neokyo's fees, taken up by each new lot. */
const settings = defineModel<AppSettings>({ required: true })

const fxFormat: Intl.NumberFormatOptions = { maximumFractionDigits: 4 }
</script>

<template>
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
          v-model="settings.fx_jpy_per_eur"
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
        <MoneyInput v-model="settings.neokyo_service_fee_jpy" currency="JPY" />
      </UFormField>
      <UFormField label="Emballage Neokyo" hint="par colis">
        <MoneyInput v-model="settings.neokyo_packing_fee_jpy" currency="JPY" />
      </UFormField>
    </div>
  </UCard>
</template>
