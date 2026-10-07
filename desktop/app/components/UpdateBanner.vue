<script setup lang="ts">
import type { Update } from '@tauri-apps/plugin-updater'

/**
 * Offers a new version of the desktop app when one is released on GitHub: download,
 * install, restart. It floats over the page, which the dashboard fills entirely. Nothing
 * shows in a browser or when the app is up to date.
 */
const update = shallowRef<Update | null>(null)
const progress = ref<number | null>(null)
const failure = ref<string | null>(null)
const dismissed = ref(false)

onMounted(async () => {
  if (!('__TAURI_INTERNALS__' in window)) return
  try {
    const { check } = await import('@tauri-apps/plugin-updater')
    update.value = await check()
  } catch {
    // Offline, or no release published yet: the app keeps working as it is.
  }
})

async function install() {
  const pending = update.value
  if (!pending) return
  failure.value = null
  progress.value = 0
  let total = 0
  let received = 0
  try {
    await pending.downloadAndInstall((event) => {
      if (event.event === 'Started') total = event.data.contentLength ?? 0
      if (event.event === 'Progress') {
        received += event.data.chunkLength
        progress.value = total ? Math.round((received / total) * 100) : null
      }
    })
    const { relaunch } = await import('@tauri-apps/plugin-process')
    await relaunch()
  } catch (error) {
    progress.value = null
    failure.value = error instanceof Error ? error.message : String(error)
  }
}
</script>

<template>
  <div
    v-if="update && !dismissed"
    class="fixed bottom-4 left-1/2 z-50 flex w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 flex-wrap items-center gap-3 rounded-lg border border-default bg-default px-4 py-3 text-sm shadow-lg"
  >
    <UIcon name="i-lucide-sparkles" class="size-4 shrink-0 text-primary" />
    <p class="min-w-0 flex-1">
      <span class="font-medium">Mekiki {{ update.version }} est disponible.</span>
      <span v-if="failure" class="text-error"> La mise à jour a échoué : {{ failure }}</span>
      <span v-else-if="progress !== null" class="text-muted">
        Téléchargement{{ progress ? ` ${progress} %` : '…' }}, l’app redémarrera toute seule.
      </span>
      <span v-else class="text-muted"> Installez-la pour profiter des nouveautés.</span>
    </p>
    <UButton
      size="xs"
      icon="i-lucide-download"
      label="Mettre à jour"
      :loading="progress !== null && !failure"
      @click="install"
    />
    <UButton
      v-if="progress === null"
      size="xs"
      color="neutral"
      variant="ghost"
      label="Plus tard"
      @click="dismissed = true"
    />
  </div>
</template>
