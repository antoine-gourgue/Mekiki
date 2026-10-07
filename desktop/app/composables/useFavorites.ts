import type { FavoriteCreate, Favorites, FavoriteUpdate } from '~/types/engine'

/**
 * Favorite listings shared by every page: the star on a listing card, the cart page and the
 * sidebar badge all read the same state. Every change returns the whole list re-priced.
 */
export function useFavorites() {
  const engine = useEngine()
  const showError = useErrorToast()
  const toast = useToast()
  const state = useState<Favorites | null>('favorites', () => null)

  const keys = computed(
    () =>
      new Map(
        (state.value?.items ?? []).map((item) => [`${item.source}:${item.external_id}`, item]),
      ),
  )
  const cartCount = computed(() => state.value?.cart?.card_count ?? 0)

  async function run(action: () => Promise<Favorites>) {
    try {
      state.value = await action()
    } catch (error) {
      showError(error)
    }
  }

  function find(source: string, externalId: string) {
    return keys.value.get(`${source}:${externalId}`)
  }

  async function toggle(listing: FavoriteCreate) {
    const existing = find(listing.source, listing.external_id)
    if (existing) {
      await run(() => engine.deleteFavorite(existing.id))
    } else {
      await run(() => engine.addFavorite(listing))
      toast.add({
        title: 'Ajoutée aux favoris',
        description: 'Retrouvez-la dans le panier pour composer un colis.',
        color: 'success',
        duration: 2500,
      })
    }
  }

  return {
    state,
    cartCount,
    find,
    toggle,
    refresh: () => run(() => engine.listFavorites()),
    update: (id: number, body: FavoriteUpdate) => run(() => engine.updateFavorite(id, body)),
    remove: (id: number) => run(() => engine.deleteFavorite(id)),
    emptyCart: () => run(() => engine.emptyCart()),
  }
}

interface ListingLike {
  source: FavoriteCreate['source']
  external_id: string
  title: string
  price_jpy: number
  shipping_included: boolean | null
  url: string
  thumbnail_url: string | null
  listed_at: string | null
  ends_at: string | null
  bids: number | null
}

/** A favorite from any listing card: discovery pick, scanner deal or search result. */
export function listingToFavorite(
  listing: ListingLike,
  extra: Pick<FavoriteCreate, 'game'> & Partial<FavoriteCreate>,
): FavoriteCreate {
  return {
    source: listing.source,
    external_id: listing.external_id,
    title: listing.title,
    price_jpy: listing.price_jpy,
    shipping_included: listing.shipping_included,
    url: listing.url,
    thumbnail_url: listing.thumbnail_url,
    listed_at: listing.listed_at,
    ends_at: listing.ends_at,
    bids: listing.bids,
    ...extra,
  }
}
