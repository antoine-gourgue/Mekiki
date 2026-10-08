<script setup lang="ts">
import type { ListingSort } from '~/composables/useListingFilter'
import type { ListingCondition } from '~/types/engine'

/** Minimum condition and sort order of a list of listings (see useListingFilter). */
defineProps<{ hidden: number; hiddenWithoutCondition: boolean }>()
const minCondition = defineModel<ListingCondition | 'all'>('minCondition', { required: true })
const sortBy = defineModel<ListingSort>('sortBy', { required: true })
</script>

<template>
  <div class="flex flex-wrap items-center gap-2.5">
    <USelect
      v-model="minCondition"
      :items="MIN_CONDITION_ITEMS"
      icon="i-lucide-sparkles"
      class="w-56"
      aria-label="État minimum"
    />
    <USelect
      v-model="sortBy"
      :items="LISTING_SORT_ITEMS"
      icon="i-lucide-arrow-down-wide-narrow"
      class="w-48"
      aria-label="Trier par"
    />
    <p v-if="hidden" class="text-sm text-dimmed">
      {{ hidden }} masquée{{ hidden > 1 ? 's' : '' }} par l’état
      <template v-if="hiddenWithoutCondition">
        · Rakuma n’indique pas l’état dans ses résultats
      </template>
    </p>
  </div>
</template>
