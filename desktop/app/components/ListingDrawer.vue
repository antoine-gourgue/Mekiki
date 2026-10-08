<script setup lang="ts">
import type { ListingPreview } from '~/composables/useDrawer'

/** Side panel of a listing to buy in Japan: is its price worth it? */
const props = defineProps<{ listing: ListingPreview }>()

const engine = useEngine()

// The product's Cardmarket page, loaded ahead so the link opens on the first click.
const cardmarketUrl = ref<string | null>(null)
watch(
  () => props.listing.product_id,
  async (id) => {
    cardmarketUrl.value = null
    if (id == null) return
    try {
      cardmarketUrl.value = (await engine.getProduct(id)).url
    } catch {
      // Without the product, the link is simply not shown.
    }
  },
  { immediate: true },
)

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
        <button
          type="button"
          class="flex h-44 w-32 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-accented bg-elevated"
          aria-label="Voir l’annonce"
          @click="openExternal(listing.url)"
        >
          <img
            v-if="listing.thumbnail_url"
            :src="listing.thumbnail_url"
            :alt="listing.title"
            referrerpolicy="no-referrer"
            class="size-full object-cover"
          />
          <UIcon v-else name="i-lucide-image-off" class="size-6 text-dimmed" />
        </button>
        <div class="flex min-w-0 flex-1 flex-col">
          <p class="line-clamp-3 text-sm text-toned" :title="listing.title">{{ listing.title }}</p>
          <p class="mt-3 text-3xl font-semibold tracking-tight text-highlighted tabular-nums">
            {{ formatYen(listing.price_jpy) }}
          </p>
          <p class="mt-1 text-sm text-dimmed">
            {{
              listing.shipping_included
                ? 'port compris'
                : listing.shipping_included === false
                  ? '+ port au Japon'
                  : 'port non précisé'
            }}
          </p>
          <UButton
            v-if="cardmarketUrl"
            icon="i-lucide-chart-line"
            trailing-icon="i-lucide-arrow-up-right"
            label="Voir sur Cardmarket"
            color="neutral"
            variant="link"
            size="sm"
            class="mt-auto self-start px-0"
            @click="openExternal(cardmarketUrl)"
          />
        </div>
      </div>

      <section class="space-y-2.5">
        <h3 class="text-xs font-semibold tracking-[0.12em] text-dimmed uppercase">
          Faut-il l’acheter ?
        </h3>
        <CardVerdictPanel :query="verdictQuery" />
      </section>
    </div>

    <div class="flex gap-2.5 border-t border-default px-4 py-4 sm:px-6">
      <UButton
        icon="i-lucide-external-link"
        label="Voir l’annonce"
        color="neutral"
        variant="outline"
        size="xl"
        class="flex-1 justify-center"
        @click="openExternal(listing.url)"
      />
      <UButton
        v-if="listing.neokyo_url"
        trailing-icon="i-lucide-arrow-up-right"
        label="Acheter via Neokyo"
        size="xl"
        class="flex-[2] justify-center"
        @click="openExternal(listing.neokyo_url)"
      />
    </div>
  </div>
</template>
