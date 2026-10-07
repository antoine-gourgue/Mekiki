<script setup lang="ts">
import type { FormError } from '@nuxt/ui'
import type { Item, SalePlatform } from '~/types/engine'

/** Puts `item` up for sale, changes its listing or withdraws it. */
const props = defineProps<{ item: Item | null }>()
const emit = defineEmits<{ saved: [item: Item] }>()
const open = defineModel<boolean>('open', { default: false })

const engine = useEngine()
const showError = useErrorToast()

const state = reactive<{ platform: SalePlatform; price_cents: number | null }>({
  platform: 'cardmarket',
  price_cents: null,
})

watch(open, (isOpen) => {
  if (!isOpen || !props.item) return
  state.platform = props.item.listing_platform ?? 'cardmarket'
  state.price_cents = props.item.listing_price_cents
})

function validate(form: typeof state): FormError[] {
  return form.price_cents == null ? [{ name: 'price_cents', message: 'Prix obligatoire.' }] : []
}

const saving = ref(false)

async function save(listing: { platform: SalePlatform | null; price_cents: number | null }) {
  if (!props.item) return
  saving.value = true
  try {
    const saved = await engine.updateItem(props.item.id, {
      listing_platform: listing.platform,
      listing_price_cents: listing.price_cents,
    })
    emit('saved', saved)
    open.value = false
  } catch (error) {
    showError(error)
  } finally {
    saving.value = false
  }
}

const platformItems = selectItems(PLATFORM_LABELS)
</script>

<template>
  <UModal
    v-model:open="open"
    title="Mettre en vente"
    :description="item?.name"
    :ui="{ footer: 'justify-between' }"
  >
    <template #body>
      <UForm
        id="listing-form"
        :state="state"
        :validate="validate"
        class="grid gap-4 sm:grid-cols-2"
        @submit="save(state)"
      >
        <UFormField label="Plateforme" name="platform">
          <USelect v-model="state.platform" :items="platformItems" class="w-full" />
        </UFormField>
        <UFormField label="Prix affiché" name="price_cents" required>
          <MoneyInput v-model="state.price_cents" currency="EUR" autofocus />
        </UFormField>
        <p v-if="item" class="text-sm text-muted sm:col-span-2">
          Coût de revient : {{ formatCents(item.landed_cost.total_cents) }}. Le net et la marge
          prévus apparaissent dans le stock une fois l’annonce enregistrée.
        </p>
      </UForm>
    </template>

    <template #footer>
      <UButton
        v-if="item?.listing_platform"
        color="neutral"
        variant="ghost"
        label="Retirer de la vente"
        :disabled="saving"
        @click="save({ platform: null, price_cents: null })"
      />
      <span v-else />
      <UButton type="submit" form="listing-form" :loading="saving" label="Enregistrer" />
    </template>
  </UModal>
</template>
