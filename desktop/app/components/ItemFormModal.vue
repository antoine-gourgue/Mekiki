<script setup lang="ts">
import type { FormError } from '@nuxt/ui'
import type { Game, Item, ItemCreate, LotSummary, SourcePlatform } from '~/types/engine'

/** Adds a card to `lotId`, or edits `item` when given (including moving it to another lot). */
const props = defineProps<{
  lotId?: number
  item?: Item | null
  lots?: LotSummary[]
}>()
const emit = defineEmits<{ saved: [item: Item] }>()
const open = defineModel<boolean>('open', { default: false })

const engine = useEngine()
const showError = useErrorToast()
const toast = useToast()

interface ItemForm {
  lot_id: number | undefined
  game: Game
  name: string
  set_code: string
  card_number: string
  rarity: string
  language: string
  condition: string
  grading: string
  source_platform: SourcePlatform
  source_url: string
  price_jpy: number | null
  domestic_shipping_jpy: number | null
  service_fee_jpy: number | null
  cardmarket_product_id: number | null
  notes: string
}

function initialState(item = props.item): ItemForm {
  return {
    lot_id: item?.lot_id ?? props.lotId,
    game: item?.game ?? 'pokemon',
    name: item?.name ?? '',
    set_code: item?.set_code ?? '',
    card_number: item?.card_number ?? '',
    rarity: item?.rarity ?? '',
    language: item?.language ?? 'ja',
    condition: item?.condition ?? '',
    grading: item?.grading ?? '',
    source_platform: item?.source_platform ?? 'mercari',
    source_url: item?.source_url ?? '',
    price_jpy: item?.price_jpy ?? null,
    domestic_shipping_jpy: item?.domestic_shipping_jpy ?? 0,
    // Left empty on creation, takes the proxy service fee from the settings.
    service_fee_jpy: item?.service_fee_jpy ?? null,
    cardmarket_product_id: item?.cardmarket_product_id ?? null,
    notes: item?.notes ?? '',
  }
}

const state = reactive(initialState())
watch(open, (isOpen) => isOpen && Object.assign(state, initialState()))

function validate(form: ItemForm): FormError[] {
  const errors: FormError[] = []
  if (!form.name.trim()) errors.push({ name: 'name', message: 'Nom obligatoire.' })
  if (form.price_jpy == null) errors.push({ name: 'price_jpy', message: 'Prix obligatoire.' })
  return errors
}

function toBody(form: ItemForm): ItemCreate {
  const text = (value: string) => value.trim() || null
  return {
    game: form.game,
    name: form.name.trim(),
    set_code: text(form.set_code),
    card_number: text(form.card_number),
    rarity: text(form.rarity),
    language: form.language.trim() || 'ja',
    condition: text(form.condition),
    grading: text(form.grading),
    source_platform: form.source_platform,
    source_url: text(form.source_url),
    price_jpy: form.price_jpy ?? 0,
    domestic_shipping_jpy: form.domestic_shipping_jpy ?? 0,
    service_fee_jpy: form.service_fee_jpy ?? props.item?.service_fee_jpy ?? null,
    cardmarket_product_id: form.cardmarket_product_id,
    notes: text(form.notes),
  }
}

const saving = ref(false)
// Entering a whole parcel card by card: keep the modal open and the shared fields filled.
const keepOpen = ref(false)

async function submit() {
  saving.value = true
  try {
    const body = toBody(state)
    let saved: Item
    if (props.item) {
      saved = await engine.updateItem(props.item.id, {
        ...body,
        service_fee_jpy: body.service_fee_jpy ?? props.item.service_fee_jpy,
        ...(state.lot_id != null && { lot_id: state.lot_id }),
      })
    } else {
      saved = await engine.addItem(state.lot_id!, body)
    }
    emit('saved', saved)
    if (keepOpen.value && !props.item) {
      toast.add({ title: `${saved.name} ajoutée`, color: 'success', duration: 2000 })
      Object.assign(state, {
        name: '',
        card_number: '',
        rarity: '',
        source_url: '',
        price_jpy: null,
        domestic_shipping_jpy: 0,
        cardmarket_product_id: null,
        notes: '',
      })
    } else {
      open.value = false
    }
  } catch (error) {
    showError(error)
  } finally {
    saving.value = false
    keepOpen.value = false
  }
}

const lotItems = computed(() =>
  (props.lots ?? []).map((lot) => ({ value: lot.id, label: lot.label })),
)
const gameItems = selectItems(GAME_LABELS)
const sourceItems = selectItems(SOURCE_LABELS)
</script>

<template>
  <UModal
    v-model:open="open"
    :title="item ? 'Modifier la carte' : 'Ajouter une carte'"
    :ui="{ content: 'sm:max-w-2xl', footer: 'justify-end' }"
  >
    <template #body>
      <UForm id="item-form" :state="state" :validate="validate" class="space-y-6" @submit="submit">
        <div class="grid gap-4 sm:grid-cols-3">
          <UFormField label="Nom" name="name" required class="sm:col-span-2">
            <UInput v-model="state.name" placeholder="Pikachu ex SAR" autofocus class="w-full" />
          </UFormField>
          <UFormField label="Jeu" name="game">
            <USelect v-model="state.game" :items="gameItems" class="w-full" />
          </UFormField>
          <UFormField label="Extension" name="set_code">
            <UInput v-model="state.set_code" placeholder="SV8a, OP09…" class="w-full" />
          </UFormField>
          <UFormField label="Numéro" name="card_number">
            <UInput v-model="state.card_number" placeholder="205/187" class="w-full" />
          </UFormField>
          <UFormField label="Rareté" name="rarity">
            <UInput v-model="state.rarity" placeholder="SAR, SR, AA…" class="w-full" />
          </UFormField>
          <UFormField label="Langue" name="language">
            <UInput v-model="state.language" class="w-full" />
          </UFormField>
          <UFormField label="État" name="condition">
            <UInput v-model="state.condition" placeholder="Near Mint" class="w-full" />
          </UFormField>
          <UFormField label="Gradation" name="grading">
            <UInput v-model="state.grading" placeholder="PSA 10" class="w-full" />
          </UFormField>
        </div>

        <USeparator label="Achat" />
        <div class="grid gap-4 sm:grid-cols-3">
          <UFormField label="Prix" name="price_jpy" required>
            <MoneyInput v-model="state.price_jpy" currency="JPY" />
          </UFormField>
          <UFormField label="Port au Japon" name="domestic_shipping_jpy">
            <MoneyInput v-model="state.domestic_shipping_jpy" currency="JPY" />
          </UFormField>
          <UFormField label="Frais de service" name="service_fee_jpy">
            <MoneyInput
              v-model="state.service_fee_jpy"
              currency="JPY"
              placeholder="Valeur des paramètres"
            />
          </UFormField>
          <UFormField label="Site" name="source_platform">
            <USelect v-model="state.source_platform" :items="sourceItems" class="w-full" />
          </UFormField>
          <UFormField label="Lien de l’annonce" name="source_url" class="sm:col-span-2">
            <UInput v-model="state.source_url" type="url" class="w-full" />
          </UFormField>
          <UFormField v-if="item && lotItems.length" label="Lot" name="lot_id">
            <USelect v-model="state.lot_id" :items="lotItems" class="w-full" />
          </UFormField>
          <UFormField label="ID produit Cardmarket" name="cardmarket_product_id">
            <UInputNumber
              v-model="state.cardmarket_product_id"
              :format-options="{ useGrouping: false }"
              :min="1"
              :increment="false"
              :decrement="false"
              class="w-full"
            />
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
        v-if="!item"
        type="submit"
        form="item-form"
        color="neutral"
        variant="outline"
        label="Ajouter et continuer"
        :loading="saving && keepOpen"
        @click="keepOpen = true"
      />
      <UButton
        type="submit"
        form="item-form"
        :loading="saving && !keepOpen"
        :label="item ? 'Enregistrer' : 'Ajouter'"
        @click="keepOpen = false"
      />
    </template>
  </UModal>
</template>
