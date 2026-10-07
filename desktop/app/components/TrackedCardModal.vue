<script setup lang="ts">
import type { FormError } from '@nuxt/ui'
import type { Game, MarketPrice, TrackedCard, TrackedCardCreate } from '~/types/engine'

/** Adds a card to the watch list, or edits `card` when given. */
const props = defineProps<{
  card?: TrackedCard | null
  /** Pre-filled values, e.g. from a one-off search. */
  initial?: Partial<TrackedCardCreate> | null
  initialProduct?: MarketPrice | null
}>()
const emit = defineEmits<{ saved: [card: TrackedCard] }>()
const open = defineModel<boolean>('open', { default: false })

const engine = useEngine()
const showError = useErrorToast()

interface TrackedCardForm {
  game: Game
  name: string
  set_code: string
  card_number: string
  rarity: string
  grading: string
  search_query: string
  required_keywords: string
  excluded_keywords: string
  target_price_cents: number | null
  min_price_jpy: number | null
  max_price_jpy: number | null
  active: boolean
  notes: string
}

const product = ref<MarketPrice | null>(null)

function initialState(): TrackedCardForm {
  const card = props.card
  const initial = props.initial ?? {}
  return {
    game: card?.game ?? initial.game ?? 'pokemon',
    name: card?.name ?? initial.name ?? '',
    set_code: card?.set_code ?? initial.set_code ?? '',
    card_number: card?.card_number ?? initial.card_number ?? '',
    rarity: card?.rarity ?? initial.rarity ?? '',
    grading: card?.grading ?? initial.grading ?? '',
    search_query: card?.search_query ?? initial.search_query ?? '',
    required_keywords: card?.required_keywords ?? initial.required_keywords ?? '',
    excluded_keywords: card?.excluded_keywords ?? initial.excluded_keywords ?? '',
    target_price_cents: card?.target_price_cents ?? initial.target_price_cents ?? null,
    min_price_jpy: card?.min_price_jpy ?? initial.min_price_jpy ?? null,
    max_price_jpy: card?.max_price_jpy ?? initial.max_price_jpy ?? null,
    active: card?.active ?? true,
    notes: card?.notes ?? '',
  }
}

const state = reactive(initialState())
watch(open, (isOpen) => {
  if (!isOpen) return
  Object.assign(state, initialState())
  product.value = props.card?.market ?? props.initialProduct ?? null
})

// Picking a product names an empty card after it.
watch(product, (picked) => {
  if (picked?.name && !state.name) state.name = picked.name
})

function validate(form: TrackedCardForm): FormError[] {
  return form.name.trim() ? [] : [{ name: 'name', message: 'Nom obligatoire.' }]
}

const saving = ref(false)

async function submit() {
  saving.value = true
  const text = (value: string) => value.trim() || null
  const body = {
    game: state.game,
    name: state.name.trim(),
    set_code: text(state.set_code),
    card_number: text(state.card_number),
    rarity: text(state.rarity),
    grading: text(state.grading),
    cardmarket_product_id: product.value?.id_product ?? null,
    required_keywords: text(state.required_keywords),
    excluded_keywords: text(state.excluded_keywords),
    target_price_cents: state.target_price_cents,
    min_price_jpy: state.min_price_jpy,
    max_price_jpy: state.max_price_jpy,
    active: state.active,
    notes: text(state.notes),
  }
  try {
    const query = text(state.search_query)
    const saved = props.card
      ? await engine.updateTrackedCard(props.card.id, {
          ...body,
          ...(query && { search_query: query }),
        })
      : await engine.createTrackedCard({ ...body, search_query: query })
    emit('saved', saved)
    open.value = false
  } catch (error) {
    showError(error)
  } finally {
    saving.value = false
  }
}

const gameItems = selectItems(GAME_LABELS)
</script>

<template>
  <UModal
    v-model:open="open"
    :title="card ? 'Modifier la carte suivie' : 'Suivre une carte'"
    description="Le scanner cherche cette carte sur Mercari et Yahoo et calcule la marge de chaque annonce."
    :ui="{ content: 'sm:max-w-2xl', footer: 'justify-end' }"
  >
    <template #body>
      <UForm
        id="tracked-card-form"
        :state="state"
        :validate="validate"
        class="space-y-6"
        @submit="submit"
      >
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
          <UFormField label="Numéro" name="card_number" help="Exigé dans le titre">
            <UInput v-model="state.card_number" placeholder="205/187, OP05-119" class="w-full" />
          </UFormField>
          <UFormField label="Rareté" name="rarity">
            <UInput v-model="state.rarity" placeholder="SAR, SR, コミパラ…" class="w-full" />
          </UFormField>
        </div>

        <USeparator label="Cote Cardmarket" />
        <div class="space-y-3">
          <ProductPicker v-model="product" :game="state.game" />
          <UFormField
            label="Prix de revente visé"
            name="target_price_cents"
            help="Vide : la cote Cardmarket. À remplir si la version japonaise se vend moins cher."
          >
            <MoneyInput
              v-model="state.target_price_cents"
              currency="EUR"
              placeholder="Cote Cardmarket"
            />
          </UFormField>
        </div>

        <USeparator label="Recherche" />
        <div class="grid gap-4 sm:grid-cols-2">
          <UFormField
            label="Mots-clés de recherche"
            name="search_query"
            help="Vide : le numéro de la carte"
            class="sm:col-span-2"
          >
            <UInput v-model="state.search_query" placeholder="ピカチュウ 205/187" class="w-full" />
          </UFormField>
          <UFormField
            label="Mots obligatoires"
            name="required_keywords"
            help="Séparés par des espaces"
          >
            <UInput v-model="state.required_keywords" placeholder="コミパラ" class="w-full" />
          </UFormField>
          <UFormField
            label="Mots exclus"
            name="excluded_keywords"
            help="En plus de la liste globale"
          >
            <UInput v-model="state.excluded_keywords" placeholder="傷 ジャンク" class="w-full" />
          </UFormField>
          <UFormField label="Gradation" name="grading" help="Vide : cartes non gradées seulement">
            <UInput v-model="state.grading" placeholder="PSA 10" class="w-full" />
          </UFormField>
          <div class="grid grid-cols-2 gap-4">
            <UFormField label="Prix min." name="min_price_jpy">
              <MoneyInput v-model="state.min_price_jpy" currency="JPY" />
            </UFormField>
            <UFormField label="Prix max." name="max_price_jpy">
              <MoneyInput v-model="state.max_price_jpy" currency="JPY" />
            </UFormField>
          </div>
        </div>

        <USwitch v-model="state.active" label="Inclure dans les scans automatiques" />
        <UFormField label="Notes" name="notes">
          <UTextarea v-model="state.notes" :rows="2" autoresize class="w-full" />
        </UFormField>
      </UForm>
    </template>

    <template #footer>
      <UButton color="neutral" variant="ghost" label="Annuler" @click="open = false" />
      <UButton
        type="submit"
        form="tracked-card-form"
        :loading="saving"
        :label="card ? 'Enregistrer' : 'Suivre la carte'"
      />
    </template>
  </UModal>
</template>
