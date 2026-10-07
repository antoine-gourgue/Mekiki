<script setup lang="ts">
import type { FormError } from '@nuxt/ui'
import type { LotCreate, LotDetail, LotStatus, LotSummary } from '~/types/engine'

/** Creates a lot, or edits `lot` when given. */
const props = defineProps<{ lot?: LotSummary | null }>()
const emit = defineEmits<{ saved: [lot: LotDetail] }>()
const open = defineModel<boolean>('open', { default: false })

const engine = useEngine()
const showError = useErrorToast()

interface LotForm {
  label: string
  status: LotStatus
  ordered_on: string
  shipped_on: string
  received_on: string
  shipping_method: string
  tracking_number: string
  fx_jpy_per_eur: number | null
  packing_fee_jpy: number | null
  international_shipping_jpy: number | null
  insurance_jpy: number | null
  other_fees_jpy: number | null
  payment_fees_cents: number | null
  customs_duty_cents: number | null
  handling_fee_cents: number | null
  vat_known: boolean
  import_vat_cents: number | null
  notes: string
}

function initialState(lot = props.lot): LotForm {
  return {
    label: lot?.label ?? '',
    status: lot?.status ?? 'purchasing',
    ordered_on: lot?.ordered_on ?? (lot ? '' : todayIso()),
    shipped_on: lot?.shipped_on ?? '',
    received_on: lot?.received_on ?? '',
    shipping_method: lot?.shipping_method ?? '',
    tracking_number: lot?.tracking_number ?? '',
    // Left empty on creation, these three take the defaults from the settings.
    fx_jpy_per_eur: lot?.fx_jpy_per_eur ?? null,
    packing_fee_jpy: lot?.packing_fee_jpy ?? null,
    handling_fee_cents: lot?.handling_fee_cents ?? null,
    international_shipping_jpy: lot?.international_shipping_jpy ?? 0,
    insurance_jpy: lot?.insurance_jpy ?? 0,
    other_fees_jpy: lot?.other_fees_jpy ?? 0,
    payment_fees_cents: lot?.payment_fees_cents ?? 0,
    customs_duty_cents: lot?.customs_duty_cents ?? 0,
    vat_known: lot ? lot.import_vat_cents !== null : false,
    import_vat_cents: lot?.import_vat_cents ?? null,
    notes: lot?.notes ?? '',
  }
}

const state = reactive(initialState())
watch(open, (isOpen) => isOpen && Object.assign(state, initialState()))

function validate(form: LotForm): FormError[] {
  return form.label.trim() ? [] : [{ name: 'label', message: 'Donnez un nom au lot.' }]
}

function toBody(form: LotForm): LotCreate {
  const text = (value: string) => value.trim() || null
  const defaulted = (value: number | null, current?: number) =>
    // Editing keeps the lot's value when the field is cleared; creating falls back to settings.
    value ?? current ?? null
  return {
    label: form.label.trim(),
    status: form.status,
    ordered_on: text(form.ordered_on),
    shipped_on: text(form.shipped_on),
    received_on: text(form.received_on),
    shipping_method: text(form.shipping_method),
    tracking_number: text(form.tracking_number),
    fx_jpy_per_eur: defaulted(form.fx_jpy_per_eur, props.lot?.fx_jpy_per_eur),
    packing_fee_jpy: defaulted(form.packing_fee_jpy, props.lot?.packing_fee_jpy),
    handling_fee_cents: defaulted(form.handling_fee_cents, props.lot?.handling_fee_cents),
    international_shipping_jpy: form.international_shipping_jpy ?? 0,
    insurance_jpy: form.insurance_jpy ?? 0,
    other_fees_jpy: form.other_fees_jpy ?? 0,
    payment_fees_cents: form.payment_fees_cents ?? 0,
    customs_duty_cents: form.customs_duty_cents ?? 0,
    import_vat_cents: form.vat_known ? (form.import_vat_cents ?? 0) : null,
    notes: text(form.notes),
  }
}

const saving = ref(false)

async function submit() {
  saving.value = true
  try {
    const body = toBody(state)
    const saved = props.lot
      ? await engine.updateLot(props.lot.id, {
          ...body,
          fx_jpy_per_eur: body.fx_jpy_per_eur!,
          packing_fee_jpy: body.packing_fee_jpy!,
          handling_fee_cents: body.handling_fee_cents!,
        })
      : await engine.createLot(body)
    emit('saved', saved)
    open.value = false
  } catch (error) {
    showError(error)
  } finally {
    saving.value = false
  }
}

const statusItems = selectItems(LOT_STATUS_LABELS)
const fxFormat: Intl.NumberFormatOptions = { maximumFractionDigits: 4 }
</script>

<template>
  <UModal
    v-model:open="open"
    :title="lot ? 'Modifier le lot' : 'Nouveau lot'"
    description="Un lot correspond à un colis international Neokyo."
    :ui="{ content: 'sm:max-w-2xl', footer: 'justify-end' }"
  >
    <template #body>
      <UForm id="lot-form" :state="state" :validate="validate" class="space-y-6" @submit="submit">
        <div class="grid gap-4 sm:grid-cols-2">
          <UFormField label="Nom du lot" name="label" required class="sm:col-span-2">
            <UInput
              v-model="state.label"
              placeholder="Colis Neokyo n° 12"
              autofocus
              class="w-full"
            />
          </UFormField>
          <UFormField label="Statut" name="status">
            <USelect v-model="state.status" :items="statusItems" class="w-full" />
          </UFormField>
          <UFormField label="Taux de change" hint="¥ pour 1 €" name="fx_jpy_per_eur">
            <UInputNumber
              v-model="state.fx_jpy_per_eur"
              :format-options="fxFormat"
              locale="fr-FR"
              :min="0.0001"
              :step="0.0001"
              :step-snapping="false"
              :increment="false"
              :decrement="false"
              placeholder="Taux des paramètres"
              class="w-full"
            />
          </UFormField>
          <UFormField label="Commandé le" name="ordered_on">
            <UInput v-model="state.ordered_on" type="date" class="w-full" />
          </UFormField>
          <UFormField label="Expédié le" name="shipped_on">
            <UInput v-model="state.shipped_on" type="date" class="w-full" />
          </UFormField>
          <UFormField label="Reçu le" name="received_on">
            <UInput v-model="state.received_on" type="date" class="w-full" />
          </UFormField>
          <UFormField label="Mode d’envoi" name="shipping_method">
            <UInput v-model="state.shipping_method" placeholder="EMS, DHL, FedEx…" class="w-full" />
          </UFormField>
          <UFormField label="Numéro de suivi" name="tracking_number" class="sm:col-span-2">
            <UInput v-model="state.tracking_number" class="w-full" />
          </UFormField>
        </div>

        <USeparator label="Frais du colis" />
        <div class="grid gap-4 sm:grid-cols-3">
          <UFormField label="Emballage" name="packing_fee_jpy">
            <MoneyInput
              v-model="state.packing_fee_jpy"
              currency="JPY"
              placeholder="Valeur des paramètres"
            />
          </UFormField>
          <UFormField label="Envoi international" name="international_shipping_jpy">
            <MoneyInput v-model="state.international_shipping_jpy" currency="JPY" />
          </UFormField>
          <UFormField label="Assurance" name="insurance_jpy">
            <MoneyInput v-model="state.insurance_jpy" currency="JPY" />
          </UFormField>
          <UFormField label="Autres frais" name="other_fees_jpy">
            <MoneyInput v-model="state.other_fees_jpy" currency="JPY" />
          </UFormField>
          <UFormField label="Frais de paiement" name="payment_fees_cents">
            <MoneyInput v-model="state.payment_fees_cents" currency="EUR" />
          </UFormField>
          <UFormField label="Frais de dossier" hint="transporteur" name="handling_fee_cents">
            <MoneyInput
              v-model="state.handling_fee_cents"
              currency="EUR"
              placeholder="Valeur des paramètres"
            />
          </UFormField>
          <UFormField label="Droits de douane" name="customs_duty_cents">
            <MoneyInput v-model="state.customs_duty_cents" currency="EUR" />
          </UFormField>
        </div>

        <USeparator label="TVA à l’import" />
        <div class="grid items-end gap-4 sm:grid-cols-2">
          <USwitch
            v-model="state.vat_known"
            label="J’ai la facture du transporteur"
            description="Sinon, la TVA est estimée avec le taux des paramètres."
          />
          <UFormField v-if="state.vat_known" label="TVA payée" name="import_vat_cents">
            <MoneyInput v-model="state.import_vat_cents" currency="EUR" />
          </UFormField>
        </div>

        <UFormField label="Notes" name="notes">
          <UTextarea v-model="state.notes" :rows="2" autoresize class="w-full" />
        </UFormField>
      </UForm>
    </template>

    <template #footer>
      <UButton color="neutral" variant="ghost" label="Annuler" @click="open = false" />
      <UButton
        type="submit"
        form="lot-form"
        :loading="saving"
        :label="lot ? 'Enregistrer' : 'Créer le lot'"
      />
    </template>
  </UModal>
</template>
