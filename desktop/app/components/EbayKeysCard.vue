<script setup lang="ts">
import type { EbayStatus } from '~/types/engine'

/**
 * The account's own eBay developer keys, for live eBay listings in the card panels. eBay
 * checks them before they are saved; the Cert ID is never shown again once saved.
 */
const engine = useEngine()
const showError = useErrorToast()
const toast = useToast()

const status = ref<EbayStatus | null>(null)
const clientId = ref('')
const clientSecret = ref('')
const saving = ref(false)
const failure = ref<string | null>(null)

onMounted(async () => {
  try {
    status.value = await engine.ebayStatus()
    clientId.value = status.value.client_id ?? ''
  } catch (error) {
    showError(error)
  }
})

const hasOwnKeys = computed(() => status.value?.source === 'account')
const canSave = computed(
  () =>
    !!clientId.value.trim() &&
    (!!clientSecret.value.trim() ||
      (hasOwnKeys.value && clientId.value.trim() === status.value?.client_id)),
)

async function save() {
  saving.value = true
  failure.value = null
  try {
    status.value = await engine.saveEbayKeys({
      client_id: clientId.value.trim(),
      client_secret: clientSecret.value.trim() || null,
    })
    clientSecret.value = ''
    toast.add({ title: 'Clés eBay vérifiées et enregistrées', color: 'success' })
  } catch (error) {
    failure.value = engineErrorMessage(error)
  } finally {
    saving.value = false
  }
}

async function remove() {
  try {
    status.value = await engine.removeEbayKeys()
    clientId.value = ''
    clientSecret.value = ''
  } catch (error) {
    showError(error)
  }
}
</script>

<template>
  <UCard id="ebay" :ui="{ body: 'space-y-4 sm:p-5' }">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="font-semibold text-highlighted">Clés eBay</h2>
        <p class="mt-1 text-sm text-dimmed">
          Vos propres clés d’application eBay : les fiches des cartes montrent alors les annonces
          eBay en direct, sans passer par Chrome. Chaque compte a les siennes.
        </p>
      </div>
      <UBadge
        v-if="status"
        variant="soft"
        :color="status.configured ? 'success' : 'neutral'"
        :label="
          hasOwnKeys
            ? 'Vos clés sont actives'
            : status.configured
              ? 'Clés communes du moteur'
              : 'Non configurées'
        "
      />
    </div>

    <p v-if="status?.configured && status.sold_api != null" class="text-sm text-muted">
      <template v-if="status.sold_api">
        <UIcon name="i-lucide-circle-check" class="mr-1 size-4 align-text-bottom text-success" />
        Ventes réussies lues par l’API d’eBay (Marketplace Insights) : plus besoin de Chrome pour
        les voir.
      </template>
      <template v-else>
        Ventes réussies lues dans Chrome : eBay réserve son API des ventes réussies (Marketplace
        Insights) aux applications qu’il approuve. Si la vôtre l’obtient, Mekiki s’en servira tout
        seul.
      </template>
    </p>

    <ol class="list-inside list-decimal space-y-1 text-sm text-muted">
      <li>
        Sur
        <ULink
          as="button"
          class="text-primary"
          @click="openExternal('https://developer.ebay.com/my/keys')"
        >
          developer.ebay.com › Application Keysets</ULink
        >, prenez le jeu de clés <strong class="text-highlighted">Production</strong> (pas Sandbox).
      </li>
      <li>Copiez l’App ID (Client ID) et le Cert ID (Client Secret) ci-dessous.</li>
    </ol>

    <form class="space-y-4" @submit.prevent="save">
      <div class="grid gap-4 sm:grid-cols-2">
        <UFormField label="App ID (Client ID)">
          <UInput
            v-model="clientId"
            placeholder="VotreNom-Mekiki-PRD-…"
            autocomplete="off"
            spellcheck="false"
            class="w-full"
          />
        </UFormField>
        <UFormField
          label="Cert ID (Client Secret)"
          :help="hasOwnKeys ? 'Enregistré : laissez vide pour le garder.' : undefined"
        >
          <UInput
            v-model="clientSecret"
            type="password"
            :placeholder="hasOwnKeys ? '••••••••••••' : 'PRD-…'"
            autocomplete="off"
            class="w-full"
          />
        </UFormField>
      </div>

      <UAlert
        v-if="failure"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        title="Clés non enregistrées"
        :description="failure"
      />

      <div class="flex flex-wrap justify-end gap-2">
        <UButton
          v-if="hasOwnKeys"
          color="neutral"
          variant="ghost"
          label="Retirer mes clés"
          @click="remove"
        />
        <UButton
          type="submit"
          icon="i-lucide-shield-check"
          label="Vérifier et enregistrer"
          :loading="saving"
          :disabled="!canSave"
        />
      </div>
    </form>
  </UCard>
</template>
