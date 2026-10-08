import type { BadgeProps } from '@nuxt/ui'
import type {
  Game,
  ItemStatus,
  ListingCondition,
  LotStatus,
  SalePlatform,
  ScannableSource,
  SourcePlatform,
} from '~/types/engine'

export const GAME_LABELS: Record<Game, string> = {
  pokemon: 'Pokémon',
  one_piece: 'One Piece',
}

export const SOURCE_LABELS: Record<SourcePlatform, string> = {
  mercari: 'Mercari',
  yahoo_auctions: 'Yahoo Auctions',
  yahoo_fleamarket: 'Yahoo Fleamarket',
  rakuma: 'Rakuma',
  other: 'Autre',
}

export const PLATFORM_LABELS: Record<SalePlatform, string> = {
  cardmarket: 'Cardmarket',
  ebay: 'eBay',
  vinted: 'Vinted',
  leboncoin: 'Leboncoin',
  other: 'Autre',
}

export const LOT_STATUS_LABELS: Record<LotStatus, string> = {
  purchasing: 'Achat en cours',
  shipped: 'Expédié',
  received: 'Reçu',
}

export const LOT_STATUS_COLORS: Record<LotStatus, BadgeProps['color']> = {
  purchasing: 'neutral',
  shipped: 'primary',
  received: 'success',
}

export const ITEM_STATUS_LABELS: Record<ItemStatus, string> = {
  incoming: 'En route',
  in_stock: 'En stock',
  listed: 'En vente',
  sold: 'Vendue',
}

export const ITEM_STATUS_COLORS: Record<ItemStatus, BadgeProps['color']> = {
  incoming: 'info',
  in_stock: 'neutral',
  listed: 'primary',
  sold: 'success',
}

/** Condition of a Japanese listing, best first. */
export const CONDITION_LABELS: Record<ListingCondition, string> = {
  new: 'Neuve',
  like_new: 'Quasi neuve',
  good: 'Bon état',
  fair: 'Légères traces',
  poor: 'Abîmée',
  bad: 'Mauvais état',
}

/** The marketplace's own wording, shown on hover. */
export const CONDITION_JAPANESE: Record<ListingCondition, string> = {
  new: '新品、未使用',
  like_new: '未使用に近い',
  good: '目立った傷や汚れなし',
  fair: 'やや傷や汚れあり',
  poor: '傷や汚れあり',
  bad: '全体的に状態が悪い',
}

export const CONDITION_COLORS: Record<ListingCondition, BadgeProps['color']> = {
  new: 'success',
  like_new: 'success',
  good: 'neutral',
  fair: 'warning',
  poor: 'error',
  bad: 'error',
}

/** Choices of a minimum condition; `all` keeps the listings that do not say. */
export const MIN_CONDITION_ITEMS: { value: ListingCondition | 'all'; label: string }[] = [
  { value: 'all', label: 'Tous les états' },
  { value: 'new', label: 'Neuve uniquement' },
  { value: 'like_new', label: 'Quasi neuve ou mieux' },
  { value: 'good', label: 'Bon état ou mieux' },
  { value: 'fair', label: 'Légères traces ou mieux' },
]

/** 0 for the best condition; listings that do not say come last. */
export function conditionRank(condition: ListingCondition | null | undefined): number {
  const order = Object.keys(CONDITION_LABELS)
  return condition ? order.indexOf(condition) : order.length
}

/** Turns a label map into `USelect` items, keeping the map's order. */
export function selectItems<T extends string>(labels: Record<T, string>) {
  return (Object.entries(labels) as [T, string][]).map(([value, label]) => ({ value, label }))
}

/** Marketplaces the engine can search, for checkbox groups. */
export const SCANNABLE_SOURCE_ITEMS: {
  value: ScannableSource
  label: string
  description?: string
}[] = [
  { value: 'mercari', label: 'Mercari' },
  { value: 'rakuma', label: 'Rakuma' },
  {
    value: 'yahoo_auctions',
    label: 'Yahoo Auctions',
    description: 'Bloqué depuis l’Union européenne',
  },
  {
    value: 'yahoo_fleamarket',
    label: 'Yahoo Fleamarket',
    description: 'Bloqué depuis l’Union européenne',
  },
]

/** Default marketplaces: Yahoo! JAPAN refuses visitors from Europe. */
export const DEFAULT_SOURCES: ScannableSource[] = ['mercari', 'rakuma']

/** Where a suggested listing price comes from (see ListingDraft.price_source). */
export const PRICE_SOURCE_LABELS: Record<string, string> = {
  listing: 'prix déjà enregistré',
  avg30: 'moyenne des ventes Cardmarket sur 30 jours',
  avg7: 'moyenne des ventes Cardmarket sur 7 jours',
  avg: 'prix moyen Cardmarket',
  avg1: 'ventes Cardmarket de la veille',
  trend: 'tendance Cardmarket',
}
