<script setup lang="ts">
import type { BusinessSettings } from '~/types/engine'

/** The micro-enterprise's identity and declaration rhythm, edited with the other settings. */
const business = defineModel<BusinessSettings>({ required: true })

const declarationItems = [
  { value: 'monthly', label: 'Chaque mois' },
  { value: 'quarterly', label: 'Chaque trimestre' },
] as const
</script>

<template>
  <UCard id="entreprise" :ui="{ body: 'space-y-4 sm:p-5' }">
    <div>
      <h2 class="font-semibold text-highlighted">Entreprise</h2>
      <p class="mt-1 text-sm text-dimmed">
        Votre micro-entreprise : Mekiki en tient les registres et prépare vos déclarations URSSAF.
      </p>
    </div>
    <div class="grid gap-4 sm:grid-cols-2">
      <UFormField label="Nom de l’entreprise">
        <UInput v-model="business.name" placeholder="Antoine Dupont EI" class="w-full" />
      </UFormField>
      <UFormField label="SIRET" hint="14 chiffres">
        <UInput
          v-model="business.siret"
          inputmode="numeric"
          placeholder="123 456 789 00012"
          class="w-full"
        />
      </UFormField>
      <UFormField label="Début d’activité">
        <UInput
          :model-value="business.started_on ?? ''"
          type="date"
          class="w-full"
          @update:model-value="(value) => (business.started_on = String(value) || null)"
        />
      </UFormField>
      <UFormField label="Déclaration du chiffre d’affaires">
        <SegmentedControl
          v-model="business.declaration"
          :items="[...declarationItems]"
          label="Déclaration du chiffre d’affaires"
          class="flex w-full *:flex-1"
        />
      </UFormField>
      <UFormField label="Plafond de la micro-entreprise" hint="vente de marchandises, par an">
        <MoneyInput v-model="business.turnover_limit_cents" currency="EUR" />
      </UFormField>
      <UFormField label="Seuil de franchise de TVA" hint="vente de marchandises, par an">
        <MoneyInput v-model="business.vat_franchise_limit_cents" currency="EUR" />
      </UFormField>
    </div>
    <p class="text-xs text-dimmed">
      Plafonds et seuils sont fixés par la loi et révisés régulièrement : vérifiez-les sur
      <ULink
        as="button"
        class="text-primary"
        @click="openExternal('https://www.autoentrepreneur.urssaf.fr')"
        >autoentrepreneur.urssaf.fr</ULink
      >.
    </p>
  </UCard>
</template>
