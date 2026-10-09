<script setup lang="ts">
import type { AppSettings } from '~/types/engine'

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

const sections = [
  { id: 'entreprise', label: 'Entreprise' },
  { id: 'achat', label: 'Achat au Japon' },
  { id: 'import', label: 'Import' },
  { id: 'revente', label: 'Revente et cotisations' },
  { id: 'ebay', label: 'Clés eBay' },
  { id: 'scanner', label: 'Scanner' },
  { id: 'vendeurs', label: 'Vendeurs bloqués' },
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

          <BuyingSettingsCard v-model="state" />

          <ImportSettingsCard v-model="state" />

          <SellingSettingsCard v-model="state" />

          <EbayKeysCard />

          <ScannerSettingsCard v-model="state" />

          <BlockedSellersCard />

          <BackupsCard />
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
