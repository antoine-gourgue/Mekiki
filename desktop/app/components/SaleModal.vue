<script setup lang="ts">
import type { FormError } from '@nuxt/ui'
import type { Item, SalePlatform } from '~/types/engine'

/** Records the sale of `item`, or edits it when the card is already sold. */
const props = defineProps<{ item: Item | null }>()
const emit = defineEmits<{ saved: [item: Item] }>()
const open = defineModel<boolean>('open', { default: false })

const engine = useEngine()
const showError = useErrorToast()

interface SaleForm {
  platform: SalePlatform
  sold_on: string
  sale_price_cents: number | null
  shipping_charged_cents: number | null
  shipping_cost_cents: number | null
  platform_fee_cents: number | null
  packaging_cents: number | null
  notes: string
}

const state = reactive<SaleForm>({
  platform: 'cardmarket',
  sold_on: todayIso(),
  sale_price_cents: null,
  shipping_charged_cents: 0,
  shipping_cost_cents: 0,
  platform_fee_cents: null,
  packaging_cents: null,
  notes: '',
})

watch(open, (isOpen) => {
  const item = props.item
  if (!isOpen || !item) return
  const sale = item.sale
  Object.assign(state, {
    platform: sale?.platform ?? item.listing_platform ?? 'cardmarket',
    sold_on: sale?.sold_on ?? todayIso(),
    sale_price_cents: sale?.sale_price_cents ?? item.listing_price_cents,
    shipping_charged_cents: sale?.shipping_charged_cents ?? 0,
    shipping_cost_cents: sale?.shipping_cost_cents ?? 0,
    // A recorded sale shows its frozen fees; clearing them recomputes from the settings.
    platform_fee_cents: sale?.platform_fee_cents ?? null,
    packaging_cents: sale?.packaging_cents ?? null,
    notes: sale?.notes ?? '',
  })
})

function validate(form: SaleForm): FormError[] {
  const errors: FormError[] = []
  if (form.sale_price_cents == null)
    errors.push({ name: 'sale_price_cents', message: 'Prix obligatoire.' })
  if (!form.sold_on) errors.push({ name: 'sold_on', message: 'Date obligatoire.' })
  return errors
}

const saving = ref(false)

async function submit() {
  if (!props.item) return
  saving.value = true
  try {
    const saved = await engine.recordSale(props.item.id, {
      platform: state.platform,
      sold_on: state.sold_on,
      sale_price_cents: state.sale_price_cents ?? 0,
      shipping_charged_cents: state.shipping_charged_cents ?? 0,
      shipping_cost_cents: state.shipping_cost_cents ?? 0,
      platform_fee_cents: state.platform_fee_cents,
      packaging_cents: state.packaging_cents,
      notes: state.notes.trim() || null,
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
    :title="item?.sale ? 'Modifier la vente' : 'Carte vendue'"
    :description="item?.name"
    :ui="{ content: 'sm:max-w-xl', footer: 'justify-end' }"
  >
    <template #body>
      <UForm
        id="sale-form"
        :state="state"
        :validate="validate"
        class="grid gap-4 sm:grid-cols-2"
        @submit="submit"
      >
        <UFormField label="Plateforme" name="platform">
          <USelect v-model="state.platform" :items="platformItems" class="w-full" />
        </UFormField>
        <UFormField label="Vendue le" name="sold_on" required>
          <UInput v-model="state.sold_on" type="date" class="w-full" />
        </UFormField>
        <UFormField label="Prix de vente" name="sale_price_cents" required>
          <MoneyInput v-model="state.sale_price_cents" currency="EUR" autofocus />
        </UFormField>
        <UFormField label="Port payé par l’acheteur" name="shipping_charged_cents">
          <MoneyInput v-model="state.shipping_charged_cents" currency="EUR" />
        </UFormField>
        <UFormField label="Coût réel de l’envoi" name="shipping_cost_cents">
          <MoneyInput v-model="state.shipping_cost_cents" currency="EUR" />
        </UFormField>
        <UFormField label="Frais de plateforme" name="platform_fee_cents" help="Vide : calculés">
          <MoneyInput v-model="state.platform_fee_cents" currency="EUR" placeholder="Calculés" />
        </UFormField>
        <UFormField label="Emballage" name="packaging_cents" help="Vide : valeur des paramètres">
          <MoneyInput v-model="state.packaging_cents" currency="EUR" placeholder="Par défaut" />
        </UFormField>
        <UFormField label="Notes" name="notes" class="sm:col-span-2">
          <UTextarea v-model="state.notes" :rows="2" autoresize class="w-full" />
        </UFormField>
      </UForm>
    </template>

    <template #footer>
      <UButton color="neutral" variant="ghost" label="Annuler" @click="open = false" />
      <UButton type="submit" form="sale-form" :loading="saving" label="Enregistrer la vente" />
    </template>
  </UModal>
</template>
