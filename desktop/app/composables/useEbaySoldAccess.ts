/** What lets the app read a card's eBay sales: eBay's API, or Chrome signed in to eBay. */
export interface EbaySoldAccess {
  /** eBay's Marketplace Insights is open to the account's keys. */
  api: boolean
  /** Chrome's last known eBay sign-in; `null` when never checked. */
  signedIn: boolean | null
}

/**
 * The access shared by every card panel and the accounts card (`null` until first loaded),
 * and `refresh`, which reads it again without opening Chrome: the engine remembers the
 * sign-in it last saw, and asks eBay once per keyset whether its API is open.
 */
export function useEbaySoldAccess() {
  const engine = useEngine()
  const access = useState<EbaySoldAccess | null>('ebay-sold-access', () => null)

  async function refresh() {
    const [browser, keys] = await Promise.allSettled([engine.browserStatus(), engine.ebayStatus()])
    access.value = {
      api: keys.status === 'fulfilled' && keys.value.sold_api === true,
      signedIn: browser.status === 'fulfilled' ? (browser.value.connections.ebay ?? null) : null,
    }
  }

  return { access, refresh }
}
