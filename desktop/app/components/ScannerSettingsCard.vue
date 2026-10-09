<script setup lang="ts">
import type { AppSettings } from '~/types/engine'

/** How the deals scanner prices a listing, and where and how often it looks. */
const settings = defineModel<AppSettings>({ required: true })

const platformItems = selectItems(PLATFORM_LABELS)
</script>

<template>
  <UCard id="scanner" :ui="{ body: 'space-y-4 sm:p-5' }">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="font-semibold text-highlighted">Scanner de bonnes affaires</h2>
        <p class="mt-1 text-sm text-dimmed">
          Cherche les cartes suivies sur les sites japonais et chiffre chaque annonce comme une
          carte d’un colis type.
        </p>
      </div>
      <USwitch
        v-model="settings.scanner.enabled"
        label="Scanner automatiquement"
        description="Tant que l’application est ouverte."
      />
    </div>
    <div class="grid gap-4 sm:grid-cols-3">
      <UFormField label="Intervalle" hint="minutes">
        <UInputNumber
          v-model="settings.scanner.interval_minutes"
          :min="10"
          :max="1440"
          :step="5"
          class="w-full"
        />
      </UFormField>
      <UFormField label="ROI visé">
        <PercentInput v-model="settings.scanner.min_roi_percent" :max="1000" />
      </UFormField>
      <UFormField label="Revente sur">
        <USelect v-model="settings.scanner.resale_platform" :items="platformItems" class="w-full" />
      </UFormField>
      <UFormField label="Cartes par colis">
        <UInputNumber v-model="settings.scanner.cards_per_lot" :min="1" :max="500" class="w-full" />
      </UFormField>
      <UFormField label="Envoi du colis">
        <MoneyInput v-model="settings.scanner.lot_shipping_jpy" currency="JPY" />
      </UFormField>
      <UFormField label="Port au Japon" hint="si non compris">
        <MoneyInput v-model="settings.scanner.domestic_shipping_jpy" currency="JPY" />
      </UFormField>
    </div>
    <UFormField label="Sites">
      <UCheckboxGroup
        v-model="settings.scanner.sources"
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
      <UTextarea v-model="settings.scanner.excluded_keywords" :rows="2" autoresize class="w-full" />
    </UFormField>
  </UCard>
</template>
