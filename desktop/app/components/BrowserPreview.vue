<script setup lang="ts">
import type { BrowserActivity } from '~/types/engine'

/**
 * Live view of Mekiki's Chrome window while it works off screen: what it shows and the
 * step it is at, refreshed every second or so; the window itself can be brought up.
 */
const props = defineProps<{ active: boolean }>()

const engine = useEngine()

const POLL_MS = 1200
const activity = ref<BrowserActivity | null>(null)
const image = ref<string | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined

async function poll() {
  try {
    const [state, blob] = await Promise.all([engine.browserActivity(), engine.browserPreview()])
    activity.value = state
    if (blob && blob.size) {
      const previous = image.value
      image.value = URL.createObjectURL(blob)
      if (previous) URL.revokeObjectURL(previous)
    }
  } catch {
    // A missed frame is replaced by the next one.
  }
  if (props.active) timer = setTimeout(poll, POLL_MS)
}

watch(
  () => props.active,
  (active) => {
    clearTimeout(timer)
    if (active) void poll()
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  clearTimeout(timer)
  if (image.value) URL.revokeObjectURL(image.value)
})

async function toggleWindow() {
  activity.value = activity.value?.visible ? await engine.hideBrowser() : await engine.showBrowser()
}
</script>

<template>
  <div v-if="active" class="space-y-2 rounded-md border border-default p-2">
    <div class="flex items-center gap-2 text-xs">
      <UIcon name="i-lucide-loader-circle" class="size-4 shrink-0 animate-spin text-primary" />
      <span class="min-w-0 flex-1 truncate text-muted">
        {{ activity?.activity ?? 'Chrome travaille…' }}
      </span>
      <UButton
        size="xs"
        color="neutral"
        variant="ghost"
        :icon="activity?.visible ? 'i-lucide-eye-off' : 'i-lucide-app-window'"
        :label="activity?.visible ? 'Masquer la fenêtre' : 'Afficher la fenêtre'"
        @click="toggleWindow"
      />
    </div>
    <div class="aspect-[1280/900] overflow-hidden rounded bg-elevated">
      <img
        v-if="image"
        :src="image"
        alt="Aperçu de la fenêtre Chrome de Mekiki"
        class="size-full object-cover object-top"
      />
    </div>
  </div>
</template>
