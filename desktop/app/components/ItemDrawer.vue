<script setup lang="ts">
import type { Item, ItemPhoto, MarketPrice } from '~/types/engine'

/** Side panel of a card in stock: what it cost, where it is listed, what it earns. */
const props = defineProps<{ id: number; siblings?: number[] }>()

const engine = useEngine()
const drawer = useDrawer()

const item = ref<Item | null>(null)
const product = ref<MarketPrice | null>(null)
const photos = ref<ItemPhoto[]>([])
const failure = ref<string | null>(null)

async function load() {
  failure.value = null
  try {
    item.value = await engine.getItem(props.id)
    photos.value = [...item.value.photos]
    const productId = item.value.cardmarket_product_id
    product.value = productId ? await engine.getProduct(productId).catch(() => null) : null
  } catch (error) {
    failure.value = engineErrorMessage(error)
  }
}
watch(() => props.id, load, { immediate: true })

// A change made here also shows in the page underneath (stock, lot).
async function changed() {
  await Promise.all([load(), refreshNuxtData()])
}

const position = computed(() => props.siblings?.indexOf(props.id) ?? -1)
function go(offset: number) {
  const next = props.siblings?.[position.value + offset]
  if (next != null) drawer.replace({ kind: 'item', id: next, siblings: props.siblings })
}

const subtitle = computed(() => {
  const card = item.value
  if (!card) return undefined
  const number = [card.set_code?.toUpperCase(), card.card_number].filter(Boolean).join(' ')
  return [GAME_LABELS[card.game], number, card.rarity, card.grading].filter(Boolean).join(' · ')
})

// Projected margin while listed, actual margin once sold.
const outcome = computed(() => item.value?.sale?.breakdown ?? item.value?.listing_projection)

const listingOpen = ref(false)
const saleOpen = ref(false)
const editOpen = ref(false)
</script>

<template>
  <div class="flex h-full flex-col">
    <DrawerHeader :title="item?.name ?? 'Carte'" :subtitle="subtitle" icon="i-lucide-layers" />

    <div
      v-if="siblings && siblings.length > 1"
      class="flex items-center justify-between border-b border-default px-4 py-2 sm:px-6"
    >
      <UButton
        icon="i-lucide-chevron-left"
        label="Précédente"
        color="neutral"
        variant="ghost"
        size="sm"
        :disabled="position <= 0"
        @click="go(-1)"
      />
      <span class="text-sm text-muted tabular-nums">
        {{ position + 1 }} / {{ siblings.length }}
      </span>
      <UButton
        trailing-icon="i-lucide-chevron-right"
        label="Suivante"
        color="neutral"
        variant="ghost"
        size="sm"
        :disabled="position >= siblings.length - 1"
        @click="go(1)"
      />
    </div>

    <div class="flex-1 space-y-6 overflow-y-auto p-4 sm:p-6">
      <UAlert
        v-if="failure"
        color="error"
        variant="subtle"
        :title="failure"
        :actions="[{ label: 'Réessayer', onClick: () => load() }]"
      />

      <template v-else-if="item">
        <div class="grid grid-cols-2 gap-2">
          <template v-if="item.sale">
            <UButton
              icon="i-lucide-receipt"
              label="Modifier la vente"
              color="neutral"
              variant="subtle"
              block
              class="col-span-2"
              @click="saleOpen = true"
            />
          </template>
          <template v-else>
            <UButton
              icon="i-lucide-tag"
              :label="item.listing_platform ? 'Modifier l’annonce' : 'Mettre en vente'"
              block
              @click="listingOpen = true"
            />
            <UButton
              icon="i-lucide-badge-euro"
              label="Vendue"
              color="neutral"
              variant="subtle"
              block
              @click="saleOpen = true"
            />
          </template>
        </div>

        <section class="space-y-2">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-semibold tracking-wider text-muted uppercase">
              Vente et fiche
            </h3>
            <UBadge
              :color="ITEM_STATUS_COLORS[item.status]"
              variant="subtle"
              :label="ITEM_STATUS_LABELS[item.status]"
            />
          </div>
          <div class="grid grid-cols-2 gap-2">
            <InfoTile
              label="Prix d’achat"
              :value="formatYen(item.price_jpy)"
              :hint="SOURCE_LABELS[item.source_platform]"
            />
            <InfoTile label="Coût de revient" :value="formatCents(item.landed_cost.total_cents)" />
            <InfoTile
              v-if="item.sale"
              label="Vendue"
              :value="formatCents(item.sale.sale_price_cents)"
              :hint="`${PLATFORM_LABELS[item.sale.platform]} · ${formatDate(item.sale.sold_on)}`"
            />
            <InfoTile
              v-else
              label="Prix affiché"
              :value="formatCents(item.listing_price_cents)"
              :hint="
                item.listing_platform ? PLATFORM_LABELS[item.listing_platform] : 'Pas en vente'
              "
            />
            <InfoTile
              :label="item.sale ? 'Marge' : 'Marge prévue'"
              :value="formatCents(outcome?.margin_cents)"
              :value-class="outcome ? signClass(outcome.margin_cents) : undefined"
              :hint="outcome?.roi != null ? `ROI ${formatRatio(outcome.roi)}` : undefined"
            />
            <InfoTile
              label="État"
              :value="item.condition ?? '—'"
              :hint="`Langue : ${item.language}`"
            />
            <button
              type="button"
              class="text-left"
              @click="(drawer.close(), navigateTo(`/lots/${item.lot_id}`))"
            >
              <InfoTile
                label="Colis"
                :value="item.lot_label"
                :hint="LOT_STATUS_LABELS[item.lot_status]"
              />
            </button>
          </div>
          <div class="flex gap-2">
            <UButton
              icon="i-lucide-pencil"
              label="Modifier la carte"
              color="neutral"
              variant="ghost"
              size="sm"
              @click="editOpen = true"
            />
            <UButton
              v-if="item.source_url"
              icon="i-lucide-external-link"
              label="Annonce d’achat"
              color="neutral"
              variant="ghost"
              size="sm"
              @click="openExternal(item.source_url)"
            />
          </div>
        </section>

        <section class="space-y-2">
          <h3 class="text-xs font-semibold tracking-wider text-muted uppercase">Où la vendre ?</h3>
          <CardVerdictPanel :query="{ item_id: item.id }" />
          <button
            v-if="product"
            type="button"
            class="flex w-full items-center gap-3 rounded-md border border-default px-3 py-2 text-left hover:bg-elevated/50"
            @click="drawer.push({ kind: 'product', id: product.id_product })"
          >
            <UIcon name="i-lucide-chart-line" class="size-5 shrink-0 text-muted" />
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm font-medium">{{ product.name }}</span>
              <span class="block truncate text-xs text-muted">{{ product.expansion_name }}</span>
            </span>
            <span class="text-right">
              <span class="block font-semibold tabular-nums">
                {{ formatCents(product.reference_cents) }}
              </span>
              <span class="block text-xs text-muted">Cardmarket</span>
            </span>
          </button>
          <p v-else class="text-sm text-muted">
            Aucun produit Cardmarket lié : modifiez la carte pour en choisir un.
          </p>
        </section>

        <section class="space-y-2">
          <h3 class="text-xs font-semibold tracking-wider text-muted uppercase">Photos</h3>
          <ItemPhotos v-model="photos" :item-id="item.id" @changed="changed" />
        </section>

        <section v-if="item.notes" class="space-y-2">
          <h3 class="text-xs font-semibold tracking-wider text-muted uppercase">Notes</h3>
          <p class="text-sm whitespace-pre-line">{{ item.notes }}</p>
        </section>
      </template>

      <div v-else class="flex justify-center py-12">
        <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-muted" />
      </div>
    </div>

    <ListingModal
      v-model:open="listingOpen"
      :item="item"
      @saved="changed"
      @photos-changed="changed"
    />
    <SaleModal v-model:open="saleOpen" :item="item" @saved="changed" />
    <ItemFormModal v-model:open="editOpen" :item="item" @saved="changed" />
  </div>
</template>
