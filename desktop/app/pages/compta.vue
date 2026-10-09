<script setup lang="ts">
/**
 * The micro-enterprise's books: turnover and contributions of each period to declare, the
 * yearly thresholds, and the book of receipts and register of purchases for Excel.
 */
const engine = useEngine()

const thisYear = new Date().getFullYear()
const year = ref(thisYear)
const yearItems = [thisYear, thisYear - 1, thisYear - 2].map((value) => ({
  value: String(value),
  label: String(value),
}))
const yearModel = computed({
  get: () => String(year.value),
  set: (value: string) => (year.value = Number(value)),
})

const {
  data: summary,
  error,
  refresh,
} = useAsyncData('books', () => engine.booksSummary(year.value), { watch: [year] })
</script>

<template>
  <UDashboardPanel id="books">
    <template #header>
      <PageNavbar
        title="Comptabilité"
        description="Le chiffre d’affaires à déclarer, vos cotisations et vos registres : Mekiki calcule, vous déclarez."
      >
        <template #right>
          <SegmentedControl v-model="yearModel" :items="yearItems" label="Année" />
        </template>
      </PageNavbar>
    </template>

    <template #body>
      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="Impossible de charger la comptabilité"
        :description="engineErrorMessage(error)"
        :actions="[{ label: 'Réessayer', onClick: () => refresh() }]"
      />

      <BooksView v-else-if="summary" :summary="summary" />
    </template>
  </UDashboardPanel>
</template>
