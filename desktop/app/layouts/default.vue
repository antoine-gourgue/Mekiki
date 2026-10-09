<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'
import type { BrowserActivity } from '~/types/engine'

const engine = useEngine()
const favorites = useFavorites()
const auth = useAuth()

// Good deals not looked at yet and what Chrome is doing, refreshed every 30 seconds.
const unseenDeals = ref(0)
const chrome = ref<BrowserActivity | null>(null)
let statusTimer: ReturnType<typeof setInterval> | undefined
async function refreshSidebar() {
  const [scan, activity] = await Promise.allSettled([engine.scanStatus(), engine.browserActivity()])
  // A failure keeps the last value: the engine status dot already says when it is down.
  if (scan.status === 'fulfilled') unseenDeals.value = scan.value.unseen_deals
  if (activity.status === 'fulfilled') chrome.value = activity.value
}

const links = computed<NavigationMenuItem[][]>(() => [
  [
    { label: 'Tableau de bord', icon: 'i-lucide-layout-dashboard', to: '/' },
    { label: 'Acheter au Japon', type: 'label' },
    { label: 'Trouver des cartes', icon: 'i-lucide-wand-sparkles', to: '/decouverte' },
    {
      label: 'Bonnes affaires',
      icon: 'i-lucide-tag',
      to: '/affaires',
      badge: unseenDeals.value
        ? { label: String(unseenDeals.value), color: 'primary', variant: 'soft' }
        : undefined,
    },
    { label: 'Recherche', icon: 'i-lucide-search', to: '/recherche' },
    { label: 'Cartes suivies', icon: 'i-lucide-eye', to: '/suivi' },
    {
      label: 'Panier',
      icon: 'i-lucide-shopping-cart',
      to: '/panier',
      badge: favorites.cartCount.value
        ? { label: String(favorites.cartCount.value), color: 'neutral', variant: 'soft' }
        : undefined,
    },
    { label: 'Stock et ventes', type: 'label' },
    { label: 'Lots', icon: 'i-lucide-package', to: '/lots' },
    { label: 'Stock', icon: 'i-lucide-layers', to: '/stock' },
    { label: 'Ventes', icon: 'i-lucide-receipt-euro', to: '/ventes' },
    { label: 'Comptabilité', icon: 'i-lucide-landmark', to: '/compta' },
    { label: 'Outils', type: 'label' },
    { label: 'Simulateur', icon: 'i-lucide-calculator', to: '/simulateur' },
    { label: 'Paramètres', icon: 'i-lucide-sliders-horizontal', to: '/parametres' },
  ],
])

const chromeState = computed(() => {
  if (!chrome.value?.running) return 'fermé'
  return chrome.value.visible ? 'à l’écran' : 'hors écran'
})

const { status, startPolling } = useEngineStatus()
let stopPolling: (() => void) | undefined
onMounted(() => (stopPolling = startPolling()))
onBeforeUnmount(() => stopPolling?.())

// Pages load their data on mount, so they wait until the engine has answered once.
const ready = ref(false)
watch(
  status,
  (value) => {
    if (value !== 'online' || ready.value) return
    ready.value = true
    void refreshSidebar()
    void favorites.refresh()
    auth.loadUser().catch(() => {
      // A refused session already sends the user back to the sign-in page.
    })
    statusTimer = setInterval(refreshSidebar, 30_000)
  },
  { immediate: true },
)
onBeforeUnmount(() => clearInterval(statusTimer))

// Collapsed, the sidebar is a column of square icons: the expanded paddings would push
// them off center and make their hover box narrower than tall.
const collapsed = ref(false)
const COLLAPSED_SIDEBAR = { header: 'px-3 justify-center', body: 'px-3', footer: 'px-3' }

const initial = computed(() => (auth.user.value?.display_name ?? '?').slice(0, 1).toUpperCase())
</script>

<template>
  <UDashboardGroup unit="rem">
    <UDashboardSidebar
      v-model:collapsed="collapsed"
      collapsible
      resizable
      :default-size="16"
      :ui="collapsed ? COLLAPSED_SIDEBAR : undefined"
    >
      <template #header>
        <AppLogo :collapsed="collapsed" :class="collapsed ? 'mx-auto' : ''" />
      </template>

      <template #default>
        <UDashboardSearchButton
          :collapsed="collapsed"
          label="Rechercher…"
          class="bg-muted ring-default"
        />
        <UNavigationMenu
          :collapsed="collapsed"
          :items="links"
          orientation="vertical"
          color="neutral"
          tooltip
          :ui="{
            label:
              'mt-4 px-3 pb-1 text-[11px] font-semibold tracking-[0.14em] uppercase text-dimmed',
            link: [
              'h-10 text-muted before:rounded-md hover:before:bg-elevated aria-[current=page]:text-highlighted aria-[current=page]:before:bg-elevated aria-[current=page]:before:ring-1 aria-[current=page]:before:ring-default',
              collapsed ? 'w-10 justify-center px-0' : 'gap-3 px-3',
            ].join(' '),
            linkLeadingIcon: 'size-[18px] group-aria-[current=page]:text-primary',
          }"
        />
      </template>

      <template #footer>
        <div class="flex w-full flex-col gap-2">
          <NuxtLink
            v-if="!collapsed"
            to="/compte"
            class="rounded-lg border border-default px-3 py-2.5 text-xs transition-colors hover:bg-elevated/50"
          >
            <span class="flex items-center justify-between gap-2">
              <span class="text-muted">Chrome</span>
              <span class="font-mono text-dimmed">{{ chromeState }}</span>
            </span>
            <span class="mt-1 block truncate text-toned">
              {{ chrome?.activity ?? 'Vinted et eBay' }}
            </span>
          </NuxtLink>

          <NuxtLink
            to="/compte"
            class="flex items-center gap-2.5 rounded-md transition-colors hover:bg-elevated"
            :class="collapsed ? 'size-10 justify-center' : 'p-2'"
            active-class="bg-elevated"
            :aria-label="collapsed ? 'Mon compte' : undefined"
          >
            <span
              class="flex size-8 shrink-0 items-center justify-center rounded-full bg-accented text-sm font-semibold text-highlighted"
            >
              {{ initial }}
            </span>
            <span v-if="!collapsed" class="min-w-0 flex-1">
              <span class="block truncate text-sm font-medium text-highlighted">
                {{ auth.user.value?.display_name ?? 'Mon compte' }}
              </span>
              <span class="flex items-center gap-1.5 text-xs text-dimmed">
                <span
                  class="size-1.5 shrink-0 rounded-full"
                  :class="{
                    'bg-success': status === 'online',
                    'animate-pulse bg-warning': status === 'connecting',
                    'bg-error': status === 'offline',
                  }"
                />
                {{
                  status === 'online'
                    ? 'Moteur connecté'
                    : status === 'connecting'
                      ? 'Connexion au moteur…'
                      : 'Moteur injoignable'
                }}
              </span>
            </span>
          </NuxtLink>
        </div>
      </template>
    </UDashboardSidebar>

    <AppSearch :links="links" />
    <DrawerHost />

    <slot v-if="ready" />
    <UDashboardPanel v-else id="engine-wait">
      <template #body>
        <UEmpty
          v-if="status === 'connecting'"
          icon="i-lucide-loader-circle"
          title="Démarrage du moteur…"
          description="Mekiki attend son moteur de calcul local."
          class="m-auto"
          :ui="{ avatar: 'animate-spin' }"
        />
        <UEmpty
          v-else
          icon="i-lucide-plug-zap"
          title="Le moteur ne répond pas"
          description="En développement, lancez-le dans un autre terminal avec « npm run engine » (dossier desktop). Cette page se reconnecte toute seule."
          class="m-auto max-w-md"
        />
      </template>
    </UDashboardPanel>
  </UDashboardGroup>
</template>
