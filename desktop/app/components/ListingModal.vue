<script setup lang="ts">
import type { FormError } from '@nuxt/ui'
import type {
  Item,
  ItemPhoto,
  ListingDraft,
  ListingSite,
  PublishJob,
  SalePlatform,
} from '~/types/engine'

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

// Publishing in Mekiki's Chrome window: started here, followed until it ends.
const job = ref<PublishJob | null>(null)
let jobTimer: ReturnType<typeof setTimeout> | undefined
onBeforeUnmount(() => clearTimeout(jobTimer))
watch(open, (isOpen) => {
  if (isOpen) job.value = null
})

async function publishNow() {
  const current = site.value
  if (!props.item || !current || !draft.value || state.price_cents == null) return
  try {
    job.value = await engine.publishListing(current, props.item.id, {
      title: draft.value.title,
      description: draft.value.description,
      price_cents: state.price_cents,
    })
    followJob(current, props.item.id)
  } catch (error) {
    showError(error, 'Publication impossible')
  }
}

function followJob(current: ListingSite, itemId: number) {
  jobTimer = setTimeout(async () => {
    try {
      job.value = await engine.publishStatus(current, itemId)
    } catch {
      // A missed poll is retried on the next tick.
    }
    if (job.value?.status === 'running') return followJob(current, itemId)
    if (job.value?.status === 'done' && props.item) {
      toast.add({
        title: `Annonce publiée sur ${SITES[current]}`,
        color: 'success',
        actions: job.value.url
          ? [{ label: 'Voir l’annonce', onClick: () => void openExternal(job.value!.url!) }]
          : [],
      })
      emit('saved', await engine.getItem(props.item.id))
    }
  }, 2000)
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
              color="neutral"
              variant="subtle"
              :label="`Ouvrir ${SITES[site]}`"
              @click="openExternal(draft.new_listing_url)"
            />
          </div>

          <div class="space-y-2 rounded-md border border-default p-3">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="min-w-0">
                <p class="text-sm font-medium">Publier automatiquement</p>
                <p class="text-xs text-muted">
                  Mekiki remplit le formulaire {{ SITES[site] }} dans sa fenêtre Chrome, avec
                  {{ photos.length }} photo{{ photos.length > 1 ? 's' : '' }}, et publie.
                </p>
              </div>
              <UButton
                icon="i-lucide-send"
                :label="`Publier sur ${SITES[site]}`"
                :loading="job?.status === 'running'"
                :disabled="!photos.length || state.price_cents == null || job?.status === 'done'"
                @click="publishNow"
              />
            </div>
            <p v-if="!photos.length" class="text-xs text-warning">
              Ajoutez au moins une photo : {{ SITES[site] }} n’accepte pas d’annonce sans photo.
            </p>
            <UAlert
              v-if="job?.status === 'running'"
              color="info"
              variant="subtle"
              icon="i-lucide-loader-circle"
              title="Publication en cours dans Chrome…"
              description="Laissez la fenêtre Chrome de Mekiki ouverte jusqu’à la fin."
              :ui="{ icon: 'animate-spin' }"
            />
            <UAlert
              v-else-if="job?.status === 'done'"
              color="success"
              variant="subtle"
              icon="i-lucide-badge-check"
              title="Annonce publiée"
              :description="
                job.error ?? 'La carte apparaît désormais comme en vente dans le stock.'
              "
              :actions="
                job.url ? [{ label: 'Voir l’annonce', onClick: () => openExternal(job!.url!) }] : []
              "
            />
            <UAlert
              v-else-if="job?.status === 'failed'"
              color="error"
              variant="subtle"
              icon="i-lucide-circle-alert"
              title="La publication n’est pas allée au bout"
              :description="`${job.error}. Le formulaire est resté ouvert dans Chrome : vérifiez-le et terminez la publication à la main.`"
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
