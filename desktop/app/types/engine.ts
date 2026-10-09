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
/** The six conditions of Japanese flea markets, best first (新品、未使用 … 全体的に状態が悪い). */
export type ListingCondition = 'new' | 'like_new' | 'good' | 'fair' | 'poor' | 'bad'

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
  scanner: ScannerSettings
  business: BusinessSettings
  /** False from the account's creation until its guided setup (/bienvenue) is finished. */
  onboarded: boolean
}

/** The micro-enterprise behind the account, for its books and declarations. */
export interface BusinessSettings {
  name: string
  siret: string
  /** "2026-10-01" */
  started_on: string | null
  /** How often the turnover is declared to URSSAF. */
  declaration: 'monthly' | 'quarterly'
  /** Yearly limits of the micro-enterprise and of the VAT franchise, set by law. */
  turnover_limit_cents: number
  vat_franchise_limit_cents: number
}

/** One month or quarter to declare to URSSAF. */
export interface BooksPeriod {
  label: string
  start: string
  end: string
  /** Last day to declare it. */
  due_on: string
  turnover_cents: number
  contributions_cents: number
  /** The flat income tax paid with the contributions, when chosen. */
  income_tax_cents: number
  /** upcoming: not over yet; due: to declare by `due_on`; past: its deadline passed. */
  state: 'upcoming' | 'due' | 'past'
}

export interface BooksSummary {
  year: number
  declaration: 'monthly' | 'quarterly'
  periods: BooksPeriod[]
  turnover_cents: number
  contributions_cents: number
  income_tax_cents: number
  turnover_limit_cents: number
  vat_franchise_limit_cents: number
  /** The period over and not declared yet, if any. */
  next_declaration: BooksPeriod | null
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
  tracking_number: string | null
  /** `null` while the card is still to ship. */
  shipped_on: string | null
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
  photos: ItemPhoto[]
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
  tracking_number?: string | null
  shipped_on?: string | null
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
  /** Unsold cards received more than 60 days ago, and what they cost. */
  dormant_count: number
  dormant_cost_cents: number
  /** Days from receiving a card to selling it, on average over the period's sales. */
  average_days_to_sell: number | null
  /** Sales whose parcel has not left yet. */
  to_ship_count: number
}

/** A card's resale price on Cardmarket, one day. */
export interface PricePoint {
  date: string
  cents: number
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

export type ListingTriage = 'new' | 'seen' | 'dismissed' | 'bought'
export type ScannableSource = Extract<
  SourcePlatform,
  'mercari' | 'rakuma' | 'yahoo_auctions' | 'yahoo_fleamarket'
>

export interface ScannerSettings {
  enabled: boolean
  interval_minutes: number
  sources: ScannableSource[]
  min_roi_percent: number
  cards_per_lot: number
  lot_shipping_jpy: number
  resale_platform: SalePlatform
  /** Added when the buyer pays the Japanese shipping. */
  domestic_shipping_jpy: number
  /** Space-separated words that disqualify a listing title. */
  excluded_keywords: string
}

export interface TrackedCardFields {
  game: Game
  name: string
  set_code: string | null
  card_number: string | null
  rarity: string | null
  grading: string | null
  cardmarket_product_id: number | null
  /** Keywords sent to the marketplaces, in Japanese or as a card number. */
  search_query: string
  required_keywords: string | null
  excluded_keywords: string | null
  /** Expected resale price; `null` uses the Cardmarket price. */
  target_price_cents: number | null
  min_price_jpy: number | null
  max_price_jpy: number | null
  active: boolean
  notes: string | null
}

export interface TrackedCardCreate extends Partial<Omit<TrackedCardFields, 'search_query'>> {
  game: Game
  name: string
  /** Left empty, built from the card number (or the name). */
  search_query?: string | null
}

export type TrackedCardUpdate = Partial<TrackedCardFields>

export interface MarketPrice {
  id_product: number
  game: Game
  name: string | null
  /** Guessed from Cardmarket's sealed products; unknown for some expansions. */
  expansion_name: string | null
  url: string
  avg_cents: number | null
  low_cents: number | null
  trend_cents: number | null
  avg1_cents: number | null
  avg7_cents: number | null
  avg30_cents: number | null
  prices_date: string | null
  /** avg30, else avg7, avg, avg1, trend; never low. */
  reference_cents: number | null
  reference_field: string | null
  /** A Japanese printing: the one Japanese listings sell. */
  japanese: boolean
}

export interface TrackedCard extends TrackedCardFields {
  id: number
  last_scanned_at: string | null
  market: MarketPrice | null
  expected_sale_cents: number | null
  /** Highest asking price that still reaches the scanner's ROI target. */
  max_buy_price_jpy: number | null
  listing_count: number
  best_roi: number | null
}

export interface Deal {
  id: number
  tracked_card_id: number
  card_name: string
  game: Game
  cardmarket_product_id: number | null
  target_price_cents: number | null
  source: SourcePlatform
  external_id: string
  title: string
  price_jpy: number
  shipping_included: boolean | null
  url: string
  neokyo_url: string | null
  thumbnail_url: string | null
  listed_at: string | null
  ends_at: string | null
  bids: number | null
  condition: ListingCondition | null
  triage: ListingTriage
  first_seen_at: string
  last_seen_at: string
  /** False once the last scan no longer found the listing. */
  online: boolean
  expected_sale_cents: number | null
  landed_cost: LandedCost
  sale: SaleBreakdown | null
}

export interface DealQuery {
  triage?: ListingTriage
  tracked_card_id?: number
  min_roi_percent?: number
  include_offline?: boolean
}

export interface ScanStatus {
  running: boolean
  enabled: boolean
  last_started_at: string | null
  last_finished_at: string | null
  last_error: string | null
  next_run_at: string | null
  cards_scanned: number
  new_listings: number
  new_deals: number
  /** Online listings not looked at yet that reach the ROI target. */
  unseen_deals: number
}

export interface CardmarketStatus {
  game: Game
  products: number
  priced_products: number
  prices_date: string | null
  fetched_at: string | null
  last_error: string | null
}

export interface SearchRequest {
  query: string
  game?: Game
  sources?: ScannableSource[] | null
  card_number?: string | null
  required_keywords?: string | null
  excluded_keywords?: string | null
  grading?: string | null
  cardmarket_product_id?: number | null
  expected_sale_cents?: number | null
}

export interface SearchResult {
  source: SourcePlatform
  external_id: string
  title: string
  price_jpy: number
  shipping_included: boolean | null
  url: string
  neokyo_url: string | null
  thumbnail_url: string | null
  listed_at: string | null
  ends_at: string | null
  bids: number | null
  condition: ListingCondition | null
  matched: boolean
  reject_reason: string | null
  landed_cost: LandedCost
  sale: SaleBreakdown | null
}

export interface SearchResponse {
  /** What was searched: card names translated to Japanese. */
  searched_query: string
  expected_sale_cents: number | null
  results: SearchResult[]
  /** Sources that failed, with the reason. */
  errors: Record<string, string>
  /** The same search on Neokyo's site, per marketplace (Yahoo stays reachable through it). */
  neokyo_search_urls: Record<string, string>
}

/** A Japanese listing checked on its marketplace just now. */
export interface ListingAvailability {
  /** `null` when the marketplace could not tell (blocked from Europe, unreachable…). */
  available: boolean | null
  /** "en vente", "vendue", "supprimée"… or why it could not be checked. */
  status: string
  condition: ListingCondition | null
  price_jpy: number | null
  checked_at: string
  seller_id?: string | null
  /** Why Neokyo would refuse this seller, when the listing gives it away. */
  seller_warning?: string | null
  /** Worth knowing without refusing the seller: "2 évaluations négatives sur 80". */
  seller_note?: string | null
  /** The seller's own description, in Japanese. */
  description?: string | null
}

export interface TranslationOut {
  text: string
  /** "deepl" with the account's key, else "mymemory", free and limited. */
  provider: 'deepl' | 'mymemory'
}

export interface TranslationStatus {
  provider: 'deepl' | 'mymemory'
  deepl_configured: boolean
}

/** A seller Neokyo refuses: their listings are never proposed. */
export interface BlockedSeller {
  source: SourcePlatform
  seller_id: string
  reason: string
  blocked_at: string
}

export interface BlockSellerRequest {
  source: SourcePlatform
  external_id: string
  /** Looked up from the listing when not given (Mercari only). */
  seller_id?: string | null
  reason?: string
}

export interface DiscoveryRequest {
  game: Game
  /** Everything included: cards, proxy fees, parcel shipping, estimated import taxes. */
  budget_cents: number
  card_count: number
  /** Left `null`, the scanner's ROI target from the settings. */
  min_roi_percent?: number | null
  sources?: ScannableSource[] | null
  /** quick: ~1 500 listings in 1-2 min; deep: ~5 000 in ~5 min; max: 10 000+ in ~15 min. */
  depth?: DiscoveryDepth
  /** Only listings in this condition or better; those that do not say are left out too. */
  min_condition?: ListingCondition | null
  /** A card name, French and English names searched in Japanese. */
  name?: string | null
  eras?: Era[]
  /** Set codes from the catalog: "sv2a", "op05". */
  sets?: string[]
  /** Catalog rarity ids: "sar", "ar", "sec", "parallel"… */
  rarities?: string[]
  /** Bounds of the card's Cardmarket price. */
  min_market_cents?: number | null
  max_market_cents?: number | null
  /** Bounds of the listing's price; left empty, they follow the budget per card. */
  min_price_jpy?: number | null
  max_price_jpy?: number | null
  /** Listings put online within this many days; those without a date are kept. */
  max_age_days?: number | null
  exclude_mirrors?: boolean
  /** Leaves out cards recognised without their number. */
  confident_only?: boolean
}

export type DiscoveryDepth = 'quick' | 'deep' | 'max'

/** Pokémon eras, from the set codes: "mega" (m1…), "sv", "swsh" (s1…), "sm", "xy", "bw". */
export type Era = 'mega' | 'sv' | 'swsh' | 'sm' | 'xy' | 'bw' | 'older'

export interface DiscoveryEra {
  id: Era
  label: string
  /** "2023-2025" */
  years: string
}

export interface DiscoverySet {
  code: string
  /** As printed on the cards: "SV2a", "OP05". */
  printed: string
  /** Cardmarket's expansion name. */
  name: string | null
  japanese_name: string | null
  era: Era | null
  cards: number
}

export interface DiscoveryRarity {
  id: string
  label: string
  description: string
}

/** What a discovery can be narrowed to, for the search form. */
export interface DiscoveryCatalog {
  game: Game
  eras: DiscoveryEra[]
  sets: DiscoverySet[]
  rarities: DiscoveryRarity[]
}

export interface DiscoveryPick {
  source: SourcePlatform
  external_id: string
  title: string
  price_jpy: number
  shipping_included: boolean | null
  url: string
  neokyo_url: string | null
  thumbnail_url: string | null
  listed_at: string | null
  ends_at: string | null
  bids: number | null
  condition: ListingCondition | null
  /** What the title was read as, e.g. "SV2A 201/165 · SAR". */
  card_label: string
  product: MarketPrice
  /** "medium": several Cardmarket versions share the number, check the price. */
  confidence: 'high' | 'medium'
  confidence_note: string | null
  /** Set when the price is too far below the market to be the real card. */
  warning: string | null
  seller_id: string | null
  /** Why Neokyo would refuse the seller: shown apart, never in the parcel. */
  blocked_reason: string | null
  landed_cost: LandedCost
  sale: SaleBreakdown
}

export interface DiscoveryTotals {
  card_count: number
  purchase_jpy: number
  landed_cents: number
  revenue_cents: number
  net_cents: number
  margin_cents: number
  roi: number | null
  /** Cards without a resale price: their cost counts, their resale does not. */
  unpriced_count: number
}

export interface DiscoveryRun {
  status: 'idle' | 'running' | 'done' | 'failed'
  request: DiscoveryRequest | null
  started_at: string | null
  finished_at: string | null
  searches_done: number
  searches_total: number
  listings_seen: number
  listings_identified: number
  listings_priced: number
  /** The parcel's listings are being checked on their marketplace; sold ones are replaced. */
  verifying: boolean
  listings_checked: number
  listings_gone: number
  /** The parcel, priced as one real lot. */
  picks: DiscoveryPick[]
  totals: DiscoveryTotals | null
  /** Other listings reaching the ROI target, best first. */
  alternatives: DiscoveryPick[]
  /** Listings that would have made it but whose seller Neokyo refuses. */
  blocked: DiscoveryPick[]
  errors: string[]
  /** Stopped by the user: the results cover the listings browsed until then. */
  stopped: boolean
  /** Every step, oldest first: what the page shows while the discovery runs. */
  log: LogLine[]
}

export interface FavoriteFields {
  game: Game
  source: SourcePlatform
  external_id: string
  title: string
  price_jpy: number
  shipping_included: boolean | null
  url: string
  thumbnail_url: string | null
  listed_at: string | null
  ends_at: string | null
  bids: number | null
  condition: ListingCondition | null
  /** What the listing was read as, e.g. "SV2a 201/165 · SAR". */
  card_label: string | null
  cardmarket_product_id: number | null
  /** Resale price chosen by hand; `null` uses the Cardmarket price. */
  target_price_cents: number | null
  in_cart: boolean
  notes: string | null
}

export type FavoriteCreate = Partial<FavoriteFields> &
  Pick<FavoriteFields, 'game' | 'source' | 'external_id' | 'title' | 'price_jpy' | 'url'>

export type FavoriteUpdate = Partial<
  Pick<FavoriteFields, 'in_cart' | 'target_price_cents' | 'notes'>
>

export interface Favorite extends FavoriteFields {
  id: number
  created_at: string
  neokyo_url: string | null
  product: MarketPrice | null
  expected_sale_cents: number | null
  /** In the cart: its share of the cart parcel. Otherwise: one card of a typical parcel. */
  landed_cost: LandedCost
  sale: SaleBreakdown | null
}

export interface Favorites {
  items: Favorite[]
  /** The cart priced as one parcel; `null` when it is empty. */
  cart: DiscoveryTotals | null
}

export interface User {
  id: number
  email: string
  display_name: string
  created_at: string
}

export interface AuthResponse {
  /** Opaque session token, sent back as `Authorization: Bearer`. */
  token: string
  user: User
}

export interface RegisterRequest {
  email: string
  password: string
  display_name: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface AccountUpdate {
  display_name?: string
  /** Required with `new_password`; changing it signs out the other devices. */
  current_password?: string
  new_password?: string
}

/** Searches opened in the browser: the engine never fetches eBay or Vinted pages. */
export interface ResaleLinks {
  ebay_listings: string
  ebay_sold: string
  ebay_research: string
  vinted: string
}

export interface EbayListing {
  item_id: string
  title: string
  price_cents: number
  shipping_cents: number | null
  url: string
  image_url: string | null
  condition: string | null
  country: string | null
}

/** The account's eBay developer keys, as sent from the settings. */
export interface EbayKeysUpdate {
  client_id: string
  /** Left null, the secret already saved is kept: the engine never sends it back. */
  client_secret?: string | null
  marketplace?: string
}

export interface EbayStatus {
  configured: boolean
  /** "account": the account's own keys; "server": the engine's .env, for every account. */
  source: 'account' | 'server' | null
  client_id: string | null
  marketplace: string | null
  /**
   * Whether eBay lets these keys read sold listings (Marketplace Insights); `null` when eBay
   * could not be asked.
   */
  sold_api: boolean | null
}

export interface EbayPrices {
  /** False when the engine has no eBay application keys: only the links work then. */
  configured: boolean
  error: string | null
  total: number
  min_cents: number | null
  median_cents: number | null
  max_cents: number | null
  listings: EbayListing[]
}

export interface ResalePrices {
  query: string
  links: ResaleLinks
  ebay: EbayPrices
}

export interface ResaleQuery {
  q?: string
  product_id?: number
  /** Card label, e.g. "SV2a 201/165 · SAR", whose number refines a product search. */
  label?: string
}

export type ListingSite = 'ebay' | 'vinted'

export interface ListingDraft {
  platform: ListingSite
  title: string
  description: string
  price_cents: number | null
  /** "listing" for the price already set, else the Cardmarket field it comes from. */
  price_source: string | null
  new_listing_url: string
  query: string
  links: ResaleLinks
}

export interface ItemPhoto {
  id: number
  content_type: string
  /** 0 is the main photo, shown first in listings. */
  position: number
}

export interface ResaleOutlet {
  platform: SalePlatform
  sale_cents: number
  /** Where the price comes from, e.g. "Cote Cardmarket, moyenne des ventes sur 30 jours". */
  basis: string
  net_cents: number
  /** Highest price to pay in Japan, shipping included, to reach the target ROI. */
  max_buy_jpy: number | null
  margin_cents: number | null
  roi: number | null
}

export interface VerdictSignal {
  tone: 'positive' | 'warning' | 'negative' | 'neutral'
  text: string
}

export type Verdict = 'good' | 'fair' | 'bad' | 'suspicious' | 'unknown' | 'limit'

export interface CardVerdict {
  verdict: Verdict
  headline: string
  target_roi: number
  price_jpy: number | null
  landed_cents: number | null
  /** Best first. */
  outlets: ResaleOutlet[]
  signals: VerdictSignal[]
  prices: ResalePrices
  /** The number listings must name to count: "201/165", "OP05-119". */
  card_number: string | null
  /** The card's name in French, English and Japanese. */
  card_names: string[]
  /** What to search on each site in Chrome (French names on Vinted). */
  market_queries: Partial<Record<BrowserSite, string>>
}

/** A card in stock, a Japanese listing (with its price) or a catalog product. */
export interface VerdictQuery {
  item_id?: number
  product_id?: number
  label?: string
  q?: string
  price_jpy?: number
  shipping_included?: boolean
}

/** How to track a Cardmarket product, as Japanese listings write the card. */
export interface TrackedCardTemplate {
  game: Game
  name: string
  set_code: string | null
  card_number: string | null
  rarity: string | null
  search_query: string
  /** Which printing this is: "SV2A 201/165 · SAR", "OP05-119 · parallèle". */
  label: string
  /** False for an English printing: Japanese listings sell another card. */
  japanese: boolean
}

export type BrowserSite = 'vinted' | 'ebay'

export interface BrowserStatus {
  chrome_installed: boolean
  /** The Mekiki Chrome window is open. */
  running: boolean
  /** Signed in to each site when Chrome last saw it; a site never checked is missing. */
  connections: Partial<Record<BrowserSite, boolean>>
}

export interface SiteConnection {
  site: BrowserSite
  connected: boolean
}

export interface BrowserPricesRequest {
  query: string
  card_number?: string | null
  names?: string[]
}

export interface MarketListing {
  site: BrowserSite
  external_id: string
  title: string
  price_cents: number
  url: string
  image_url: string | null
  /** Vinted: the condition. eBay: the sale date. */
  detail: string | null
  /** eBay: the sale date read from `detail`, "2026-10-06". */
  sold_on: string | null
  shipping_cents: number | null
  /** eBay: a lower offer was accepted, the real price is unknown. */
  best_offer: boolean
  /** Names the card's number and name, ungraded and alone: counts towards the median. */
  relevant: boolean
}

export interface BrowserPrices {
  site: BrowserSite
  query: string
  listings: MarketListing[]
  relevant_count: number
  median_cents: number | null
  min_cents: number | null
  max_cents: number | null
  /** eBay: sales of the card over the last 30 and 90 days; `null` on Vinted. */
  sales_30_days: number | null
  sales_90_days: number | null
  fetched_at: string
  error: string | null
  /** "api": read through eBay's Marketplace Insights, without Chrome. */
  source: 'chrome' | 'api'
}

export interface PublishRequest {
  title: string
  description: string
  price_cents: number
}

/** A listing being published in Mekiki's Chrome window, and how it ended. */
export interface PublishJob {
  site: BrowserSite
  item_id: number
  started_at: string
  status: 'running' | 'done' | 'failed'
  /** The published listing, once done. */
  url: string | null
  error: string | null
}

/** One step of a long task (Chrome's reading, a discovery), shown in the app's logs. */
export interface LogLine {
  /** UTC timestamp: 2026-10-08T05:12:03Z, with microseconds for discoveries. */
  at: string
  text: string
}

/** What Mekiki's Chrome window is doing, for the live preview. */

/** Something to do now, and the page where it is done. */
export interface Task {
  id: string
  /** Changes when something new comes in: the app notifies once per key. */
  key: string
  title: string
  detail: string
  /** The app's route: "/ventes", "/lots/12". */
  to: string
  tone: 'primary' | 'warning' | 'info' | 'error'
  count: number | null
  /** Worth a Windows notification when its key is new. */
  notify: boolean
}

/** What an import of a platform's sales report did. */
export interface ImportReport {
  lines: number
  /** Recorded on the card whose listing Mekiki published. */
  imported: number
  /** Already imported: only its shipping or tracking changed. */
  updated: number
  /** Waiting for the user to name their card. */
  pending: number
  errors: string[]
  /** When the report could not be read: its headers and the columns not found. */
  headers: string[]
  missing_columns: string[]
}

export interface SuggestedItem {
  item_id: number
  label: string
}

/** A line of a sales report that no card was found for yet. */
export interface PendingSale {
  id: number
  platform: SalePlatform
  title: string
  buyer: string | null
  quantity: number
  sold_on: string
  price_cents: number
  shipping_cents: number
  shipped_on: string | null
  /** The cards it most likely sold, likeliest first. */
  suggestions: SuggestedItem[]
}

export interface Backup {
  /** "mekiki-20261009-021500-000.sqlite3" */
  name: string
  created_at: string
  size_bytes: number
  /** Each kind keeps its own number of copies. */
  kind: 'daily' | 'manual' | 'before-restore'
}

/** The daily copies of the database, newest first. */
export interface Backups {
  folder: string
  backups: Backup[]
  /** Only on the computer that keeps the database. */
  restore_allowed: boolean
  /** Why the latest daily copy failed, if it did. */
  last_error: string | null
}

export interface AuthStatus {
  accounts_exist: boolean
}

export interface BrowserActivity {
  /** "Vinted : « Dracaufeu 201/165 », page 2", or null when idle. */
  activity: string | null
  running: boolean
  /** The window is on screen (sign-in, a form to finish, a bot check to pass). */
  visible: boolean
  /** The latest steps and outcomes, oldest first. */
  log: LogLine[]
}
