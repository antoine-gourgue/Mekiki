export type EngineStatus = 'connecting' | 'online' | 'offline'

// In release the engine is a sidecar that needs a few seconds to unpack and start, so the UI
// keeps "connecting" for a while before calling it offline.
const STARTUP_GRACE_MS = 20_000
const FAST_POLL_MS = 500
const SLOW_POLL_MS = 5_000

/**
 * Shared engine reachability, polled from the layout with `startPolling()`.
 * Pages are only rendered once the engine is online, so their first fetch can rely on it.
 */
export function useEngineStatus() {
  const status = useState<EngineStatus>('engine-status', () => 'connecting')
  const engine = useEngine()

  function startPolling(): () => void {
    const startedAt = Date.now()
    let timer: ReturnType<typeof setTimeout> | undefined
    let stopped = false

    async function check() {
      try {
        await engine.health()
        status.value = 'online'
      } catch {
        const inGrace = status.value === 'connecting' && Date.now() - startedAt < STARTUP_GRACE_MS
        status.value = inGrace ? 'connecting' : 'offline'
      }
      if (!stopped) {
        timer = setTimeout(check, status.value === 'connecting' ? FAST_POLL_MS : SLOW_POLL_MS)
      }
    }

    void check()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }

  return { status, startPolling }
}
