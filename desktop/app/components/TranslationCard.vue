<script setup lang="ts">
import type { TranslationStatus } from '~/types/engine'

/**
 * How listing descriptions are translated: a free service by default, DeepL with the
 * account's own key. DeepL checks the key before it is kept; it is never shown again.
 */
const engine = useEngine()
const showError = useErrorToast()
const toast = useToast()

const status = ref<TranslationStatus | null>(null)
// Listing panels translate on opening once a DeepL key is saved (see ListingDescription).
const deepl = useState<boolean | null>('translation-deepl', () => null)
watch(status, (value) => {
  if (value) deepl.value = value.deepl_configured
})
const key = ref('')
const saving = ref(false)
const failure = ref<string | null>(null)

onMounted(async () => {
  try {
    status.value = await engine.translationStatus()
  } catch (error) {
    showError(error)
  }
})

async function save() {
  saving.value = true
  failure.value = null
  try {
    status.value = await engine.saveDeeplKey(key.value.trim())
    key.value = ''
    toast.add({ title: 'Clé DeepL vérifiée et enregistrée', color: 'success' })
  } catch (error) {
    failure.value = engineErrorMessage(error)
  } finally {
    saving.value = false
  }
}

async function remove() {
  try {
    status.value = await engine.removeDeeplKey()
  } catch (error) {
    showError(error)
  }
}
</script>

<template>
  <UCard id="traduction" :ui="{ body: 'space-y-4 sm:p-5' }">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="font-semibold text-highlighted">Traduction des annonces</h2>
        <p class="mt-1 text-sm text-dimmed">
          La fiche d’une annonce traduit la description du vendeur en français. Sans clé, un service
          gratuit en traduit quelques-unes par jour (environ 5 000 caractères) ; avec une clé DeepL,
          gratuite elle aussi, la traduction est meilleure et quasi illimitée.
        </p>
      </div>
      <UBadge
        v-if="status"
        variant="soft"
        :color="status.deepl_configured ? 'success' : 'neutral'"
        :label="status.deepl_configured ? 'DeepL actif' : 'Service gratuit'"
      />
    </div>

    <ol class="list-inside list-decimal space-y-1 text-sm text-muted">
      <li>
        Créez un compte
        <ULink
          as="button"
          class="text-primary"
          @click="openExternal('https://www.deepl.com/fr/pro-api')"
          >DeepL API Free</ULink
        >
        (500 000 caractères par mois).
      </li>
      <li>Copiez la clé d’authentification de votre compte (elle finit par « :fx ») ci-dessous.</li>
    </ol>

    <form class="flex flex-wrap items-end gap-3" @submit.prevent="save">
      <UFormField
        label="Clé DeepL"
        :help="
          status?.deepl_configured
            ? 'Enregistrée : saisissez-en une autre pour la remplacer.'
            : undefined
        "
        class="min-w-64 flex-1"
      >
        <UInput
          v-model="key"
          type="password"
          :placeholder="status?.deepl_configured ? '••••••••••••' : 'xxxxxxxx-xxxx-…:fx'"
          autocomplete="off"
          class="w-full"
        />
      </UFormField>
      <UButton
        v-if="status?.deepl_configured"
        color="neutral"
        variant="ghost"
        label="Retirer la clé"
        @click="remove"
      />
      <UButton
        type="submit"
        icon="i-lucide-shield-check"
        label="Vérifier et enregistrer"
        :loading="saving"
        :disabled="key.trim().length < 10"
      />
    </form>
    <UAlert
      v-if="failure"
      color="error"
      variant="subtle"
      icon="i-lucide-circle-alert"
      title="Clé non enregistrée"
      :description="failure"
    />
  </UCard>
</template>
