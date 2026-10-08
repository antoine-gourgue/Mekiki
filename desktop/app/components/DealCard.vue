<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import type { LandedCost, ListingCondition, SaleBreakdown, SourcePlatform } from '~/types/engine'

/**
 * One listing with what it would earn. Used for scanner deals, one-off search results and
 * the proposed parcel: as a row in lists, as a tile in the parcel's grid.
 */
const props = withDefaults(
  defineProps<{
    title: string
    /** The card the title was read as, shown above the Japanese title when known. */
    heading?: string | null
    subtitle?: string
    source: SourcePlatform
    priceJpy: number
    shippingIncluded: boolean | null
    url: string
    neokyoUrl: string | null
    thumbnailUrl: string | null
    listedAt?: string | null
    endsAt?: string | null
    bids?: number | null
    /** Unknown on Rakuma and Yahoo Auctions, whose results do not say. */
    condition?: ListingCondition | null
    landedCost: LandedCost
    sale: SaleBreakdown | null
    /** ROI the scanner aims for, as a fraction (0.3). */
    targetRoi: number
    isNew?: boolean
    offline?: boolean
    muted?: boolean
    note?: string | null
    menu?: DropdownMenuItem[]
    /** Shows the star button. */
    favoritable?: boolean
    /** The listing is already a favorite. */
    favorite?: boolean
    layout?: 'row' | 'tile'
  }>(),
  {
    heading: null,
    subtitle: undefined,
    listedAt: null,
    endsAt: null,
    bids: null,
    condition: null,
    note: null,
    menu: undefined,
    layout: 'row',
  },
)

// `open` asks for the listing's side panel (see ListingDrawer).
const emit = defineEmits<{ toggleFavorite: []; open: [] }>()

const roiTone = computed(() => {
  const roi = props.sale?.roi
  if (roi == null) return 'bg-accented text-muted'
  if (roi >= props.targetRoi) return 'bg-success/15 text-success'
  return roi >= 0 ? 'bg-accented text-highlighted' : 'bg-error/15 text-error'
})

const shippingLabel = computed(() => {
  if (props.shippingIncluded) return 'port compris'
  return props.shippingIncluded === false ? '+ port au Japon' : 'port non précisé'
})

const meta = computed(() =>
  [
    SOURCE_LABELS[props.source],
    props.listedAt ? formatDateTime(props.listedAt) : null,
    props.endsAt ? `fin ${formatDateTime(props.endsAt)}` : null,
    props.bids != null ? `${props.bids} enchère${props.bids > 1 ? 's' : ''}` : null,
  ]
    .filter(Boolean)
    .join(' · '),
)
</script>

<template>
  <!-- Tile: photo on top, figures below (the proposed parcel). -->
  <article
    v-if="layout === 'tile'"
    class="flex flex-col overflow-hidden rounded-lg border border-default bg-muted"
    :class="{ 'opacity-60': muted }"
  >
    <div class="relative h-40 bg-elevated">
      <button
        type="button"
        class="flex size-full items-center justify-center"
        aria-label="Ouvrir la fiche de l’annonce"
        @click="emit('open')"
      >
        <img
          v-if="thumbnailUrl"
          :src="thumbnailUrl"
          :alt="title"
          loading="lazy"
          referrerpolicy="no-referrer"
          class="h-full w-full object-contain p-2"
        />
        <UIcon v-else name="i-lucide-image-off" class="size-6 text-dimmed" />
      </button>
      <span
        v-if="sale?.roi != null"
        class="absolute top-2.5 left-2.5 rounded-full px-2 py-0.5 font-mono text-xs font-semibold"
        :class="roiTone"
      >
        ROI {{ formatRatio(sale.roi) }}
      </span>
      <UBadge
        v-if="condition"
        :color="CONDITION_COLORS[condition]"
        variant="soft"
        :label="CONDITION_LABELS[condition]"
        :title="CONDITION_JAPANESE[condition]"
        class="absolute bottom-2.5 left-2.5"
      />
      <UButton
        v-if="favoritable"
        :color="favorite ? 'primary' : 'neutral'"
        variant="ghost"
        icon="i-lucide-star"
        :aria-label="favorite ? 'Retirer des favoris' : 'Ajouter aux favoris'"
        class="absolute top-1 right-1"
        :class="{ '[&_svg]:fill-current': favorite }"
        @click="emit('toggleFavorite')"
      />
    </div>

    <div class="flex flex-1 flex-col gap-3 p-4">
      <div class="flex items-start gap-2">
        <button type="button" class="min-w-0 flex-1 text-left" @click="emit('open')">
          <p class="truncate font-semibold text-highlighted" :title="heading ?? title">
            {{ heading ?? title }}
          </p>
          <p class="mt-0.5 truncate text-xs text-dimmed" :title="subtitle">
            {{ [subtitle, SOURCE_LABELS[source]].filter(Boolean).join(' · ') }}
          </p>
        </button>
        <UDropdownMenu v-if="menu?.length" :items="menu" :content="{ align: 'end' }">
          <UButton
            icon="i-lucide-ellipsis"
            color="neutral"
            variant="ghost"
            size="sm"
            aria-label="Actions"
          />
        </UDropdownMenu>
      </div>

      <dl class="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-sm">
        <dt class="text-muted">Achat</dt>
        <dd class="text-right tabular-nums">{{ formatYen(priceJpy) }}</dd>
        <dt class="text-muted">
          <UPopover mode="hover" :content="{ side: 'top' }">
            <span class="cursor-help underline decoration-dotted underline-offset-2">
              Coût de revient
            </span>
            <template #content>
              <div class="w-72 space-y-3 p-3">
                <LandedCostBreakdown :cost="landedCost" />
                <SaleBreakdownList v-if="sale" :sale="sale" />
              </div>
            </template>
          </UPopover>
        </dt>
        <dd class="text-right tabular-nums">{{ formatCents(landedCost.total_cents) }}</dd>
        <dt class="text-muted">Revente</dt>
        <dd class="text-right tabular-nums">{{ sale ? formatCents(sale.revenue_cents) : '—' }}</dd>
      </dl>

      <p v-if="note" class="text-xs text-error">{{ note }}</p>

      <div class="mt-auto flex items-center justify-between gap-2 border-t border-default pt-3">
        <span class="font-semibold tabular-nums" :class="signClass(sale?.margin_cents)">
          {{ sale ? formatSignedCents(sale.margin_cents) : 'Pas de cote' }}
        </span>
        <span class="flex gap-1">
          <UButton
            color="neutral"
            variant="ghost"
            size="sm"
            icon="i-lucide-external-link"
            aria-label="Voir l’annonce"
            @click="openExternal(url)"
          />
          <UButton
            v-if="neokyoUrl"
            size="sm"
            variant="soft"
            label="Neokyo"
            trailing-icon="i-lucide-arrow-up-right"
            @click="openExternal(neokyoUrl)"
          />
        </span>
      </div>
      <slot />
    </div>
  </article>

  <!-- Row: thumbnail, titles, three figures, actions (lists of deals and results). -->
  <article
    v-else
    class="rounded-lg border border-default bg-muted px-4 py-3.5"
    :class="{ 'opacity-60': muted }"
  >
    <div class="flex flex-wrap items-center gap-x-6 gap-y-3">
      <slot name="leading" />
      <button
        type="button"
        class="flex h-[72px] w-[52px] shrink-0 items-center justify-center overflow-hidden rounded-md border border-accented bg-elevated"
        aria-label="Ouvrir la fiche de l’annonce"
        @click="emit('open')"
      >
        <img
          v-if="thumbnailUrl"
          :src="thumbnailUrl"
          :alt="title"
          loading="lazy"
          referrerpolicy="no-referrer"
          class="size-full object-cover"
        />
        <UIcon v-else name="i-lucide-image-off" class="size-5 text-dimmed" />
      </button>

      <div class="min-w-0 flex-[1_1_260px]">
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="truncate text-left font-semibold text-highlighted hover:underline"
            :title="heading ?? title"
            @click="emit('open')"
          >
            {{ heading ?? title }}
          </button>
          <span
            v-if="isNew"
            class="rounded-full bg-primary/15 px-2 py-px text-[11px] font-semibold tracking-wide text-primary uppercase"
          >
            Nouveau
          </span>
          <span
            v-if="offline"
            class="rounded-full border border-accented px-2 py-px text-[11px] text-muted"
          >
            Plus en ligne
          </span>
          <UBadge
            v-if="condition"
            :color="CONDITION_COLORS[condition]"
            variant="soft"
            size="sm"
            :label="CONDITION_LABELS[condition]"
            :title="CONDITION_JAPANESE[condition]"
          />
        </div>
        <p v-if="heading" class="mt-0.5 truncate text-[13px] text-dimmed" :title="title">
          {{ title }}
        </p>
        <p class="mt-0.5 truncate text-xs text-dimmed" :title="subtitle">
          {{ [subtitle, meta].filter(Boolean).join(' · ') }}
        </p>
        <p v-if="note" class="mt-1 text-xs text-error">{{ note }}</p>
      </div>

      <div class="flex flex-wrap gap-x-7 gap-y-2">
        <div class="min-w-24">
          <p class="text-xs text-dimmed">Prix</p>
          <p class="mt-0.5 font-semibold text-highlighted tabular-nums">
            {{ formatYen(priceJpy) }}
          </p>
          <UPopover mode="hover" :content="{ side: 'top' }">
            <p
              class="mt-0.5 cursor-help text-xs text-dimmed underline decoration-dotted underline-offset-2"
            >
              revient {{ formatCents(landedCost.total_cents) }}
            </p>
            <template #content>
              <div class="w-72 space-y-3 p-3">
                <LandedCostBreakdown :cost="landedCost" />
                <SaleBreakdownList v-if="sale" :sale="sale" />
              </div>
            </template>
          </UPopover>
        </div>
        <div class="min-w-24">
          <p class="text-xs text-dimmed">Revente</p>
          <p class="mt-0.5 font-semibold text-highlighted tabular-nums">
            {{ sale ? formatCents(sale.revenue_cents) : '—' }}
          </p>
          <p class="mt-0.5 text-xs text-dimmed">{{ shippingLabel }}</p>
        </div>
        <div class="min-w-24">
          <p class="text-xs text-dimmed">Marge</p>
          <p class="mt-0.5 font-semibold tabular-nums" :class="signClass(sale?.margin_cents)">
            {{ sale ? formatSignedCents(sale.margin_cents) : '—' }}
          </p>
          <p v-if="sale?.roi != null" class="mt-0.5">
            <span
              class="rounded-full px-1.5 py-px font-mono text-[11px] font-semibold"
              :class="roiTone"
            >
              ROI {{ formatRatio(sale.roi) }}
            </span>
          </p>
        </div>
      </div>

      <div class="flex items-center gap-1.5">
        <UButton
          v-if="favoritable"
          :color="favorite ? 'primary' : 'neutral'"
          variant="outline"
          icon="i-lucide-star"
          :aria-label="favorite ? 'Retirer des favoris' : 'Ajouter aux favoris'"
          :class="{ '[&_svg]:fill-current': favorite }"
          @click="emit('toggleFavorite')"
        />
        <UButton
          color="neutral"
          variant="outline"
          icon="i-lucide-external-link"
          aria-label="Voir l’annonce"
          @click="openExternal(url)"
        />
        <UButton
          v-if="neokyoUrl"
          variant="soft"
          label="Neokyo"
          trailing-icon="i-lucide-arrow-up-right"
          @click="openExternal(neokyoUrl)"
        />
        <UDropdownMenu v-if="menu?.length" :items="menu" :content="{ align: 'end' }">
          <UButton icon="i-lucide-ellipsis" color="neutral" variant="ghost" aria-label="Actions" />
        </UDropdownMenu>
      </div>
    </div>
    <slot />
  </article>
</template>
