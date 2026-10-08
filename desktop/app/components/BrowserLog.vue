<script setup lang="ts">
import type { BrowserActivity } from '~/types/engine'

/**
 * What Mekiki's Chrome window does while it works off screen, as a log of its steps; the
 * window itself can be brought up. Read every second while `active`, kept afterwards with
 * the outcome.
 */
const props = defineProps<{ active: boolean }>()

const engine = useEngine()

const POLL_MS = 1000
// The first step can be logged before the first read: lines from just before count too.
const LEAD_MS = 3000

const state = ref<BrowserActivity | null>(null)
const since = ref<string | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined

async function poll() {
  try {
    state.value = await engine.browserActivity()
  } catch {
    // A missed read is replaced by the next one.
  }
  if (props.active) timer = setTimeout(poll, POLL_MS)
}

watch(
  () => props.active,
  (active) => {
    clearTimeout(timer)
    if (active) {
      // Same format as the engine's timestamps, so they compare as strings.
      since.value = `${new Date(Date.now() - LEAD_MS).toISOString().slice(0, 19)}Z`
      void poll()
    } else if (since.value) {
      // One last read for the outcome line.
      void poll()
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => clearTimeout(timer))

const lines = computed(() =>
  since.value ? (state.value?.log ?? []).filter((line) => line.at >= since.value!) : [],
)

async function toggleWindow() {
  state.value = state.value?.visible ? await engine.hideBrowser() : await engine.showBrowser()
}
</script>

<template>
  <ActivityLog
    v-if="active || lines.length"
    :lines="lines"
    :active="active"
    :title="`Chrome · ${active ? 'en cours, hors de l’écran' : 'terminé'}`"
    placeholder="Démarrage de Chrome…"
  >
    <template #actions>
      <UButton
        size="xs"
        color="neutral"
        variant="ghost"
        :icon="state?.visible ? 'i-lucide-eye-off' : 'i-lucide-app-window'"
        :label="state?.visible ? 'Masquer la fenêtre' : 'Afficher la fenêtre'"
        @click="toggleWindow"
      />
    </template>
  </ActivityLog>
</template>
