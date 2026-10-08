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

const list = ref<HTMLElement | null>(null)
watch(
  () => lines.value.length,
  async () => {
    await nextTick()
    if (list.value) list.value.scrollTop = list.value.scrollHeight
  },
)

const clock = new Intl.DateTimeFormat('fr-FR', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

async function toggleWindow() {
  state.value = state.value?.visible ? await engine.hideBrowser() : await engine.showBrowser()
}
</script>

<template>
  <div
    v-if="active || lines.length"
    class="overflow-hidden rounded-lg border border-default bg-[#0b0a0d]"
  >
    <div class="flex items-center gap-2 border-b border-default px-3 py-1.5 text-xs">
      <UIcon
        :name="active ? 'i-lucide-loader-circle' : 'i-lucide-terminal'"
        class="size-4 shrink-0"
        :class="active ? 'animate-spin text-primary' : 'text-dimmed'"
      />
      <span class="flex-1 text-muted">
        Chrome · {{ active ? 'en cours, hors de l’écran' : 'terminé' }}
      </span>
      <UButton
        size="xs"
        color="neutral"
        variant="ghost"
        :icon="state?.visible ? 'i-lucide-eye-off' : 'i-lucide-app-window'"
        :label="state?.visible ? 'Masquer la fenêtre' : 'Afficher la fenêtre'"
        @click="toggleWindow"
      />
    </div>
    <ol
      ref="list"
      class="max-h-56 space-y-1 overflow-y-auto px-3 py-2.5 font-mono text-xs"
      aria-live="polite"
    >
      <li v-for="(line, index) in lines" :key="`${line.at}-${index}`" class="flex gap-3">
        <span class="shrink-0 text-dimmed">{{ clock.format(new Date(line.at)) }}</span>
        <span :class="index === lines.length - 1 && active ? 'text-highlighted' : 'text-muted'">
          {{ line.text }}
        </span>
      </li>
      <li v-if="!lines.length" class="text-dimmed">Démarrage de Chrome…</li>
    </ol>
  </div>
</template>
