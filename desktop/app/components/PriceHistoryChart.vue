<script setup lang="ts">
import type { PricePoint } from '~/types/engine'

/**
 * Line of a card's resale price, one point a day, with the value under the pointer. Single
 * series: the section title names it, no legend.
 */
const props = defineProps<{ points: PricePoint[] }>()

const HEIGHT = 168
const PADDING = { top: 12, right: 12, bottom: 24, left: 56 }

const container = ref<HTMLElement | null>(null)
const width = ref(480)
let observer: ResizeObserver | undefined
onMounted(() => {
  observer = new ResizeObserver(([entry]) => {
    if (entry) width.value = Math.max(280, entry.contentRect.width)
  })
  if (container.value) observer.observe(container.value)
})
onBeforeUnmount(() => observer?.disconnect())

const geometry = computed(() => {
  const values = props.points.map((point) => point.cents)
  const low = Math.min(...values)
  const high = Math.max(...values)
  // A flat price still gets some room above and below its line.
  const margin = Math.max((high - low) * 0.15, high * 0.05, 50)
  const min = Math.max(0, low - margin)
  const max = high + margin
  const plotWidth = width.value - PADDING.left - PADDING.right
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom
  const x = (index: number) =>
    PADDING.left + (props.points.length > 1 ? (index / (props.points.length - 1)) * plotWidth : 0)
  const y = (cents: number) => PADDING.top + (1 - (cents - min) / (max - min)) * plotHeight
  const coords = props.points.map((point, index) => ({ x: x(index), y: y(point.cents), point }))
  const line = coords.map((c, i) => `${i ? 'L' : 'M'}${c.x.toFixed(1)},${c.y.toFixed(1)}`)
  const baseline = HEIGHT - PADDING.bottom
  const first = coords[0]
  const last = coords.at(-1)
  return {
    coords,
    line: line.join(' '),
    area:
      first && last
        ? `${line.join(' ')} L${last.x.toFixed(1)},${baseline} L${first.x.toFixed(1)},${baseline} Z`
        : '',
    ticks: [max, (max + min) / 2, min].map((value) => ({ value, y: y(value) })),
    baseline,
  }
})

const hovered = ref<number | null>(null)
function hover(event: PointerEvent) {
  const box = (event.currentTarget as SVGElement).getBoundingClientRect()
  const offset = event.clientX - box.left
  let best = 0
  geometry.value.coords.forEach((coord, index) => {
    if (Math.abs(coord.x - offset) < Math.abs(geometry.value.coords[best]!.x - offset)) best = index
  })
  hovered.value = best
}

const shown = computed(() =>
  hovered.value == null ? null : (geometry.value.coords[hovered.value] ?? null),
)
</script>

<template>
  <div ref="container" class="relative">
    <svg
      :width="width"
      :height="HEIGHT"
      class="block touch-none"
      role="img"
      :aria-label="`Cote de ${formatCents(points[0]?.cents)} à ${formatCents(points.at(-1)?.cents)}`"
      @pointermove="hover"
      @pointerleave="hovered = null"
    >
      <g v-for="tick in geometry.ticks" :key="tick.value">
        <line
          :x1="PADDING.left"
          :x2="width - PADDING.right"
          :y1="tick.y"
          :y2="tick.y"
          class="stroke-[var(--ui-border)]"
          stroke-dasharray="2 4"
        />
        <text
          :x="PADDING.left - 8"
          :y="tick.y + 4"
          text-anchor="end"
          class="fill-[var(--ui-text-dimmed)] font-mono text-[11px]"
        >
          {{ formatCents(Math.round(tick.value)) }}
        </text>
      </g>
      <path :d="geometry.area" class="fill-[var(--ui-primary)] opacity-10" />
      <path
        :d="geometry.line"
        fill="none"
        class="stroke-[var(--ui-primary)]"
        stroke-width="2"
        stroke-linejoin="round"
        stroke-linecap="round"
      />
      <text :x="PADDING.left" :y="HEIGHT - 6" class="fill-[var(--ui-text-dimmed)] text-[11px]">
        {{ formatDate(points[0]?.date) }}
      </text>
      <text
        :x="width - PADDING.right"
        :y="HEIGHT - 6"
        text-anchor="end"
        class="fill-[var(--ui-text-dimmed)] text-[11px]"
      >
        {{ formatDate(points.at(-1)?.date) }}
      </text>
      <template v-if="shown">
        <line
          :x1="shown.x"
          :x2="shown.x"
          :y1="PADDING.top"
          :y2="geometry.baseline"
          class="stroke-[var(--ui-border-accented)]"
        />
        <circle
          :cx="shown.x"
          :cy="shown.y"
          r="4"
          class="fill-[var(--ui-primary)] stroke-[var(--ui-bg)]"
          stroke-width="2"
        />
      </template>
    </svg>
    <div
      v-if="shown"
      class="pointer-events-none absolute top-1 rounded-md border border-default bg-default px-2.5 py-1.5 text-xs shadow-lg"
      :style="{ left: `${Math.min(shown.x + 10, width - 132)}px` }"
    >
      <p class="text-dimmed">{{ formatDate(shown.point.date) }}</p>
      <p class="font-semibold text-highlighted tabular-nums">
        {{ formatCents(shown.point.cents) }}
      </p>
    </div>
  </div>
</template>
