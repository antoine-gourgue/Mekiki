<script setup lang="ts">
import type { MonthlySales } from '~/types/engine'

/**
 * Column chart of the margin per month, with a per-column tooltip. Single series: no legend;
 * a losing month is drawn in the loss color.
 */
const props = defineProps<{ months: MonthlySales[] }>()

const HEIGHT = 240
const PADDING = { top: 12, right: 8, bottom: 28, left: 64 }
const MAX_BAR = 24
const RADIUS = 4
const TOOLTIP_WIDTH = 176

const container = ref<HTMLElement | null>(null)
const width = ref(640)
let observer: ResizeObserver | undefined

onMounted(() => {
  observer = new ResizeObserver(([entry]) => {
    if (entry) width.value = Math.max(320, entry.contentRect.width)
  })
  if (container.value) observer.observe(container.value)
})
onBeforeUnmount(() => observer?.disconnect())

/** Round tick step (1, 2 or 5 × 10^n euros) giving about four intervals. */
function niceStep(range: number): number {
  const raw = range / 4
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  const normalized = raw / magnitude
  return (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude
}

const scale = computed(() => {
  const values = props.months.map((m) => m.margin_cents / 100)
  const rawMax = Math.max(0, ...values)
  const rawMin = Math.min(0, ...values)
  const step = niceStep(rawMax - rawMin || 100)
  const max = Math.ceil(rawMax / step) * step || step
  const min = Math.floor(rawMin / step) * step
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom
  const y = (euros: number) => PADDING.top + ((max - euros) / (max - min)) * plotHeight
  const ticks: number[] = []
  for (let tick = min; tick <= max + step / 2; tick += step) ticks.push(tick)
  return { y, ticks }
})

const tickFormat = new Intl.NumberFormat('fr-FR', {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 0,
})

const bars = computed(() => {
  const plotWidth = width.value - PADDING.left - PADDING.right
  const slot = plotWidth / Math.max(1, props.months.length)
  const barWidth = Math.min(MAX_BAR, slot * 0.6)
  const baseline = scale.value.y(0)
  // Keep month labels from colliding when many months are shown.
  const labelEvery = Math.ceil(36 / slot)
  return props.months.map((month, index) => {
    const x = PADDING.left + slot * index + (slot - barWidth) / 2
    const top = scale.value.y(month.margin_cents / 100)
    return {
      month,
      slotX: PADDING.left + slot * index,
      slotWidth: slot,
      center: x + barWidth / 2,
      path: columnPath(x, barWidth, baseline, top),
      showLabel: index % labelEvery === 0,
    }
  })
})

/** Column from the baseline to `end`, rounded at the data end and square at the baseline. */
function columnPath(x: number, w: number, baseline: number, end: number): string {
  const h = Math.abs(baseline - end)
  if (h < 0.5) return ''
  const r = Math.min(RADIUS, h, w / 2)
  const dir = end < baseline ? 1 : -1
  return [
    `M${x},${baseline}`,
    `V${end + dir * r}`,
    `Q${x},${end} ${x + r},${end}`,
    `H${x + w - r}`,
    `Q${x + w},${end} ${x + w},${end + dir * r}`,
    `V${baseline}`,
    'Z',
  ].join(' ')
}

const active = ref<number | null>(null)
const tooltip = computed(() => {
  if (active.value == null) return null
  const bar = bars.value[active.value]
  if (!bar) return null
  // Beside the column rather than over it, on the side with room.
  const gap = MAX_BAR / 2 + 8
  const left = bar.center > width.value / 2 ? bar.center - gap - TOOLTIP_WIDTH : bar.center + gap
  return { bar, left }
})
</script>

<template>
  <div ref="container" class="relative w-full">
    <svg
      :width="width"
      :height="HEIGHT"
      role="img"
      aria-label="Marge par mois"
      class="block overflow-visible"
    >
      <g>
        <template v-for="tick in scale.ticks" :key="tick">
          <line
            :x1="PADDING.left"
            :x2="width - PADDING.right"
            :y1="scale.y(tick)"
            :y2="scale.y(tick)"
            :stroke="tick === 0 ? 'var(--ui-border-accented)' : 'var(--ui-border)'"
            stroke-width="1"
            shape-rendering="crispEdges"
          />
          <text
            :x="PADDING.left - 8"
            :y="scale.y(tick)"
            text-anchor="end"
            dominant-baseline="middle"
            fill="var(--ui-text-muted)"
            class="text-xs tabular-nums"
          >
            {{ tickFormat.format(tick) }}
          </text>
        </template>
      </g>

      <g
        v-for="(bar, index) in bars"
        :key="bar.month.month"
        tabindex="0"
        :aria-label="`${formatMonth(bar.month.month)} : marge ${formatCents(bar.month.margin_cents)}`"
        class="cursor-default outline-none"
        @pointerenter="active = index"
        @pointerleave="active = null"
        @focus="active = index"
        @blur="active = null"
      >
        <!-- The whole month slot is the hit target, not just the painted column. -->
        <rect
          :x="bar.slotX"
          :y="PADDING.top"
          :width="bar.slotWidth"
          :height="HEIGHT - PADDING.top - PADDING.bottom"
          fill="transparent"
        />
        <path
          :d="bar.path"
          :fill="bar.month.margin_cents < 0 ? 'var(--ui-error)' : 'var(--color-vermilion-500)'"
          :opacity="active === null || active === index ? 1 : 0.55"
        />
        <text
          v-if="bar.showLabel"
          :x="bar.center"
          :y="HEIGHT - 8"
          text-anchor="middle"
          fill="var(--ui-text-muted)"
          class="text-xs"
        >
          {{ formatMonth(bar.month.month) }}
        </text>
      </g>
    </svg>

    <div
      v-if="tooltip"
      class="pointer-events-none absolute top-0 z-10 rounded-md border border-default bg-elevated p-2.5 text-xs shadow-lg"
      :style="{ left: `${tooltip.left}px`, width: `${TOOLTIP_WIDTH}px` }"
    >
      <p
        class="text-sm font-semibold tabular-nums"
        :class="signClass(tooltip.bar.month.margin_cents)"
      >
        {{ formatCents(tooltip.bar.month.margin_cents) }}
      </p>
      <p class="text-muted">Marge · {{ formatMonth(tooltip.bar.month.month) }}</p>
      <dl class="mt-1 space-y-0.5">
        <div class="flex justify-between">
          <dt class="text-muted">CA</dt>
          <dd class="tabular-nums">{{ formatCents(tooltip.bar.month.revenue_cents) }}</dd>
        </div>
        <div class="flex justify-between">
          <dt class="text-muted">Net</dt>
          <dd class="tabular-nums">{{ formatCents(tooltip.bar.month.net_cents) }}</dd>
        </div>
        <div class="flex justify-between">
          <dt class="text-muted">Ventes</dt>
          <dd class="tabular-nums">{{ tooltip.bar.month.sold_count }}</dd>
        </div>
      </dl>
    </div>
  </div>
</template>
