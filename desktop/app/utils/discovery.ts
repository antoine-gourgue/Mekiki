import type {
  DiscoveryDepth,
  DiscoveryRequest,
  Era,
  Game,
  ListingCondition,
  ScannableSource,
} from '~/types/engine'

/** The discovery form as edited: an empty field means no filter. */
export interface DiscoveryFormState {
  game: Game
  budget_cents: number | null
  card_count: number | null
  min_roi_percent: number | null
  sources: ScannableSource[]
  depth: DiscoveryDepth
  min_condition: ListingCondition | 'all'
  name: string
  eras: Era[]
  sets: string[]
  rarities: string[]
  min_market_cents: number | null
  max_market_cents: number | null
  min_price_jpy: number | null
  max_price_jpy: number | null
  max_age_days: number | null
  exclude_mirrors: boolean
  confident_only: boolean
}

export const RECENT_ERAS: Era[] = ['mega', 'sv']
export const OLDER_ERAS: Era[] = ['swsh', 'sm', 'xy', 'bw', 'older']

export const AGE_ITEMS: { value: number; label: string }[] = [
  { value: 0, label: 'Peu importe' },
  { value: 1, label: 'Dernières 24 h' },
  { value: 3, label: '3 derniers jours' },
  { value: 7, label: '7 derniers jours' },
  { value: 30, label: '30 derniers jours' },
]

/** The filters on cards, as a fresh form has them: none. */
export function noCardFilters() {
  return {
    name: '',
    eras: [] as Era[],
    sets: [] as string[],
    rarities: [] as string[],
    min_market_cents: null,
    max_market_cents: null,
    min_price_jpy: null,
    max_price_jpy: null,
    max_age_days: null,
    exclude_mirrors: false,
    confident_only: false,
  } satisfies Partial<DiscoveryFormState>
}

export function toDiscoveryRequest(form: DiscoveryFormState): DiscoveryRequest {
  return {
    game: form.game,
    budget_cents: form.budget_cents ?? 0,
    card_count: form.card_count ?? 1,
    min_roi_percent: form.min_roi_percent,
    sources: form.sources,
    depth: form.depth,
    min_condition: form.min_condition === 'all' ? null : form.min_condition,
    name: form.name.trim() || null,
    eras: form.game === 'pokemon' ? form.eras : [],
    sets: form.sets,
    rarities: form.rarities,
    min_market_cents: form.min_market_cents,
    max_market_cents: form.max_market_cents,
    min_price_jpy: form.min_price_jpy,
    max_price_jpy: form.max_price_jpy,
    max_age_days: form.max_age_days || null,
    exclude_mirrors: form.game === 'pokemon' && form.exclude_mirrors,
    confident_only: form.confident_only,
  }
}

/** The form's card filters, from a request sent before (the last discovery). */
export function cardFiltersOf(request: DiscoveryRequest) {
  return {
    name: request.name ?? '',
    eras: request.eras ?? [],
    sets: request.sets ?? [],
    rarities: request.rarities ?? [],
    min_market_cents: request.min_market_cents ?? null,
    max_market_cents: request.max_market_cents ?? null,
    min_price_jpy: request.min_price_jpy ?? null,
    max_price_jpy: request.max_price_jpy ?? null,
    max_age_days: request.max_age_days ?? null,
    exclude_mirrors: request.exclude_mirrors ?? false,
    confident_only: request.confident_only ?? false,
  } satisfies Partial<DiscoveryFormState>
}

/** How many of the "more filters" are set, for the toggle's badge. */
export function moreFilterCount(form: DiscoveryFormState): number {
  return [
    form.min_market_cents != null,
    form.max_market_cents != null,
    form.min_price_jpy != null,
    form.max_price_jpy != null,
    form.min_condition !== 'all',
    Boolean(form.max_age_days),
    form.game === 'pokemon' && form.exclude_mirrors,
    form.confident_only,
  ].filter(Boolean).length
}
