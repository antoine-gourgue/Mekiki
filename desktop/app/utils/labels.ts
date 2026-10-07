import type { BadgeProps } from '@nuxt/ui'
import type {
  Game,
  ItemStatus,
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
  shipped: 'info',
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
  listed: 'warning',
  sold: 'success',
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
