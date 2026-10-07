<script setup lang="ts">
import type { FormError } from '@nuxt/ui'
import type { Item, ItemPhoto, ListingDraft, ListingSite, SalePlatform } from '~/types/engine'

/**
 * Puts `item` up for sale, changes its listing or withdraws it. For eBay and Vinted it also
 * prepares the listing text: the user pastes it on the site, adds photos and publishes.
 */
const props = defineProps<{ item: Item | null }>()
const emit = defineEmits<{ saved: [item: Item]; photosChanged: [] }>()
const open = defineModel<boolean>('open', { default: false })

const engine = useEngine()
const showError = useErrorToast()
const toast = useToast()

const state = reactive<{ platform: SalePlatform; price_cents: number | null }>({
  platform: 'cardmarket',
  price_cents: null,
})

const photos = ref<ItemPhoto[]>([])

watch(open, (isOpen) => {
  if (!isOpen || !props.item) return
  state.platform = props.item.listing_platform ?? 'cardmarket'
  state.price_cents = props.item.listing_price_cents
  photos.value = [...props.item.photos]
  showPrices.value = false
})

const SITES: Record<ListingSite, string> = { ebay: 'eBay', vinted: 'Vinted' }
const site = computed(() =>
  state.platform === 'ebay' || state.platform === 'vinted' ? state.platform : null,
)

const draft = ref<ListingDraft | null>(null)
const loadingDraft = ref(false)
const showPrices = ref(false)

watch(
  [open, site],
  async ([isOpen, current]) => {
    draft.value = null
    if (!isOpen || !current || !props.item) return
    loadingDraft.value = true
    try {
      draft.value = await engine.listingDraft(props.item.id, current)
      state.price_cents ??= draft.value.price_cents
    } catch (error) {
      showError(error)
    } finally {
      loadingDraft.value = false
    }
  },
  { immediate: true },
)

async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.add({ title: `${what} copié`, color: 'success', duration: 1500 })
  } catch {
    toast.add({ title: 'Copie impossible', description: 'Sélectionnez le texte à la main.' })
  }
}

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
    :ui="{ content: site ? 'sm:max-w-2xl' : undefined, footer: 'justify-between' }"
  >
    <template #body>
      <div v-if="item" class="mb-6 space-y-2">
        <h3 class="font-medium text-highlighted">Photos</h3>
        <ItemPhotos v-model="photos" :item-id="item.id" @changed="emit('photosChanged')" />
      </div>

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
        <UFormField
          label="Prix affiché"
          name="price_cents"
          required
          :help="
            draft?.price_source && draft.price_cents === state.price_cents
              ? `Suggéré : ${PRICE_SOURCE_LABELS[draft.price_source] ?? draft.price_source}.`
              : undefined
          "
        >
          <MoneyInput v-model="state.price_cents" currency="EUR" autofocus />
        </UFormField>
        <p v-if="item" class="text-sm text-muted sm:col-span-2">
          Coût de revient : {{ formatCents(item.landed_cost.total_cents) }}. Le net et la marge
          prévus apparaissent dans le stock une fois l’annonce enregistrée.
        </p>
      </UForm>

      <div v-if="site" class="mt-6 space-y-4 border-t border-default pt-4">
        <div>
          <h3 class="font-medium text-highlighted">Annonce prête pour {{ SITES[site] }}</h3>
          <p class="text-sm text-muted">
            Copiez le texte, ouvrez {{ SITES[site] }}, ajoutez vos photos et publiez. Enregistrez
            ensuite l’annonce ici pour suivre la marge prévue.
          </p>
        </div>

        <div v-if="loadingDraft" class="flex justify-center py-4">
          <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-muted" />
        </div>
        <template v-else-if="draft">
          <UFormField label="Titre" :hint="`${draft.title.length}/80`">
            <UInput v-model="draft.title" :maxlength="80" class="w-full" :ui="{ trailing: 'pe-1' }">
              <template #trailing>
                <UButton
                  icon="i-lucide-copy"
                  color="neutral"
                  variant="link"
                  size="sm"
                  aria-label="Copier le titre"
                  @click="copy(draft.title, 'Titre')"
                />
              </template>
            </UInput>
          </UFormField>
          <UFormField label="Description">
            <UTextarea v-model="draft.description" autoresize :rows="6" class="w-full" />
          </UFormField>
          <div class="flex flex-wrap gap-2">
            <UButton
              icon="i-lucide-copy"
              color="neutral"
              variant="subtle"
              label="Copier la description"
              @click="copy(draft.description, 'Description')"
            />
            <UButton
              icon="i-lucide-euro"
              color="neutral"
              variant="subtle"
              :label="showPrices ? 'Masquer les prix' : 'Voir les prix du marché'"
              @click="showPrices = !showPrices"
            />
            <span class="flex-1" />
            <UButton
              icon="i-lucide-external-link"
              :label="`Créer l’annonce sur ${SITES[site]}`"
              @click="openExternal(draft.new_listing_url)"
            />
          </div>
          <ResalePanel v-if="showPrices" :query="{ q: draft.query }" />
        </template>
      </div>
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
