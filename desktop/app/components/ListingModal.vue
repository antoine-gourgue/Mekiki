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
})

const SITES: Record<ListingSite, string> = { ebay: 'eBay', vinted: 'Vinted' }
const site = computed(() =>
  state.platform === 'ebay' || state.platform === 'vinted' ? state.platform : null,
)

const draft = ref<ListingDraft | null>(null)
const loadingDraft = ref(false)

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

// Publishing in Mekiki's Chrome window: started here, followed until it ends, even with the
// modal closed. Reopened, the modal shows the card's last publication on the site.
const job = ref<PublishJob | null>(null)
// Why the engine refused to publish the card again: already for sale, or maybe online.
const conflict = ref<string | null>(null)
let jobTimer: ReturnType<typeof setTimeout> | undefined
// Cleared on unmount, so a read still on its way does not start the loop again.
let alive = true
onBeforeUnmount(() => {
  alive = false
  clearTimeout(jobTimer)
})
watch(
  [open, site],
  async ([isOpen, current]) => {
    if (!isOpen) return
    clearTimeout(jobTimer)
    job.value = null
    conflict.value = null
    if (!current || !props.item) return
    const itemId = props.item.id
    let last: PublishJob | null = null
    try {
      last = await engine.publishStatus(current, itemId)
    } catch {
      // Unknown: the engine refuses a second publication anyway.
    }
    // Another site or card may have been chosen meanwhile.
    if (site.value !== current || props.item?.id !== itemId) return
    job.value = last
    if (last?.status === 'running') followJob(current, itemId)
  },
  { immediate: true },
)

async function publishNow(force = false) {
  const current = site.value
  if (!props.item || !current || !draft.value || state.price_cents == null) return
  conflict.value = null
  try {
    job.value = await engine.publishListing(current, props.item.id, {
      title: draft.value.title,
      description: draft.value.description,
      price_cents: state.price_cents,
      force,
    })
    followJob(current, props.item.id)
  } catch (error) {
    if ((error as { statusCode?: number }).statusCode === 409) {
      conflict.value = engineErrorMessage(error)
    } else {
      showError(error, 'Publication impossible')
    }
  }
}

function followJob(current: ListingSite, itemId: number) {
  jobTimer = setTimeout(async () => {
    try {
      job.value = await engine.publishStatus(current, itemId)
    } catch {
      // A missed poll is retried on the next tick.
    }
    if (!alive) return
    if (job.value?.status === 'running') return followJob(current, itemId)
    if (job.value?.status === 'done') {
      toast.add({
        title: `Annonce publiée sur ${SITES[current]}`,
        color: 'success',
        actions: job.value.url
          ? [{ label: 'Voir l’annonce', onClick: () => void openExternal(job.value!.url!) }]
          : [],
      })
      emit('saved', await engine.getItem(itemId))
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
    :title="`Mettre en vente · ${item?.name ?? ''}`"
    :description="item ? `Coût de revient ${formatCents(item.landed_cost.total_cents)}` : undefined"
    :ui="{
      content: site ? 'sm:max-w-5xl' : 'sm:max-w-xl',
      body: 'p-0 sm:p-0',
      footer: 'justify-between',
    }"
  >
    <template #body>
      <div class="flex flex-wrap">
        <div class="min-w-0 flex-[1_1_440px] space-y-5 p-5 sm:p-6">
          <SegmentedControl
            v-model="state.platform"
            :items="platformItems"
            label="Plateforme"
            class="flex w-full *:flex-1"
          />

          <div v-if="item" class="space-y-2">
            <h3 class="text-sm font-medium text-muted">Photos</h3>
            <ItemPhotos v-model="photos" :item-id="item.id" @changed="emit('photosChanged')" />
          </div>

          <UForm id="listing-form" :state="state" :validate="validate" @submit="save(state)">
            <UFormField
              label="Prix affiché"
              name="price_cents"
              required
              :help="
                draft?.price_source && draft.price_cents === state.price_cents
                  ? `Suggéré : ${PRICE_SOURCE_LABELS[draft.price_source] ?? draft.price_source}.`
                  : 'Le net et la marge prévus apparaissent dans le stock une fois l’annonce enregistrée.'
              "
            >
              <MoneyInput v-model="state.price_cents" currency="EUR" autofocus />
            </UFormField>
          </UForm>

          <template v-if="site">
            <div v-if="loadingDraft" class="flex justify-center py-4">
              <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-muted" />
            </div>
            <template v-else-if="draft">
              <UFormField label="Titre" :hint="`${draft.title.length}/80`">
                <UInput
                  v-model="draft.title"
                  :maxlength="80"
                  class="w-full"
                  :ui="{ trailing: 'pe-1' }"
                >
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
                <UTextarea v-model="draft.description" autoresize :rows="5" class="w-full" />
              </UFormField>
              <div class="flex flex-wrap gap-2">
                <UButton
                  icon="i-lucide-copy"
                  color="neutral"
                  variant="outline"
                  size="md"
                  label="Copier la description"
                  @click="copy(draft.description, 'Description')"
                />
                <span class="flex-1" />
                <UButton
                  trailing-icon="i-lucide-arrow-up-right"
                  color="neutral"
                  variant="ghost"
                  size="md"
                  :label="`Ouvrir ${SITES[site]}`"
                  @click="openExternal(draft.new_listing_url)"
                />
              </div>
            </template>
          </template>
        </div>

        <div
          v-if="site"
          class="min-w-0 flex-[1_1_360px] space-y-4 border-t border-default bg-[#121116] p-5 sm:p-6 lg:border-t-0 lg:border-l"
        >
          <div>
            <h3 class="font-semibold text-highlighted">Publier automatiquement</h3>
            <p class="mt-1 text-sm text-muted">
              Mekiki remplit le formulaire {{ SITES[site] }} dans sa fenêtre Chrome, hors de
              l’écran, avec {{ photos.length }} photo{{ photos.length > 1 ? 's' : '' }}, puis
              publie. Vous suivez chaque étape ici.
            </p>
          </div>

          <BrowserLog v-if="job" :active="job.status === 'running'" />
          <p
            v-else
            class="rounded-lg border border-dashed border-accented px-4 py-6 text-center text-sm text-dimmed"
          >
            Le journal de la fenêtre Chrome s’affiche ici pendant la publication.
          </p>

          <p v-if="!photos.length" class="text-sm text-error">
            Ajoutez au moins une photo : {{ SITES[site] }} n’accepte pas d’annonce sans photo.
          </p>
          <UAlert
            v-if="job?.status === 'done'"
            color="success"
            variant="subtle"
            icon="i-lucide-badge-check"
            title="Annonce publiée"
            :description="job.error ?? 'La carte apparaît désormais comme en vente dans le stock.'"
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
            :description="`${job.error}. La fenêtre Chrome s’est affichée avec le formulaire : vérifiez-le et terminez la publication à la main.`"
          />
          <UAlert
            v-else-if="job?.status === 'to_check'"
            color="warning"
            variant="subtle"
            icon="i-lucide-search-check"
            title="Publication à vérifier"
            :description="`${job.error}. Le formulaire a été envoyé : l’annonce est peut-être en ligne. Ne republiez qu’après avoir vérifié vos annonces ${SITES[site]}.`"
            :actions="[
              {
                label: 'Vérifié : publier à nouveau',
                color: 'neutral',
                variant: 'outline',
                onClick: () => publishNow(true),
              },
            ]"
          />
          <UAlert
            v-if="conflict"
            color="warning"
            variant="subtle"
            icon="i-lucide-copy-check"
            title="Déjà publiée ?"
            :description="conflict"
            :actions="[
              {
                label: 'Publier une autre annonce',
                color: 'neutral',
                variant: 'outline',
                onClick: () => publishNow(true),
              },
            ]"
          />

          <UButton
            block
            size="xl"
            icon="i-lucide-send"
            :label="
              job?.status === 'running'
                ? `Publication sur ${SITES[site]}…`
                : `Publier sur ${SITES[site]}`
            "
            :loading="job?.status === 'running'"
            :disabled="
              !draft ||
              !photos.length ||
              state.price_cents == null ||
              job?.status === 'done' ||
              job?.status === 'to_check' ||
              !!conflict
            "
            @click="publishNow()"
          />
          <p class="text-xs text-dimmed">
            Une vérification anti-robot ? La fenêtre s’affiche pour que vous la passiez vous-même.
          </p>
        </div>
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
      <UButton type="submit" form="listing-form" :loading="saving" label="Enregistrer l’annonce" />
    </template>
  </UModal>
</template>
