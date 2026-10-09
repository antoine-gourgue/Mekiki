<script setup lang="ts">
import type { BlockedSeller } from '~/types/engine'

/** The sellers Neokyo refuses, blocked by hand or spotted by Mekiki, and their unblocking. */
const engine = useEngine()
const showError = useErrorToast()

const sellers = ref<BlockedSeller[] | null>(null)
async function load() {
  try {
    sellers.value = await engine.blockedSellers()
  } catch (error) {
    showError(error)
  }
}
onMounted(load)

async function unblock(seller: BlockedSeller) {
  try {
    await engine.unblockSeller(seller.source, seller.seller_id)
    await load()
  } catch (error) {
    showError(error)
  }
}

function profileUrl(seller: BlockedSeller) {
  return seller.source === 'mercari'
    ? `https://jp.mercari.com/user/profile/${encodeURIComponent(seller.seller_id)}`
    : null
}
</script>

<template>
  <UCard id="vendeurs" :ui="{ body: 'space-y-4 sm:p-5' }">
    <div>
      <h2 class="font-semibold text-highlighted">Vendeurs bloqués</h2>
      <p class="mt-1 text-sm text-dimmed">
        Neokyo refuse d’acheter chez eux : leurs annonces ne sont plus proposées. Mekiki y ajoute
        seul les vendeurs qui refusent les intermédiaires ou sont mal notés.
      </p>
    </div>
    <p v-if="sellers && !sellers.length" class="text-sm text-muted">
      Aucun vendeur bloqué pour l’instant.
    </p>
    <ul v-else-if="sellers" class="divide-y divide-default rounded-lg border border-default">
      <li
        v-for="seller in sellers"
        :key="`${seller.source}:${seller.seller_id}`"
        class="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm"
      >
        <span class="min-w-0 flex-1">
          <span class="text-highlighted">
            {{ SOURCE_LABELS[seller.source] }} · vendeur {{ seller.seller_id }}
          </span>
          <span class="block text-xs text-dimmed">
            {{ seller.reason }} · {{ formatDate(seller.blocked_at) }}
          </span>
        </span>
        <UButton
          v-if="profileUrl(seller)"
          size="sm"
          color="neutral"
          variant="ghost"
          icon="i-lucide-arrow-up-right"
          aria-label="Voir le vendeur sur Mercari"
          @click="openExternal(profileUrl(seller)!)"
        />
        <UButton
          size="sm"
          color="neutral"
          variant="outline"
          label="Débloquer"
          @click="unblock(seller)"
        />
      </li>
    </ul>
  </UCard>
</template>
