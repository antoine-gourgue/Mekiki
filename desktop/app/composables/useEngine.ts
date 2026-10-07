import type {
  AppSettings,
  CardmarketStatus,
  Dashboard,
  Deal,
  DealQuery,
  DiscoveryRequest,
  DiscoveryRun,
  FavoriteCreate,
  Favorites,
  FavoriteUpdate,
  Game,
  DashboardQuery,
  InventoryQuery,
  Item,
  ItemCreate,
  ItemUpdate,
  LotCreate,
  LotDetail,
  LotSummary,
  ListingTriage,
  LotUpdate,
  MarketPrice,
  SaleUpsert,
  ScanStatus,
  SearchRequest,
  SearchResponse,
  SimulationRequest,
  SimulationResult,
  TrackedCard,
  TrackedCardCreate,
  TrackedCardUpdate,
} from '~/types/engine'

/**
 * Typed client for the local engine (FastAPI on 127.0.0.1).
 *
 * The base URL comes from `runtimeConfig.public.engineUrl` (`NUXT_PUBLIC_ENGINE_URL`).
 * Every method rejects with an ofetch `FetchError`; `engineErrorMessage()` turns it into
 * a message for the UI.
 */
export function useEngine() {
  const { engineUrl } = useRuntimeConfig().public
  const request = $fetch.create({ baseURL: engineUrl, retry: 0 })

  return {
    health: () => request<{ status: string; version: string }>('/health', { timeout: 2000 }),

    getSettings: () => request<AppSettings>('/settings'),
    saveSettings: (body: AppSettings) => request<AppSettings>('/settings', { method: 'PUT', body }),

    listLots: () => request<LotSummary[]>('/lots'),
    getLot: (id: number) => request<LotDetail>(`/lots/${id}`),
    createLot: (body: LotCreate) => request<LotDetail>('/lots', { method: 'POST', body }),
    updateLot: (id: number, body: LotUpdate) =>
      request<LotDetail>(`/lots/${id}`, { method: 'PATCH', body }),
    deleteLot: async (id: number): Promise<void> => {
      await request(`/lots/${id}`, { method: 'DELETE' })
    },

    addItem: (lotId: number, body: ItemCreate) =>
      request<Item>(`/lots/${lotId}/items`, { method: 'POST', body }),
    updateItem: (id: number, body: ItemUpdate) =>
      request<Item>(`/items/${id}`, { method: 'PATCH', body }),
    deleteItem: async (id: number): Promise<void> => {
      await request(`/items/${id}`, { method: 'DELETE' })
    },

    recordSale: (itemId: number, body: SaleUpsert) =>
      request<Item>(`/items/${itemId}/sale`, { method: 'PUT', body }),
    cancelSale: (itemId: number) => request<Item>(`/items/${itemId}/sale`, { method: 'DELETE' }),

    inventory: (query: InventoryQuery = {}) => request<Item[]>('/inventory', { query }),
    dashboard: (query: DashboardQuery = {}) => request<Dashboard>('/dashboard', { query }),
    simulate: (body: SimulationRequest) =>
      request<SimulationResult>('/simulate', { method: 'POST', body }),

    listTrackedCards: () => request<TrackedCard[]>('/tracked-cards'),
    createTrackedCard: (body: TrackedCardCreate) =>
      request<TrackedCard>('/tracked-cards', { method: 'POST', body }),
    updateTrackedCard: (id: number, body: TrackedCardUpdate) =>
      request<TrackedCard>(`/tracked-cards/${id}`, { method: 'PATCH', body }),
    deleteTrackedCard: async (id: number): Promise<void> => {
      await request(`/tracked-cards/${id}`, { method: 'DELETE' })
    },

    searchProducts: (game: Game, q: string) =>
      request<MarketPrice[]>('/cardmarket/products', { query: { game, q } }),
    cardmarketStatus: () => request<CardmarketStatus[]>('/cardmarket/status'),
    refreshCardmarket: () =>
      request<CardmarketStatus[]>('/cardmarket/refresh', { method: 'POST', body: {} }),

    listDeals: (query: DealQuery = {}) => request<Deal[]>('/deals', { query }),
    updateDeal: (id: number, triage: ListingTriage) =>
      request<Deal>(`/deals/${id}`, { method: 'PATCH', body: { triage } }),
    markDealsSeen: () =>
      request<{ updated: number }>('/deals/mark-seen', { method: 'POST', body: {} }),

    scanStatus: () => request<ScanStatus>('/scanner/status'),
    runScan: () => request<ScanStatus>('/scanner/run', { method: 'POST', body: {} }),
    discovery: () => request<DiscoveryRun>('/discovery'),
    startDiscovery: (body: DiscoveryRequest) =>
      request<DiscoveryRun>('/discovery', { method: 'POST', body }),
    stopDiscovery: () => request<DiscoveryRun>('/discovery/stop', { method: 'POST', body: {} }),
    listFavorites: () => request<Favorites>('/favorites'),
    addFavorite: (body: FavoriteCreate) =>
      request<Favorites>('/favorites', { method: 'POST', body }),
    updateFavorite: (id: number, body: FavoriteUpdate) =>
      request<Favorites>(`/favorites/${id}`, { method: 'PATCH', body }),
    deleteFavorite: (id: number) => request<Favorites>(`/favorites/${id}`, { method: 'DELETE' }),
    emptyCart: () => request<Favorites>('/favorites/empty-cart', { method: 'POST', body: {} }),
    search: (body: SearchRequest) =>
      request<SearchResponse>('/search', { method: 'POST', body, timeout: 120_000 }),
  }
}

export type EngineClient = ReturnType<typeof useEngine>
