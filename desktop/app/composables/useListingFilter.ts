import type { ListingCondition } from '~/types/engine'

export type ListingSort = 'roi' | 'condition' | 'price' | 'recent'

interface FilterableListing {
  condition: ListingCondition | null
  price_jpy: number
  listed_at: string | null
  /** Search results the title rule rejected stay after the others, whatever the order. */
  matched?: boolean
}

export const LISTING_SORT_ITEMS: { value: ListingSort; label: string }[] = [
  { value: 'roi', label: 'Meilleur ROI' },
  { value: 'condition', label: 'Meilleur état' },
  { value: 'price', label: 'Prix le plus bas' },
  { value: 'recent', label: 'Plus récentes' },
]

const COMPARE: Record<
  Exclude<ListingSort, 'roi'>,
  (a: FilterableListing, b: FilterableListing) => number
> = {
  condition: (a, b) => conditionRank(a.condition) - conditionRank(b.condition),
  price: (a, b) => a.price_jpy - b.price_jpy,
  recent: (a, b) => (b.listed_at ?? '').localeCompare(a.listed_at ?? ''),
}

/**
 * Filters listings on a minimum condition and sorts them, in the page: changing either never
 * searches again. `roi` keeps the engine's order, best return first.
 */
export function useListingFilter<T extends FilterableListing>(listings: () => T[]) {
  const minCondition = ref<ListingCondition | 'all'>('all')
  const sortBy = ref<ListingSort>('roi')

  const visible = computed(() => {
    const minimum = minCondition.value
    const kept = listings().filter(
      (listing) => minimum === 'all' || conditionRank(listing.condition) <= conditionRank(minimum),
    )
    if (sortBy.value === 'roi') return kept
    const compare = COMPARE[sortBy.value]
    const rejected = (listing: T) => Number(listing.matched === false)
    return [...kept].sort((a, b) => rejected(a) - rejected(b) || compare(a, b))
  })
  const hidden = computed(() => listings().length - visible.value.length)
  // Rakuma's results never give the condition: say why its listings disappear.
  const hiddenWithoutCondition = computed(
    () => minCondition.value !== 'all' && listings().some((listing) => !listing.condition),
  )

  return { minCondition, sortBy, visible, hidden, hiddenWithoutCondition }
}
