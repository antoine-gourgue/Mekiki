<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import type { LandedCost, SaleBreakdown, SourcePlatform } from '~/types/engine'

/** One listing with what it would earn. Used for scanner deals and one-off search results. */
const props = defineProps<{
  title: string
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
}>()

const emit = defineEmits<{ toggleFavorite: [] }>()

const roiColor = computed(() => {
  const roi = props.sale?.roi
  if (roi == null) return 'neutral' as const
  if (roi >= props.targetRoi) return 'success' as const
  return roi >= 0 ? ('warning' as const) : ('error' as const)
})

const shippingLabel = computed(() => {
  if (props.shippingIncluded) return 'port compris'
  return props.shippingIncluded === false ? '+ port au Japon' : 'port non précisé'
})
</script>

<template>
  <UCard :class="{ 'opacity-60': muted }" :ui="{ body: 'p-3 sm:p-3' }">
    <div class="flex gap-3">
      <div class="size-24 shrink-0 overflow-hidden rounded-md bg-elevated">
        <img
          v-if="thumbnailUrl"
          :src="thumbnailUrl"
          :alt="title"
          loading="lazy"
          referrerpolicy="no-referrer"
          class="size-full object-cover"
        />
        <UIcon v-else name="i-lucide-image-off" class="m-auto mt-9 size-6 text-muted" />
      </div>

      <div class="min-w-0 flex-1">
        <div class="flex items-start justify-between gap-2">
          <p class="line-clamp-2 text-sm font-medium text-highlighted" :title="title">
            {{ title }}
          </p>
          <UDropdownMenu v-if="menu?.length" :items="menu" :content="{ align: 'end' }">
            <UButton
              icon="i-lucide-ellipsis-vertical"
              color="neutral"
              variant="ghost"
              size="xs"
              aria-label="Actions"
            />
          </UDropdownMenu>
        </div>
        <p class="mt-0.5 text-xs text-muted">
          <UBadge
            v-if="isNew"
            color="primary"
            variant="solid"
            size="sm"
            label="Nouveau"
            class="mr-1"
          />
          <UBadge
            v-if="offline"
            color="neutral"
            variant="outline"
            size="sm"
            label="Plus en ligne"
            class="mr-1"
          />
          {{ SOURCE_LABELS[source] }}
          <template v-if="subtitle"> · {{ subtitle }}</template>
          <template v-if="listedAt"> · {{ formatDateTime(listedAt) }}</template>
          <template v-if="endsAt"> · fin {{ formatDateTime(endsAt) }}</template>
          <template v-if="bids != null"> · {{ bids }} enchère{{ bids > 1 ? 's' : '' }}</template>
        </p>

        <div class="mt-2 flex flex-wrap items-end justify-between gap-x-4 gap-y-1">
          <div>
            <p class="text-lg font-semibold tabular-nums">{{ formatYen(priceJpy) }}</p>
            <p class="text-xs text-muted">{{ shippingLabel }}</p>
          </div>
          <div class="text-right text-sm">
            <UPopover mode="hover" :content="{ side: 'left' }">
              <p class="cursor-help underline decoration-dotted">
                Revient {{ formatCents(landedCost.total_cents) }}
              </p>
              <template #content>
                <div class="w-72 space-y-3 p-3">
                  <LandedCostBreakdown :cost="landedCost" />
                  <SaleBreakdownList v-if="sale" :sale="sale" />
                </div>
              </template>
            </UPopover>
            <p v-if="sale" class="text-muted">
              Revente {{ formatCents(sale.revenue_cents) }} · marge
              <span class="font-medium" :class="signClass(sale.margin_cents)">
                {{ formatCents(sale.margin_cents) }}
              </span>
            </p>
            <p v-else class="text-muted">Pas de prix de revente</p>
          </div>
        </div>

        <p v-if="note" class="mt-1 text-xs text-warning">{{ note }}</p>

        <div class="mt-3 flex flex-wrap items-center gap-2">
          <UBadge
            v-if="sale?.roi != null"
            :color="roiColor"
            variant="subtle"
            :label="`ROI ${formatRatio(sale.roi)}`"
          />
          <span class="flex-1" />
          <UButton
            v-if="favoritable"
            size="xs"
            :color="favorite ? 'warning' : 'neutral'"
            :variant="favorite ? 'soft' : 'ghost'"
            icon="i-lucide-star"
            :aria-label="favorite ? 'Retirer des favoris' : 'Ajouter aux favoris'"
            :class="{ '[&_svg]:fill-current': favorite }"
            @click="emit('toggleFavorite')"
          />
          <UButton
            size="xs"
            color="neutral"
            variant="outline"
            icon="i-lucide-external-link"
            label="Annonce"
            @click="openExternal(url)"
          />
          <UButton
            v-if="neokyoUrl"
            size="xs"
            icon="i-lucide-shopping-cart"
            label="Neokyo"
            @click="openExternal(neokyoUrl)"
          />
        </div>
        <slot />
      </div>
    </div>
  </UCard>
</template>
