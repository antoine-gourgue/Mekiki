import type { RouteLocationRaw } from 'vue-router'
import type {
  AccountUpdate,
  AuthResponse,
  LoginRequest,
  RegisterRequest,
  User,
} from '~/types/engine'

const TOKEN_KEY = 'mekiki:session'

// Storage can be unavailable (private window, blocked site data): the session then lasts
// until the window closes.
function readStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function storeToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // See readStoredToken.
  }
}

/** The session token alone; `useEngine` reads it for every call. */
export function useSessionToken() {
  return useState<string | null>('auth-token', readStoredToken)
}

/**
 * Forgets the session locally, along with every cached page of the previous account, then
 * optionally leaves for another page. Safe to call from fetch hooks, outside a component.
 */
export function useEndSession() {
  const nuxtApp = useNuxtApp()
  const token = useSessionToken()
  return (to?: RouteLocationRaw) =>
    nuxtApp.runWithContext(async () => {
      storeToken(null)
      clearNuxtData()
      clearNuxtState((key) => key !== 'engine-status' && key !== 'auth-token')
      token.value = null
      if (to) await navigateTo(to)
    })
}

/**
 * The signed-in account. The token lives in local storage so the app reopens signed in;
 * the user is fetched from the engine when a page first needs it.
 */
export function useAuth() {
  const token = useSessionToken()
  const user = useState<User | null>('auth-user', () => null)
  const engine = useEngine()
  const endSession = useEndSession()

  function start(response: AuthResponse) {
    storeToken(response.token)
    token.value = response.token
    user.value = response.user
  }

  return {
    token,
    user,
    signedIn: computed(() => Boolean(token.value)),

    async login(body: LoginRequest) {
      start(await engine.login(body))
    },
    async register(body: RegisterRequest) {
      start(await engine.register(body))
    },
    async loadUser() {
      if (token.value && !user.value) user.value = await engine.me()
      return user.value
    },
    async update(body: AccountUpdate) {
      user.value = await engine.updateMe(body)
    },
    async logout() {
      try {
        await engine.logout()
      } catch {
        // Signed out locally either way; the server session simply expires.
      }
      await endSession('/connexion')
    },
  }
}
