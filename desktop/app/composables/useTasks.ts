import type { Task } from '~/types/engine'

const NOTIFIED_KEY = 'mekiki:notified'
const MUTED_KEY = 'mekiki:notifications-off'
const REMEMBERED = 300

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw == null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Without storage, a task may be notified again after a restart: harmless.
  }
}

/**
 * What to do now (see the engine's tasks), shared by the sidebar, the dashboard and the
 * "À faire" page; `refresh` also sends a Windows notification for each new task worth one.
 */
export function useTasks() {
  const engine = useEngine()
  const auth = useAuth()
  const tasks = useState<Task[]>('tasks', () => [])
  const muted = useState<boolean>('tasks-muted', () => read(MUTED_KEY, false))

  async function refresh() {
    try {
      tasks.value = await engine.tasks()
    } catch {
      // The engine status dot already says when it is down; the last list stays.
      return
    }
    await notify(tasks.value)
  }

  async function notify(current: Task[]) {
    const userId = auth.user.value?.id
    if (userId == null || !('__TAURI_INTERNALS__' in window)) return
    const storageKey = `${NOTIFIED_KEY}:${userId}`
    const known = read<string[] | null>(storageKey, null)
    const keys = current.filter((task) => task.notify).map((task) => task.key)
    // The first check on this computer finds what was already there: that is no news.
    const fresh = known ? current.filter((task) => task.notify && !known.includes(task.key)) : []
    write(storageKey, [...new Set([...(known ?? []), ...keys])].slice(-REMEMBERED))
    if (!fresh.length || muted.value) return
    const { isPermissionGranted, requestPermission, sendNotification } =
      await import('@tauri-apps/plugin-notification')
    const granted = (await isPermissionGranted()) || (await requestPermission()) === 'granted'
    if (!granted) return
    for (const task of fresh) sendNotification({ title: task.title, body: task.detail })
  }

  function setMuted(value: boolean) {
    muted.value = value
    write(MUTED_KEY, value)
  }

  return { tasks, refresh, muted, setMuted }
}
