/**
 * Contract of the local engine's REST API (mirror of `engine/mekiki_engine/schemas.py`).
 *
 * Money always travels in minor units: `*_cents` for euros, `*_jpy` for yen.
 * Rates are plain numbers: `*_percent` fields are percentages (12.3), `roi` is a fraction (0.1797).
 */

export type Game = 'pokemon' | 'one_piece'
export type SourcePlatform = 'mercari' | 'yahoo_auctions' | 'yahoo_fleamarket' | 'rakuma' | 'other'
export type SalePlatform = 'cardmarket' | 'ebay' | 'vinted' | 'leboncoin' | 'other'
export type LotStatus = 'purchasing' | 'shipped' | 'received'
export type ItemStatus = 'incoming' | 'in_stock' | 'listed' | 'sold'

export interface PlatformFeeSettings {
  percent: number
  fixed_cents: number
  applies_to_shipping: boolean
}

export interface AppSettings {
  fx_jpy_per_eur: number
  vat_rate_percent: number
  default_handling_fee_cents: number
  neokyo_service_fee_jpy: number
  neokyo_packing_fee_jpy: number
  contribution_rate_percent: number
  income_tax_rate_percent: number
  default_packaging_cents: number
  platform_fees: Record<SalePlatform, PlatformFeeSettings>
}

export interface LotFields {
  proxy: string
  status: LotStatus
  international_shipping_jpy: number
  insurance_jpy: number
  other_fees_jpy: number
  payment_fees_cents: number
  /** `null` until the carrier invoice is entered: the VAT is then estimated. */
  import_vat_cents: number | null
  customs_duty_cents: number
  shipping_method: string | null
  tracking_number: string | null
  ordered_on: string | null
  shipped_on: string | null
  received_on: string | null
  notes: string | null
}

export interface LotCreate extends Partial<LotFields> {
  label: string
  /** Left `null`, these take the current defaults from the settings. */
  fx_jpy_per_eur?: number | null
  packing_fee_jpy?: number | null
  handling_fee_cents?: number | null
}

/** Only the fields sent are changed; `import_vat_cents: null` goes back to an estimated VAT. */
export type LotUpdate = Partial<
  LotFields & {
    label: string
    fx_jpy_per_eur: number
    packing_fee_jpy: number
    handling_fee_cents: number
  }
>

export interface LotSummary extends LotFields {
  id: number
  label: string
  fx_jpy_per_eur: number
  packing_fee_jpy: number
  handling_fee_cents: number
  item_count: number
  sold_count: number
  goods_jpy: number
  landed_total_cents: number
  applied_import_vat_cents: number
  vat_estimated: boolean
}

export interface LotDetail extends LotSummary {
  items: Item[]
}

export interface ItemFields {
  game: Game
  name: string
  set_code: string | null
  card_number: string | null
  rarity: string | null
  language: string
  condition: string | null
  grading: string | null
  source_platform: SourcePlatform
  source_url: string | null
  price_jpy: number
  domestic_shipping_jpy: number
  cardmarket_product_id: number | null
  listing_platform: SalePlatform | null
  listing_price_cents: number | null
  notes: string | null
}

export interface ItemCreate extends Partial<ItemFields> {
  game: Game
  name: string
  price_jpy: number
  /** Left `null`, takes the proxy service fee from the settings. */
  service_fee_jpy?: number | null
}

export type ItemUpdate = Partial<ItemFields & { lot_id: number; service_fee_jpy: number }>

export interface LandedCost {
  purchase_cents: number
  proxy_fees_cents: number
  shipping_cents: number
  import_taxes_cents: number
  total_cents: number
  vat_estimated: boolean
}

export interface SaleBreakdown {
  revenue_cents: number
  platform_fee_cents: number
  shipping_cost_cents: number
  packaging_cents: number
  contributions_cents: number
  net_cents: number
  margin_cents: number
  roi: number | null
}

export interface Sale {
  platform: SalePlatform
  sold_on: string
  sale_price_cents: number
  shipping_charged_cents: number
  shipping_cost_cents: number
  platform_fee_cents: number
  packaging_cents: number
  contribution_rate_percent: number
  notes: string | null
  breakdown: SaleBreakdown
}

export interface Item extends ItemFields {
  id: number
  lot_id: number
  lot_label: string
  lot_status: LotStatus
  service_fee_jpy: number
  status: ItemStatus
  landed_cost: LandedCost
  /** What the current listing would leave once sold, shipping assumed neutral. */
  listing_projection: SaleBreakdown | null
  sale: Sale | null
}

export interface SaleUpsert {
  platform: SalePlatform
  sold_on: string
  sale_price_cents: number
  shipping_charged_cents?: number
  shipping_cost_cents?: number
  /** Left `null`, computed from the settings and then frozen with the sale. */
  platform_fee_cents?: number | null
  packaging_cents?: number | null
  notes?: string | null
}

export interface MonthlySales {
  month: string
  sold_count: number
  revenue_cents: number
  net_cents: number
  margin_cents: number
}

export interface Dashboard {
  incoming_count: number
  in_stock_count: number
  listed_count: number
  stock_cost_cents: number
  listed_price_cents: number
  listed_expected_margin_cents: number
  sold_count: number
  revenue_cents: number
  net_cents: number
  cost_of_sold_cents: number
  margin_cents: number
  roi: number | null
  monthly: MonthlySales[]
}

export interface SimulationRequest {
  price_jpy: number
  domestic_shipping_jpy?: number
  sale_price_cents: number
  platform?: SalePlatform
  shipping_charged_cents?: number
  shipping_cost_cents?: number
  cards_in_lot?: number
  lot_shipping_jpy?: number
  target_roi_percent?: number | null
  fx_jpy_per_eur?: number | null
}

export interface SimulationResult {
  landed_cost: LandedCost
  sale: SaleBreakdown
  fx_jpy_per_eur: number
  /** Highest price that still meets the target ROI; `null` when no price does. */
  max_price_jpy: number | null
}

export interface InventoryQuery {
  status?: ItemStatus
  game?: Game
}

export interface DashboardQuery {
  since?: string
  until?: string
}
