import type {
  AccountUpdate,
  AppSettings,
  AuthResponse,
  BrowserActivity,
  BrowserPrices,
  BrowserPricesRequest,
  BrowserSite,
  BrowserStatus,
  CardVerdict,
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
  ItemPhoto,
  ItemUpdate,
  LotCreate,
  LotDetail,
  LotSummary,
  ListingTriage,
  LotUpdate,
  ListingDraft,
  ListingSite,
  LoginRequest,
  MarketPrice,
  PublishJob,
  PublishRequest,
  RegisterRequest,
  SaleUpsert,
  ScanStatus,
  SearchRequest,
  SearchResponse,
  SiteConnection,
  SimulationRequest,
  SimulationResult,
  TrackedCard,
  TrackedCardCreate,
  TrackedCardTemplate,
  TrackedCardUpdate,
  User,
  VerdictQuery,
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
  const token = useSessionToken()
  const endSession = useEndSession()
  const request = $fetch.create({
    baseURL: engineUrl,
    retry: 0,
    onRequest({ options }) {
      if (token.value) options.headers.set('Authorization', `Bearer ${token.value}`)
    },
    async onResponseError({ response, options }) {
      // A session refused while signed in has expired or was revoked (password changed
      // elsewhere): back to the sign-in page, which says why.
      if (response.status === 401 && options.headers.has('Authorization')) {
        await endSession({ path: '/connexion', query: { session: 'expiree' } })
      }
    },
  })

  return {
    health: () => request<{ status: string; version: string }>('/health', { timeout: 2000 }),

    register: (body: RegisterRequest) =>
      request<AuthResponse>('/auth/register', { method: 'POST', body }),
    login: (body: LoginRequest) => request<AuthResponse>('/auth/login', { method: 'POST', body }),
    logout: async (): Promise<void> => {
      await request('/auth/logout', { method: 'POST' })
    },
    me: () => request<User>('/auth/me'),
    updateMe: (body: AccountUpdate) => request<User>('/auth/me', { method: 'PATCH', body }),

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

    getItem: (id: number) => request<Item>(`/items/${id}`),
    addItem: (lotId: number, body: ItemCreate) =>
      request<Item>(`/lots/${lotId}/items`, { method: 'POST', body }),
    updateItem: (id: number, body: ItemUpdate) =>
      request<Item>(`/items/${id}`, { method: 'PATCH', body }),
    deleteItem: async (id: number): Promise<void> => {
      await request(`/items/${id}`, { method: 'DELETE' })
    },

    addPhoto: (itemId: number, contentBase64: string) =>
      request<ItemPhoto[]>(`/items/${itemId}/photos`, {
        method: 'POST',
        body: { content_base64: contentBase64 },
        timeout: 60_000,
      }),
    photoBlob: (itemId: number, photoId: number) =>
      request<Blob>(`/items/${itemId}/photos/${photoId}`, { responseType: 'blob' }),
    movePhotoFirst: (itemId: number, photoId: number) =>
      request<ItemPhoto[]>(`/items/${itemId}/photos/${photoId}/first`, { method: 'POST' }),
    deletePhoto: (itemId: number, photoId: number) =>
      request<ItemPhoto[]>(`/items/${itemId}/photos/${photoId}`, { method: 'DELETE' }),

    recordSale: (itemId: number, body: SaleUpsert) =>
      request<Item>(`/items/${itemId}/sale`, { method: 'PUT', body }),
    cancelSale: (itemId: number) => request<Item>(`/items/${itemId}/sale`, { method: 'DELETE' }),

    inventory: (query: InventoryQuery = {}) => request<Item[]>('/inventory', { query }),
    dashboard: (query: DashboardQuery = {}) => request<Dashboard>('/dashboard', { query }),
    simulate: (body: SimulationRequest) =>
      request<SimulationResult>('/simulate', { method: 'POST', body }),

    listTrackedCards: () => request<TrackedCard[]>('/tracked-cards'),
    trackedCardTemplate: (productId: number) =>
      request<TrackedCardTemplate>('/tracked-cards/template', {
        query: { product_id: productId },
      }),
    createTrackedCard: (body: TrackedCardCreate) =>
      request<TrackedCard>('/tracked-cards', { method: 'POST', body }),
    updateTrackedCard: (id: number, body: TrackedCardUpdate) =>
      request<TrackedCard>(`/tracked-cards/${id}`, { method: 'PATCH', body }),
    deleteTrackedCard: async (id: number): Promise<void> => {
      await request(`/tracked-cards/${id}`, { method: 'DELETE' })
    },

    searchProducts: (game: Game, q: string) =>
      request<MarketPrice[]>('/cardmarket/products', { query: { game, q } }),
    getProduct: (id: number) => request<MarketPrice>(`/cardmarket/products/${id}`),
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
    verdict: (query: VerdictQuery) =>
      request<CardVerdict>('/resale/verdict', { query, timeout: 30_000 }),
    listingDraft: (itemId: number, platform: ListingSite) =>
      request<ListingDraft>(`/items/${itemId}/listing-draft`, { query: { platform } }),
    browserStatus: () => request<BrowserStatus>('/browser/status'),
    browserActivity: () => request<BrowserActivity>('/browser/activity'),
    showBrowser: () => request<BrowserActivity>('/browser/show', { method: 'POST' }),
    hideBrowser: () => request<BrowserActivity>('/browser/hide', { method: 'POST' }),
    openSite: (site: BrowserSite) =>
      request<BrowserStatus>(`/browser/${site}/open`, { method: 'POST', timeout: 60_000 }),
    checkSite: (site: BrowserSite) =>
      request<SiteConnection>(`/browser/${site}/check`, { method: 'POST', timeout: 60_000 }),
    sitePrices: (site: BrowserSite, body: BrowserPricesRequest) =>
      request<BrowserPrices>(`/browser/${site}/prices`, { method: 'POST', body, timeout: 90_000 }),
    publishListing: (site: BrowserSite, itemId: number, body: PublishRequest) =>
      request<PublishJob>(`/browser/${site}/publish/${itemId}`, { method: 'POST', body }),
    publishStatus: (site: BrowserSite, itemId: number) =>
      request<PublishJob | null>(`/browser/${site}/publish/${itemId}`),
    search: (body: SearchRequest) =>
      request<SearchResponse>('/search', { method: 'POST', body, timeout: 120_000 }),
  }
}

export type EngineClient = ReturnType<typeof useEngine>
