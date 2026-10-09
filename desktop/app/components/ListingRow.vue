<script setup lang="ts">
/** A listing on eBay, for sale or sold: one click opens it in the browser. */
defineProps<{
  url: string
  title: string
  imageUrl: string | null
  /** "Vendu le 6 oct. 2026", "Comme neuf · FR". */
  detail?: string | null
  priceCents: number
  shippingCents?: number | null
  /** A lower offer was accepted: the price shown is above what was paid. */
  bestOffer?: boolean
  site: string
}>()
</script>

<template>
  <button
    type="button"
    class="group flex w-full items-center gap-3 rounded-lg border border-transparent bg-elevated p-2 text-left text-sm transition-colors hover:border-accented hover:bg-accented"
    :title="`Ouvrir l’annonce sur ${site}`"
    @click="openExternal(url)"
  >
    <span
      class="flex h-13 w-10 shrink-0 items-center justify-center overflow-hidden rounded-md bg-accented"
    >
      <img
        v-if="imageUrl"
        :src="imageUrl"
        alt=""
        loading="lazy"
        referrerpolicy="no-referrer"
        class="size-full object-cover"
      />
      <UIcon v-else name="i-lucide-image-off" class="size-4 text-dimmed" />
    </span>
    <span class="min-w-0 flex-1">
      <span class="line-clamp-1 text-highlighted group-hover:underline" :title="title">
        {{ title }}
      </span>
      <span class="block text-xs text-dimmed">
        {{ detail }}
        <template v-if="shippingCents"> · + {{ formatCents(shippingCents) }} de port</template>
      </span>
    </span>
    <span class="shrink-0 font-semibold tabular-nums">
      {{ formatCents(priceCents) }}{{ bestOffer ? '*' : '' }}
    </span>
    <span
      class="flex size-7 shrink-0 items-center justify-center rounded-md text-dimmed transition-colors group-hover:bg-default group-hover:text-highlighted"
    >
      <UIcon name="i-lucide-arrow-up-right" class="size-4" />
    </span>
  </button>
</template>
