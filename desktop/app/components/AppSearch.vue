<script setup lang="ts">
import type { CommandPaletteGroup, CommandPaletteItem, NavigationMenuItem } from '@nuxt/ui'
import type { Item, LotSummary, MarketPrice } from '~/types/engine'

/**
 * Search across the app (Ctrl+K): pages, cards in stock, parcels, favorites and the
 * Cardmarket catalog. Cards and products open in the side panel.
 */
const props = defineProps<{ links: NavigationMenuItem[][] }>()

const engine = useEngine()
const drawer = useDrawer()
const favorites = useFavorites()

const open = ref(false)
const term = ref('')

// Stock and parcels are small: loaded whole each time the search opens, filtered locally.
const items = ref<Item[]>([])
const lots = ref<LotSummary[]>([])
watch(open, async (isOpen) => {
  if (!isOpen) return
  try {
    ;[items.value, lots.value] = await Promise.all([engine.inventory(), engine.listLots()])
  } catch {
    // The pages still work without them; the engine status shows what is wrong.
  }
})

// The catalog holds tens of thousands of products: the engine searches it.
const MIN_CATALOG_TERM = 3
const PRODUCTS_PER_GAME = 6
const products = ref<MarketPrice[]>([])
const searchingCatalog = ref(false)
let catalogTimer: ReturnType<typeof setTimeout> | undefined
watch(term, (value) => {
  clearTimeout(catalogTimer)
  const query = value.trim()
  if (query.length < MIN_CATALOG_TERM) {
    products.value = []
    return
  }
  catalogTimer = setTimeout(async () => {
    searchingCatalog.value = true
    try {
      const results = await Promise.all(
        (['pokemon', 'one_piece'] as const).map((game) => engine.searchProducts(game, query)),
      )
      products.value = results.flatMap((list) => list.slice(0, PRODUCTS_PER_GAME))
    } catch {
      products.value = []
    } finally {
      searchingCatalog.value = false
    }
  }, 300)
})
onBeforeUnmount(() => clearTimeout(catalogTimer))

function cardNumber(item: Item) {
  return [item.set_code?.toUpperCase(), item.card_number].filter(Boolean).join(' ')
}

const groups = computed<CommandPaletteGroup<CommandPaletteItem>[]>(() => [
  {
    id: 'pages',
    label: 'Pages',
    items: props.links.flat().map((link) => ({ label: link.label, icon: link.icon, to: link.to })),
  },
  {
    id: 'stock',
    label: 'Stock',
    items: items.value.map((item) => ({
      label: item.name,
      suffix: [cardNumber(item), item.rarity, item.lot_label].filter(Boolean).join(' · '),
      icon: 'i-lucide-layers',
      onSelect: () => drawer.open({ kind: 'item', id: item.id }),
    })),
  },
  {
    id: 'lots',
    label: 'Colis',
    items: lots.value.map((lot) => ({
      label: lot.label,
      suffix: LOT_STATUS_LABELS[lot.status],
      icon: 'i-lucide-package',
      to: `/lots/${lot.id}`,
    })),
  },
  {
    id: 'favorites',
    label: 'Favoris',
    items: (favorites.state.value?.items ?? []).map((favorite) => ({
      label: favorite.card_label ?? favorite.title,
      suffix: favorite.card_label ? favorite.title : SOURCE_LABELS[favorite.source],
      icon: 'i-lucide-star',
      onSelect: () =>
        favorite.cardmarket_product_id
          ? drawer.open({ kind: 'product', id: favorite.cardmarket_product_id })
          : openExternal(favorite.url),
    })),
  },
  {
    id: 'catalog',
    label: 'Catalogue Cardmarket',
    // Already matched by the engine: Fuse would drop English names typed in French.
    ignoreFilter: true,
    items: products.value.map((product) => ({
      label: product.name ?? `Produit ${product.id_product}`,
      suffix: [
        GAME_LABELS[product.game],
        product.japanese ? 'japonaise' : null,
        product.expansion_name,
        formatCents(product.reference_cents),
      ]
        .filter(Boolean)
        .join(' · '),
      icon: 'i-lucide-chart-line',
      onSelect: () => drawer.open({ kind: 'product', id: product.id_product }),
    })),
  },
])
</script>

<template>
  <UDashboardSearch
    v-model:open="open"
    v-model:search-term="term"
    :groups="groups"
    :loading="searchingCatalog"
    :color-mode="false"
    placeholder="Rechercher une carte, un colis, une page…"
    :fuse="{ resultLimit: 8 }"
  />
</template>
