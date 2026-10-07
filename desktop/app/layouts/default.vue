<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'

const links: NavigationMenuItem[] = [
  { label: 'Tableau de bord', icon: 'i-lucide-layout-dashboard', to: '/' },
  { label: 'Simulateur', icon: 'i-lucide-calculator', to: '/simulateur' },
  { label: 'Lots', icon: 'i-lucide-package', to: '/lots' },
  { label: 'Stock', icon: 'i-lucide-layers', to: '/stock' },
  { label: 'Ventes', icon: 'i-lucide-receipt-euro', to: '/ventes' },
  { label: 'Paramètres', icon: 'i-lucide-settings', to: '/parametres' },
]

const { status, startPolling } = useEngineStatus()
let stopPolling: (() => void) | undefined
onMounted(() => (stopPolling = startPolling()))
onBeforeUnmount(() => stopPolling?.())

// Pages load their data on mount, so they wait until the engine has answered once.
const ready = ref(false)
watch(status, (value) => value === 'online' && (ready.value = true), { immediate: true })
</script>

<template>
  <UDashboardGroup unit="rem">
    <UDashboardSidebar
      collapsible
      resizable
      :default-size="15"
      :ui="{ footer: 'border-t border-default' }"
    >
      <template #header="{ collapsed }">
        <div class="flex items-center gap-2 px-1">
          <span class="text-lg font-semibold text-primary">目利き</span>
          <span v-if="!collapsed" class="font-semibold text-highlighted">Mekiki</span>
        </div>
      </template>

      <template #default="{ collapsed }">
        <UNavigationMenu :collapsed="collapsed" :items="links" orientation="vertical" tooltip />
      </template>

      <template #footer="{ collapsed }">
        <div class="flex items-center gap-2 px-1 text-xs text-muted">
          <span
            class="size-2 shrink-0 rounded-full"
            :class="{
              'bg-success': status === 'online',
              'bg-warning animate-pulse': status === 'connecting',
              'bg-error': status === 'offline',
            }"
          />
          <span v-if="!collapsed">
            {{
              status === 'online'
                ? 'Moteur connecté'
                : status === 'connecting'
                  ? 'Connexion au moteur…'
                  : 'Moteur injoignable'
            }}
          </span>
        </div>
      </template>
    </UDashboardSidebar>

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
