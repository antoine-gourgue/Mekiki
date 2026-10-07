import type { BadgeProps } from '@nuxt/ui'
import type { Game, ItemStatus, LotStatus, SalePlatform, SourcePlatform } from '~/types/engine'

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
