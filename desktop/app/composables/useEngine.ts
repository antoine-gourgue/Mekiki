import type {
  AppSettings,
  Dashboard,
  DashboardQuery,
  InventoryQuery,
  Item,
  ItemCreate,
  ItemUpdate,
  LotCreate,
  LotDetail,
  LotSummary,
  LotUpdate,
  SaleUpsert,
  SimulationRequest,
  SimulationResult,
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
  }
}

export type EngineClient = ReturnType<typeof useEngine>
