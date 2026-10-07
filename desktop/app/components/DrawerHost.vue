<script setup lang="ts">
/** Renders the side panel on top of the drawer stack (see useDrawer). */
const drawer = useDrawer()
const route = useRoute()

// A panel belongs to the page it was opened from.
watch(
  () => route.path,
  () => drawer.close(),
)
</script>

<template>
  <USlideover
    :open="drawer.current.value !== null"
    side="right"
    title="Détail"
    description="Fiche ouverte depuis la recherche ou une liste"
    :ui="{ content: 'w-full max-w-xl' }"
    @update:open="(open) => !open && drawer.close()"
  >
    <template #content>
      <template v-if="drawer.current.value">
        <ItemDrawer
          v-if="drawer.current.value.kind === 'item'"
          :id="drawer.current.value.id"
          :siblings="drawer.current.value.siblings"
        />
        <ProductDrawer
          v-else-if="drawer.current.value.kind === 'product'"
          :id="drawer.current.value.id"
        />
        <ListingDrawer
          v-else-if="drawer.current.value.kind === 'listing'"
          :listing="drawer.current.value.listing"
        />
      </template>
    </template>
  </USlideover>
</template>
