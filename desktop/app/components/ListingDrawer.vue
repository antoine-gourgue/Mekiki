<script setup lang="ts">
import type { ListingPreview } from '~/composables/useDrawer'

/** Side panel of a listing to buy in Japan: is its price worth it? */
const props = defineProps<{ listing: ListingPreview }>()

const drawer = useDrawer()

const subtitle = computed(() =>
  [SOURCE_LABELS[props.listing.source], GAME_LABELS[props.listing.game]].join(' · '),
)

const verdictQuery = computed(() => ({
  ...(props.listing.product_id
    ? { product_id: props.listing.product_id, label: props.listing.label ?? undefined }
    : { q: props.listing.label ?? props.listing.title }),
  price_jpy: props.listing.price_jpy,
  shipping_included: props.listing.shipping_included ?? undefined,
}))
</script>

<template>
  <div class="flex h-full flex-col">
    <DrawerHeader
      :title="listing.label ?? listing.title"
      :subtitle="subtitle"
      icon="i-lucide-shopping-bag"
    />

    <div class="flex-1 space-y-6 overflow-y-auto p-4 sm:p-6">
      <div class="flex gap-4">
        <div class="size-32 shrink-0 overflow-hidden rounded-md bg-elevated">
          <img
            v-if="listing.thumbnail_url"
            :src="listing.thumbnail_url"
            :alt="listing.title"
            referrerpolicy="no-referrer"
            class="size-full object-cover"
          />
          <UIcon v-else name="i-lucide-image-off" class="m-auto mt-12 size-6 text-muted" />
        </div>
        <div class="min-w-0 flex-1 space-y-2">
          <p class="line-clamp-3 text-sm" :title="listing.title">{{ listing.title }}</p>
          <p class="text-2xl font-semibold tabular-nums">{{ formatYen(listing.price_jpy) }}</p>
          <p class="text-xs text-muted">
            {{
              listing.shipping_included
                ? 'port compris'
                : listing.shipping_included === false
                  ? '+ port au Japon'
                  : 'port non précisé'
            }}
          </p>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-2">
        <UButton
          icon="i-lucide-external-link"
          label="Voir l’annonce"
          color="neutral"
          variant="subtle"
          block
          @click="openExternal(listing.url)"
        />
        <UButton
          v-if="listing.neokyo_url"
          icon="i-lucide-shopping-cart"
          label="Acheter via Neokyo"
          block
          @click="openExternal(listing.neokyo_url)"
        />
        <UButton
          v-if="listing.product_id"
          icon="i-lucide-chart-line"
          label="Fiche Cardmarket"
          color="neutral"
          variant="subtle"
          block
          class="col-span-2"
          @click="drawer.push({ kind: 'product', id: listing.product_id })"
        />
      </div>

      <section class="space-y-2">
        <h3 class="text-xs font-semibold tracking-wider text-muted uppercase">
          Faut-il l’acheter ?
        </h3>
        <CardVerdictPanel :query="verdictQuery" />
      </section>
    </div>
  </div>
</template>
