<script setup lang="ts">
import type { Item, PendingSale } from '~/types/engine'

/**
 * Lines of eBay's orders report no card was found for: the user names the card sold (the
 * likeliest first), or leaves the line aside when it sold something else.
 */
const emit = defineEmits<{ matched: [] }>()

const engine = useEngine()
const showError = useErrorToast()

const pending = ref<PendingSale[]>([])
const unsold = ref<Item[]>([])
const chosen = reactive<Record<number, number | undefined>>({})
const busy = ref<number | null>(null)

async function load() {
  try {
    const [rows, items] = await Promise.all([engine.pendingSales(), engine.inventory()])
    pending.value = rows
    unsold.value = items.filter((item) => !item.sale)
    const offered = new Set(unsold.value.map((item) => item.id))
    for (const row of rows) {
      const current = chosen[row.id]
      // A card just matched to another line is sold: it left this line's choices.
      if (current == null || !offered.has(current)) {
        chosen[row.id] = row.suggestions.find((s) => offered.has(s.item_id))?.item_id
      }
    }
  } catch (error) {
    showError(error)
  }
}
onMounted(load)
defineExpose({ load })

function options(row: PendingSale) {
  const suggested = new Set(row.suggestions.map((s) => s.item_id))
  return [
    ...row.suggestions.map((s) => ({ value: s.item_id, label: `★ ${s.label}` })),
    ...unsold.value
      .filter((item) => !suggested.has(item.id))
      .map((item) => ({
        value: item.id,
        label: [item.name, item.card_number, item.lot_label].filter(Boolean).join(' · '),
      })),
  ]
}

async function match(row: PendingSale) {
  const itemId = chosen[row.id]
  if (itemId == null) return
  busy.value = row.id
  try {
    await engine.matchPendingSale(row.id, itemId)
    await load()
    emit('matched')
  } catch (error) {
    showError(error)
  } finally {
    busy.value = null
  }
}

async function ignore(row: PendingSale) {
  busy.value = row.id
  try {
    await engine.ignorePendingSale(row.id)
    await load()
  } catch (error) {
    showError(error)
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <UCard v-if="pending.length" :ui="{ body: 'space-y-3 sm:p-5' }">
    <div>
      <h2 class="font-semibold text-highlighted">Ventes eBay à rapprocher</h2>
      <p class="mt-1 text-sm text-dimmed">
        Lignes du rapport eBay dont la carte n’a pas été retrouvée : choisissez la carte vendue (★
        les plus probables), ou écartez une vente qui ne vient pas de votre stock Mekiki. Une ligne
        de plusieurs cartes s’associe carte par carte, chacune avec sa part du prix et du port.
      </p>
    </div>
    <ul class="divide-y divide-default rounded-lg border border-default">
      <li v-for="row in pending" :key="row.id" class="space-y-2.5 p-3 text-sm">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <p class="font-medium text-highlighted">{{ row.title }}</p>
          <p class="text-muted tabular-nums">
            {{ formatCents(row.price_cents) }}
            <template v-if="row.shipping_cents">
              + {{ formatCents(row.shipping_cents) }} de port</template
            >
          </p>
        </div>
        <p class="text-xs text-dimmed">
          Vendue le {{ formatDate(row.sold_on) }}
          <template v-if="row.buyer"> · {{ row.buyer }}</template>
          <template v-if="row.quantity > 1">
            · {{ row.quantity }} cartes à associer, {{ row.matched }}
            {{ row.matched > 1 ? 'faites' : 'faite' }}</template
          >
          <template v-if="row.shipped_on"> · expédiée le {{ formatDate(row.shipped_on) }}</template>
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <USelectMenu
            v-model="chosen[row.id]"
            :items="options(row)"
            value-key="value"
            placeholder="Carte vendue…"
            class="min-w-64 flex-1"
          />
          <UButton
            label="Associer"
            icon="i-lucide-link"
            :disabled="chosen[row.id] == null"
            :loading="busy === row.id"
            @click="match(row)"
          />
          <UButton
            label="Écarter"
            color="neutral"
            variant="ghost"
            :disabled="busy === row.id"
            @click="ignore(row)"
          />
        </div>
      </li>
    </ul>
  </UCard>
</template>
