<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import type { Favorite, ItemCreate } from '~/types/engine'

const engine = useEngine()
const favorites = useFavorites()
const confirm = useConfirm()

const { data: settings } = useAsyncData('settings', () => engine.getSettings())
const { data: lots } = useAsyncData('lots', () => engine.listLots())
onMounted(() => favorites.refresh())

const items = computed(() => favorites.state.value?.items ?? [])
const inCart = computed(() => items.value.filter((item) => item.in_cart))
const others = computed(() => items.value.filter((item) => !item.in_cart))
const cart = computed(() => favorites.state.value?.cart ?? null)
const targetRoi = computed(() => (settings.value?.scanner.min_roi_percent ?? 30) / 100)

// Resale price set by hand, for listings without a Cardmarket price or with a wrong one.
const editing = ref<Favorite | null>(null)
const editingOpen = ref(false)
const targetPrice = ref<number | null>(null)

function editPrice(item: Favorite) {
  editing.value = item
  targetPrice.value = item.target_price_cents ?? item.expected_sale_cents
  editingOpen.value = true
}

async function savePrice(clear = false) {
  if (!editing.value) return
  await favorites.update(editing.value.id, {
    target_price_cents: clear ? null : targetPrice.value,
  })
  editingOpen.value = false
}

// "Acheté" opens the card form pre-filled, to put the card straight into a lot.
const buying = ref(false)
const purchase = ref<Partial<ItemCreate> | null>(null)

function bought(item: Favorite) {
  purchase.value = {
    game: item.game,
    name: item.product?.name ?? item.card_label ?? item.title,
    card_number: item.card_label?.split(' · ')[0] ?? null,
    source_platform: item.source,
    source_url: item.url,
    price_jpy: item.price_jpy,
    domestic_shipping_jpy: item.shipping_included
      ? 0
      : (settings.value?.scanner.domestic_shipping_jpy ?? 0),
    cardmarket_product_id: item.cardmarket_product_id,
  }
  buying.value = true
}

const showResale = useResaleModal()

function menu(item: Favorite): DropdownMenuItem[] {
  return [
    { label: 'Prix de revente…', icon: 'i-lucide-pencil', onSelect: () => editPrice(item) },
    {
      label: 'Prix en Europe (eBay, Vinted)',
      icon: 'i-lucide-euro',
      onSelect: () =>
        showResale(
          item.card_label ?? item.title,
          item.cardmarket_product_id
            ? { product_id: item.cardmarket_product_id, label: item.card_label ?? undefined }
            : { q: item.card_label ?? item.title },
        ),
    },
    ...(item.product
      ? [
          {
            label: 'Voir la cote sur Cardmarket',
            icon: 'i-lucide-chart-line',
            onSelect: () => openExternal(item.product!.url),
          },
        ]
      : []),
    {
      label: 'Acheté : ajouter au stock',
      icon: 'i-lucide-package-plus',
      onSelect: () => bought(item),
    },
    {
      label: 'Retirer des favoris',
      icon: 'i-lucide-trash-2',
      color: 'error' as const,
      onSelect: () => favorites.remove(item.id),
    },
  ]
}

async function emptyCart() {
  const confirmed = await confirm({
    title: 'Vider le panier ?',
    description: 'Les cartes restent dans vos favoris.',
    confirmLabel: 'Vider',
  })
  if (confirmed) await favorites.emptyCart()
}

function subtitle(item: Favorite) {
  const product = item.product
    ? `${item.product.name}${item.product.expansion_name ? ` (${item.product.expansion_name})` : ''}`
    : null
  return [item.card_label, product].filter(Boolean).join(' · ') || undefined
}
</script>

<template>
  <UDashboardPanel id="cart">
    <template #header>
      <UDashboardNavbar title="Panier">
        <template #leading><UDashboardSidebarCollapse /></template>
        <template #right>
          <UButton
            v-if="inCart.length"
            color="neutral"
            variant="outline"
            icon="i-lucide-x"
            label="Vider le panier"
            @click="emptyCart"
          />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UEmpty
        v-if="!items.length"
        icon="i-lucide-star"
        title="Aucun favori"
        description="Ajoutez des annonces en favori avec l’étoile, depuis « Trouver des cartes », « Bonnes affaires » ou « Recherche », puis composez votre colis ici."
        :actions="[{ label: 'Trouver des cartes', to: '/decouverte' }]"
      />

      <template v-else>
        <section class="space-y-3">
          <div v-if="cart" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <StatTile
              icon="i-lucide-layers"
              label="Cartes dans le colis"
              :value="String(cart.card_count)"
              :hint="`${formatYen(cart.purchase_jpy)} d’achats`"
            />
            <StatTile
              icon="i-lucide-wallet"
              label="Coût du colis"
              :value="formatCents(cart.landed_cents)"
              hint="Tout compris : frais, envoi, taxes"
            />
            <StatTile
              icon="i-lucide-euro"
              label="Revente attendue"
              :value="formatCents(cart.revenue_cents)"
              :hint="`Net ${formatCents(cart.net_cents)} après frais et cotisations`"
            />
            <StatTile
              icon="i-lucide-piggy-bank"
              label="Marge attendue"
              :value="formatCents(cart.margin_cents)"
              :value-class="signClass(cart.margin_cents)"
            />
            <StatTile
              icon="i-lucide-percent"
              label="ROI du colis"
              :value="formatRatio(cart.roi)"
              :value-class="signClass(cart.roi)"
            />
          </div>
          <UAlert
            v-if="cart?.unpriced_count"
            color="warning"
            variant="subtle"
            icon="i-lucide-triangle-alert"
            :description="`${cart.unpriced_count} carte(s) sans prix de revente : leur coût compte, pas leur revente. Indiquez un prix avec « Prix de revente… ».`"
          />
          <UEmpty
            v-if="!cart"
            icon="i-lucide-shopping-basket"
            title="Le panier est vide"
            description="Cochez « Dans le colis » sur vos favoris pour voir ce que coûterait le colis et ce qu’il rapporterait."
          />
        </section>

        <section v-if="inCart.length" class="space-y-3">
          <h2 class="font-medium text-highlighted">Dans le colis</h2>
          <div class="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
            <DealCard
              v-for="item in inCart"
              :key="item.id"
              :title="item.title"
              :subtitle="subtitle(item)"
              :source="item.source"
              :price-jpy="item.price_jpy"
              :shipping-included="item.shipping_included"
              :url="item.url"
              :neokyo-url="item.neokyo_url"
              :thumbnail-url="item.thumbnail_url"
              :listed-at="item.listed_at"
              :ends-at="item.ends_at"
              :bids="item.bids"
              :landed-cost="item.landed_cost"
              :sale="item.sale"
              :target-roi="targetRoi"
              :menu="menu(item)"
            >
              <USwitch
                class="mt-3"
                :model-value="item.in_cart"
                label="Dans le colis"
                @update:model-value="(value) => favorites.update(item.id, { in_cart: value })"
              />
            </DealCard>
          </div>
        </section>

        <section v-if="others.length" class="space-y-3">
          <h2 class="font-medium text-highlighted">Autres favoris</h2>
          <p class="text-sm text-muted">
            Chiffrés comme une carte d’un colis de {{ settings?.scanner.cards_per_lot ?? 10 }}.
          </p>
          <div class="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
            <DealCard
              v-for="item in others"
              :key="item.id"
              :title="item.title"
              :subtitle="subtitle(item)"
              :source="item.source"
              :price-jpy="item.price_jpy"
              :shipping-included="item.shipping_included"
              :url="item.url"
              :neokyo-url="item.neokyo_url"
              :thumbnail-url="item.thumbnail_url"
              :listed-at="item.listed_at"
              :ends-at="item.ends_at"
              :bids="item.bids"
              :landed-cost="item.landed_cost"
              :sale="item.sale"
              :target-roi="targetRoi"
              :menu="menu(item)"
            >
              <USwitch
                class="mt-3"
                :model-value="item.in_cart"
                label="Dans le colis"
                @update:model-value="(value) => favorites.update(item.id, { in_cart: value })"
              />
            </DealCard>
          </div>
        </section>
      </template>

      <UModal
        v-model:open="editingOpen"
        title="Prix de revente"
        :description="editing?.title"
        :ui="{ footer: 'justify-between' }"
      >
        <template #body>
          <UFormField
            label="Prix visé"
            :help="
              editing?.product
                ? `Cote Cardmarket : ${formatCents(editing.product.reference_cents)}`
                : 'Pas de cote Cardmarket pour cette annonce.'
            "
          >
            <MoneyInput v-model="targetPrice" currency="EUR" autofocus />
          </UFormField>
        </template>
        <template #footer>
          <UButton
            v-if="editing?.target_price_cents != null && editing?.product"
            color="neutral"
            variant="ghost"
            label="Revenir à la cote"
            @click="savePrice(true)"
          />
          <span v-else />
          <UButton label="Enregistrer" :disabled="targetPrice == null" @click="savePrice()" />
        </template>
      </UModal>

      <ItemFormModal v-model:open="buying" :initial="purchase" :lots="lots ?? []" />
    </template>
  </UDashboardPanel>
</template>
