<script setup lang="ts">
import type { Task } from '~/types/engine'

/** Everything to do now, gathered by the engine, each leading to the page where it is done. */
const { tasks, refresh, muted, setMuted } = useTasks()
const loading = ref(true)
onMounted(async () => {
  await refresh()
  loading.value = false
})

const LOOKS: Record<Task['tone'], { icon: string; class: string }> = {
  error: { icon: 'i-lucide-octagon-alert', class: 'bg-error/10 text-error' },
  warning: { icon: 'i-lucide-clock-alert', class: 'bg-warning/10 text-warning' },
  primary: { icon: 'i-lucide-sparkles', class: 'bg-primary/10 text-primary' },
  info: { icon: 'i-lucide-circle-dot', class: 'bg-elevated text-muted' },
}
const ICONS: Record<string, string> = {
  deals: 'i-lucide-tag',
  ship: 'i-lucide-truck',
  receive: 'i-lucide-package-open',
  list: 'i-lucide-store',
  dormant: 'i-lucide-moon',
  declaration: 'i-lucide-landmark',
  backup: 'i-lucide-hard-drive',
}
function icon(task: Task) {
  return ICONS[task.id.split(':')[0] ?? ''] ?? LOOKS[task.tone].icon
}

const inApp = import.meta.client && '__TAURI_INTERNALS__' in window
</script>

<template>
  <UDashboardPanel id="tasks">
    <template #header>
      <PageNavbar
        title="À faire"
        description="Ce qui attend : ventes à expédier, déclarations, lots à réceptionner, bonnes affaires…"
      >
        <template v-if="inApp" #right>
          <USwitch
            :model-value="!muted"
            label="Notifications Windows"
            @update:model-value="(on) => setMuted(!on)"
          />
        </template>
      </PageNavbar>
    </template>

    <template #body>
      <div v-if="loading && !tasks.length" class="flex justify-center py-12">
        <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-muted" />
      </div>
      <UEmpty
        v-else-if="!tasks.length"
        icon="i-lucide-party-popper"
        title="Rien à faire pour l’instant"
        description="Les ventes à expédier, les déclarations à faire et les nouvelles bonnes affaires apparaîtront ici."
      />
      <ul v-else class="space-y-2.5">
        <li v-for="task in tasks" :key="task.id">
          <NuxtLink
            :to="task.to"
            class="group flex items-center gap-4 rounded-lg border border-default bg-muted p-4 transition-colors hover:border-accented"
          >
            <span
              class="flex size-10 shrink-0 items-center justify-center rounded-lg"
              :class="LOOKS[task.tone].class"
            >
              <UIcon :name="icon(task)" class="size-5" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block font-semibold text-highlighted group-hover:underline">
                {{ task.title }}
              </span>
              <span class="block truncate text-sm text-muted">{{ task.detail }}</span>
            </span>
            <UIcon
              name="i-lucide-chevron-right"
              class="size-5 shrink-0 text-dimmed group-hover:text-highlighted"
            />
          </NuxtLink>
        </li>
      </ul>
    </template>
  </UDashboardPanel>
</template>
