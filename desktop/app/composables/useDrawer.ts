import type { Game, SourcePlatform } from '~/types/engine'

/** A Japanese listing seen in a discovery, a search, the deals or the cart. */
export interface ListingPreview {
  title: string
  source: SourcePlatform
  price_jpy: number
  shipping_included: boolean | null
  url: string
  neokyo_url: string | null
  thumbnail_url: string | null
  game: Game
  /** The Cardmarket product it was read as, if any. */
  product_id: number | null
  /** What it was read as, e.g. "SV2a 201/165 · SAR". */
  label: string | null
}

/** A detail panel opened on the right of the app. */
export type DrawerEntry =
  /** A card in stock; `siblings` are the cards of the list it was opened from, in order. */
  | { kind: 'item'; id: number; siblings?: number[] }
  /** A Cardmarket product: its prices and European resale prices. */
  | { kind: 'product'; id: number }
  /** A listing to buy in Japan, with the verdict on its price. */
  | { kind: 'listing'; listing: ListingPreview }

/**
 * Side panels shared by the whole app. Panels stack: one opened from another (the product of
 * a card, for instance) comes with a back button to the previous one.
 */
export function useDrawer() {
  const stack = useState<DrawerEntry[]>('drawer-stack', () => [])

  return {
    stack,
    current: computed(() => stack.value.at(-1) ?? null),
    /** Opens a panel, closing any other. */
    open: (entry: DrawerEntry) => (stack.value = [entry]),
    /** Opens a panel on top of the current one. */
    push: (entry: DrawerEntry) => (stack.value = [...stack.value, entry]),
    /** Swaps the current panel, e.g. for the next card of the list. */
    replace: (entry: DrawerEntry) => (stack.value = [...stack.value.slice(0, -1), entry]),
    back: () => (stack.value = stack.value.slice(0, -1)),
    close: () => (stack.value = []),
  }
}
