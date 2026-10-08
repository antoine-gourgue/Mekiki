<script setup lang="ts">
import type { Update } from '@tauri-apps/plugin-updater'

/**
 * Offers a new version of the desktop app when one is released on GitHub: what changes
 * (the release notes, written in French), then download, install and restart. Nothing
 * shows in a browser or when the app is up to date.
 */
const update = shallowRef<Update | null>(null)
const open = ref(false)
const progress = ref<number | null>(null)
const failure = ref<string | null>(null)
const installing = computed(() => progress.value !== null && !failure.value)

onMounted(async () => {
  if (!('__TAURI_INTERNALS__' in window)) return
  try {
    const { check } = await import('@tauri-apps/plugin-updater')
    update.value = await check()
    open.value = update.value !== null
  } catch {
    // Offline, or no release published yet: the app keeps working as it is.
  }
})

interface NoteLine {
  kind: 'title' | 'item' | 'text'
  text: string
}

/** The notes are the Markdown of the release page: titles, bullets and lines are enough here. */
const notes = computed<NoteLine[]>(() =>
  (update.value?.body ?? '')
    .split(/\r?\n/)
    .map((line) =>
      line
        .trim()
        .replace(/\*\*(.+?)\*\*/g, '$1')
        .replace(/`([^`]+)`/g, '$1'),
    )
    .filter(Boolean)
    .map((line) => {
      if (/^#{1,6}\s/.test(line)) return { kind: 'title', text: line.replace(/^#+\s*/, '') }
      if (/^[-*]\s/.test(line)) return { kind: 'item', text: line.slice(2) }
      return { kind: 'text', text: line }
    }),
)

const subtitle = computed(() => {
  const current = update.value
  if (!current) return undefined
  return [
    `Vous avez la version ${current.currentVersion}`,
    current.date ? `publiée le ${formatDate(current.date)}` : null,
  ]
    .filter(Boolean)
    .join(' · ')
})

/** The updater's errors are English and technical: the user gets what to do instead. */
function explain(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error)
  if (/signature/i.test(message)) {
    return 'La mise à jour n’a pas pu être vérifiée : sa signature ne correspond pas à cette version de Mekiki. Installez-la avec l’installateur.'
  }
  if (/network|connect|timed? ?out|dns|request|status/i.test(message)) {
    return 'Le téléchargement a échoué. Vérifiez votre connexion internet, puis réessayez.'
  }
  return 'La mise à jour n’a pas pu être installée. Réessayez, ou installez-la avec l’installateur.'
}

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
    console.error('Mise à jour impossible', error)
    progress.value = null
    failure.value = explain(error)
  }
}
</script>

<template>
  <UModal
    v-if="update"
    v-model:open="open"
    :title="`Mekiki ${update.version} est disponible`"
    :description="subtitle"
    :dismissible="!installing"
    :close="!installing"
    :ui="{
      content: 'sm:max-w-xl',
      header: 'px-6 pt-6 pb-4 sm:px-6',
      title: 'text-xl font-semibold tracking-tight',
      body: 'space-y-5 px-6 sm:px-6',
      footer: 'justify-end gap-2 px-6 pb-6 sm:px-6',
    }"
  >
    <template #body>
      <section class="space-y-3">
        <h3 class="text-xs font-semibold tracking-[0.12em] text-dimmed uppercase">Nouveautés</h3>
        <div class="max-h-80 space-y-2 overflow-y-auto pe-1 text-sm">
          <template v-for="(line, index) in notes" :key="index">
            <p v-if="line.kind === 'title'" class="pt-2 font-semibold text-highlighted first:pt-0">
              {{ line.text }}
            </p>
            <p v-else-if="line.kind === 'item'" class="flex gap-2.5 text-toned">
              <span class="mt-2 size-1.5 shrink-0 rounded-full bg-primary" />
              <span>{{ line.text }}</span>
            </p>
            <p v-else class="text-toned">{{ line.text }}</p>
          </template>
          <p v-if="!notes.length" class="text-toned">Corrections et améliorations.</p>
        </div>
      </section>

      <div v-if="installing" class="space-y-2">
        <UProgress :model-value="progress ?? undefined" />
        <p class="text-sm text-muted">
          Téléchargement{{ progress ? ` ${progress} %` : '…' }}. Mekiki redémarrera tout seul.
        </p>
      </div>

      <UAlert
        v-if="failure"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        title="La mise à jour a échoué"
        :description="failure"
        :actions="[
          {
            label: 'Télécharger l’installateur',
            color: 'neutral',
            variant: 'outline',
            onClick: () => openExternal(INSTALLER_URL),
          },
        ]"
      />
    </template>

    <template #footer>
      <UButton
        color="neutral"
        variant="ghost"
        label="Plus tard"
        :disabled="installing"
        @click="open = false"
      />
      <UButton
        icon="i-lucide-download"
        :label="failure ? 'Réessayer' : 'Mettre à jour maintenant'"
        :loading="installing"
        @click="install"
      />
    </template>
  </UModal>
</template>
