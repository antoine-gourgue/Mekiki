<script setup lang="ts">
import type { ListingPreview } from '~/composables/useDrawer'
import type { ListingAvailability } from '~/types/engine'

/**
 * Side panel of a listing to buy in Japan: is it still for sale, in what condition, and is
 * its price worth it?
 */
const props = defineProps<{ listing: ListingPreview }>()

const engine = useEngine()
const blockSeller = useBlockSeller()
const emit = defineEmits<{ blocked: [] }>()
const drawer = useDrawer()

async function blockThisSeller() {
  const blocked = await blockSeller(props.listing, {
    sellerId: availability.value?.seller_id,
    reason: availability.value?.seller_warning ?? undefined,
  })
  if (!blocked) return
  emit('blocked')
  drawer.close()
}

// Results age (a discovery is kept, a favorite stays): the marketplace is asked again.
const availability = ref<ListingAvailability | null>(null)
const checking = ref(false)
watch(
  () => `${props.listing.source}:${props.listing.external_id}`,
  async () => {
    availability.value = null
    checking.value = true
    try {
      availability.value = await engine.listingAvailability(
        props.listing.source,
        props.listing.external_id,
      )
    } catch (error) {
      availability.value = {
        available: null,
        status: `vérification impossible : ${engineErrorMessage(error)}`,
        condition: null,
        price_jpy: null,
        checked_at: new Date().toISOString(),
      }
    } finally {
      checking.value = false
    }
  },
  { immediate: true },
)

const condition = computed(() => availability.value?.condition ?? props.listing.condition)
const priceChanged = computed(() => {
  const now = availability.value?.price_jpy
  return availability.value?.available && now != null && now !== props.listing.price_jpy
    ? now
    : null
})

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
          <div class="mt-2.5 flex flex-wrap items-center gap-1.5">
            <UBadge
              v-if="condition"
              :color="CONDITION_COLORS[condition]"
              variant="soft"
              :label="CONDITION_LABELS[condition]"
            />
            <span v-if="condition" class="text-xs text-dimmed">
              {{ CONDITION_JAPANESE[condition] }}
            </span>
            <span v-else-if="!checking" class="text-xs text-dimmed">état non précisé</span>
          </div>
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

      <p v-if="checking" class="flex items-center gap-2 text-sm text-muted">
        <UIcon name="i-lucide-loader-circle" class="size-4 animate-spin" />
        Vérification sur {{ SOURCE_LABELS[listing.source] }}…
      </p>
      <UAlert
        v-else-if="availability?.available === false"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-x"
        :title="`Plus disponible : ${availability.status}`"
        description="Elle a été vendue ou retirée depuis qu’elle a été trouvée."
      />
      <p v-else-if="availability?.available" class="flex items-center gap-2 text-sm text-success">
        <UIcon name="i-lucide-circle-check" class="size-4" />
        En vente sur {{ SOURCE_LABELS[listing.source] }}, vérifiée à l’instant
        <span v-if="priceChanged" class="text-warning">
          · prix actuel {{ formatYen(priceChanged) }}
        </span>
      </p>
      <p
        v-if="availability?.seller_note && !availability.seller_warning"
        class="flex items-center gap-2 text-sm text-muted"
      >
        <UIcon name="i-lucide-star-half" class="size-4" />
        Vendeur : {{ availability.seller_note }}
      </p>
      <p v-else-if="availability" class="flex items-center gap-2 text-sm text-dimmed">
        <UIcon name="i-lucide-circle-help" class="size-4" />
        Disponibilité non vérifiée : {{ availability.status }}
      </p>
      <UAlert
        v-if="availability?.seller_warning"
        color="warning"
        variant="subtle"
        icon="i-lucide-user-x"
        title="Neokyo refusera sans doute ce vendeur"
        :description="`Le vendeur ${availability.seller_warning}.`"
        :actions="[
          {
            label: 'Ne plus proposer ce vendeur',
            color: 'neutral',
            variant: 'outline',
            onClick: blockThisSeller,
          },
        ]"
      />

      <ListingDescription v-if="availability?.description" :text="availability.description" />

      <section class="space-y-2.5">
        <h3 class="text-xs font-semibold tracking-[0.12em] text-dimmed uppercase">
          Faut-il l’acheter ?
        </h3>
        <CardVerdictPanel :query="verdictQuery" />
      </section>
    </div>

    <div class="flex flex-wrap gap-2.5 border-t border-default px-4 py-4 sm:px-6">
      <UButton
        v-if="listing.source === 'mercari' || listing.source === 'rakuma'"
        icon="i-lucide-ban"
        label="Bloquer ce vendeur (refusé par Neokyo)"
        color="neutral"
        variant="ghost"
        size="xl"
        class="basis-full justify-center"
        @click="blockThisSeller"
      />
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
        :label="availability?.available === false ? 'Plus en vente' : 'Acheter via Neokyo'"
        :disabled="availability?.available === false"
        size="xl"
        class="flex-[2] justify-center"
        @click="openExternal(listing.neokyo_url)"
      />
    </div>
  </div>
</template>
