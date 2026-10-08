<script setup lang="ts">
import type { LogLine } from '~/types/engine'

/**
 * Timestamped steps of a long task, oldest first. While it runs, new lines stay in view
 * unless the user scrolled up to read earlier ones.
 */
const props = withDefaults(
  defineProps<{
    lines: LogLine[]
    title: string
    active?: boolean
    placeholder?: string
    /** Tailwind max-height of the list. */
    height?: string
  }>(),
  { active: false, placeholder: 'Démarrage…', height: 'max-h-56' },
)

const list = ref<HTMLElement | null>(null)
// How close to the bottom still counts as following the log.
const FOLLOW_PX = 48
let following = true

function onScroll() {
  const el = list.value
  if (el) following = el.scrollHeight - el.scrollTop - el.clientHeight < FOLLOW_PX
}

watch(
  () => props.lines.length,
  async () => {
    await nextTick()
    if (list.value && following) list.value.scrollTop = list.value.scrollHeight
  },
  { immediate: true },
)

const clock = new Intl.DateTimeFormat('fr-FR', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})
</script>

<template>
  <div class="overflow-hidden rounded-lg border border-default bg-[#0b0a0d]">
    <div class="flex items-center gap-2 border-b border-default px-3 py-1.5 text-xs">
      <UIcon
        :name="active ? 'i-lucide-loader-circle' : 'i-lucide-terminal'"
        class="size-4 shrink-0"
        :class="active ? 'animate-spin text-primary' : 'text-dimmed'"
      />
      <span class="flex-1 text-muted">{{ title }}</span>
      <slot name="actions" />
    </div>
    <ol
      ref="list"
      class="space-y-1 overflow-y-auto px-3 py-2.5 font-mono text-xs"
      :class="height"
      aria-live="polite"
      @scroll="onScroll"
    >
      <li v-for="(line, index) in lines" :key="`${line.at}-${index}`" class="flex gap-3">
        <span class="shrink-0 text-dimmed">{{ clock.format(new Date(line.at)) }}</span>
        <span :class="index === lines.length - 1 && active ? 'text-highlighted' : 'text-muted'">
          {{ line.text }}
        </span>
      </li>
      <li v-if="!lines.length" class="text-dimmed">{{ placeholder }}</li>
    </ol>
  </div>
</template>
