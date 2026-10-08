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
const groups = computed(() =>
  [
    { title: 'Dans le colis', list: inCart.value },
    { title: 'Autres favoris', list: others.value },
  ].filter((group) => group.list.length),
)
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
const drawer = useDrawer()

function openFavorite(item: Favorite) {
  drawer.open({
    kind: 'listing',
    listing: { ...item, product_id: item.cardmarket_product_id, label: item.card_label },
  })
}

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
  return [item.card_label, item.product?.expansion_name].filter(Boolean).join(' · ') || undefined
}

// Buying stays manual: this only opens each listing of the parcel on Neokyo.
const neokyoLinks = computed(() =>
  inCart.value.map((item) => item.neokyo_url).filter((url): url is string => !!url),
)
function openAllOnNeokyo() {
  for (const url of neokyoLinks.value) openExternal(url)
}
</script>

<template>
  <UDashboardPanel id="cart">
    <template #header>
      <PageNavbar
        title="Panier"
        description="Vos favoris. Cochez ceux qui partent dans le colis pour voir ce qu’il coûte et rapporte."
      >
        <template #right>
          <UButton
            v-if="inCart.length"
            color="neutral"
            variant="outline"
            icon="i-lucide-trash-2"
            label="Vider le panier"
            @click="emptyCart"
          />
        </template>
      </PageNavbar>
    </template>

    <template #body>
      <UEmpty
        v-if="!items.length"
        icon="i-lucide-star"
        title="Aucun favori"
        description="Ajoutez des annonces en favori avec l’étoile, depuis « Trouver des cartes », « Bonnes affaires » ou « Recherche », puis composez votre colis ici."
        :actions="[{ label: 'Trouver des cartes', to: '/decouverte' }]"
      />

      <div v-else class="flex flex-wrap items-start gap-5">
        <div class="min-w-0 flex-[2_1_560px] space-y-6">
          <section v-for="group in groups" :key="group.title" class="space-y-2.5">
            <h2 class="text-sm font-medium text-muted">
              {{ group.title }}
              <span class="font-mono text-dimmed">{{ group.list.length }}</span>
            </h2>
            <DealCard
              v-for="item in group.list"
              :key="item.id"
              :title="item.title"
              :heading="item.product?.name ?? item.card_label"
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
              :class="{ 'bg-transparent': !item.in_cart }"
              @open="openFavorite(item)"
            >
              <template #leading>
                <UCheckbox
                  :model-value="item.in_cart"
                  label="Dans le colis"
                  :ui="{ label: 'text-sm' }"
                  @update:model-value="(value) => favorites.update(item.id, { in_cart: !!value })"
                />
              </template>
            </DealCard>
          </section>
          <p v-if="others.length" class="text-xs text-dimmed">
            Les favoris hors du colis sont chiffrés comme une carte d’un colis de
            {{ settings?.scanner.cards_per_lot ?? 10 }}.
          </p>
        </div>

        <aside class="min-w-0 flex-[1_1_320px] lg:sticky lg:top-0">
          <UCard :ui="{ body: 'space-y-4 sm:p-5' }">
            <div class="flex items-baseline justify-between">
              <h2 class="font-semibold text-highlighted">Le colis</h2>
              <span class="text-sm text-muted">
                {{ cart?.card_count ?? 0 }} carte{{ (cart?.card_count ?? 0) > 1 ? 's' : '' }}
              </span>
            </div>

            <template v-if="cart">
              <div class="grid grid-cols-2 gap-2.5">
                <InfoTile
                  label="Coût du colis"
                  :value="formatCents(cart.landed_cents)"
                  :hint="`${formatYen(cart.purchase_jpy)} d’achats`"
                />
                <InfoTile
                  label="Revente attendue"
                  :value="formatCents(cart.revenue_cents)"
                  :hint="`net ${formatCents(cart.net_cents)}`"
                />
                <InfoTile
                  label="Marge attendue"
                  :value="formatSignedCents(cart.margin_cents)"
                  :value-class="signClass(cart.margin_cents)"
                />
                <InfoTile
                  label="ROI du colis"
                  :value="formatRatio(cart.roi)"
                  :value-class="signClass(cart.roi)"
                />
              </div>
              <p class="text-xs text-dimmed">
                Tout compris : frais Neokyo, envoi et taxes à l’import.
              </p>

              <UAlert
                v-if="cart.unpriced_count"
                color="error"
                variant="subtle"
                icon="i-lucide-circle-alert"
                :description="`${cart.unpriced_count} carte(s) sans prix de revente : leur coût compte, pas leur revente. Indiquez un prix avec « Prix de revente… ».`"
              />

              <UButton
                v-if="neokyoLinks.length"
                block
                size="xl"
                trailing-icon="i-lucide-arrow-up-right"
                :label="`Ouvrir ${neokyoLinks.length > 1 ? `les ${neokyoLinks.length} annonces` : 'l’annonce'} sur Neokyo`"
                @click="openAllOnNeokyo"
              />
              <p class="-mt-2 text-center text-xs text-dimmed">
                L’achat se fait sur Neokyo, annonce par annonce.
              </p>
            </template>

            <p v-else class="text-sm text-muted">
              Cochez « Dans le colis » sur vos favoris pour voir ce que coûterait le colis et ce
              qu’il rapporterait.
            </p>
          </UCard>
        </aside>
      </div>

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
