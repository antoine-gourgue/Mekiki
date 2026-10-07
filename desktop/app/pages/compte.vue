<script setup lang="ts">
import type { FormError } from '@nuxt/ui'

const auth = useAuth()
const showError = useErrorToast()
const toast = useToast()

const MIN_PASSWORD = 8

const { error, refresh } = useAsyncData('account', () => auth.loadUser())

const profile = reactive({ display_name: '' })
watch(
  auth.user,
  (user) => {
    if (user) profile.display_name = user.display_name
  },
  { immediate: true },
)
const profileDirty = computed(
  () => !!auth.user.value && profile.display_name.trim() !== auth.user.value.display_name,
)
const savingProfile = ref(false)

async function saveProfile() {
  savingProfile.value = true
  try {
    await auth.update({ display_name: profile.display_name.trim() })
    toast.add({ title: 'Profil enregistré', color: 'success' })
  } catch (failure) {
    showError(failure)
  } finally {
    savingProfile.value = false
  }
}

const passwords = reactive({ current: '', next: '', confirm: '' })
const savingPassword = ref(false)

function validatePasswords(state: typeof passwords): FormError[] {
  const errors: FormError[] = []
  if (!state.current) errors.push({ name: 'current', message: 'Requis.' })
  if (state.next.length < MIN_PASSWORD) {
    errors.push({ name: 'next', message: `${MIN_PASSWORD} caractères minimum.` })
  }
  if (state.confirm !== state.next) {
    errors.push({ name: 'confirm', message: 'Les deux mots de passe diffèrent.' })
  }
  return errors
}

async function changePassword() {
  savingPassword.value = true
  try {
    await auth.update({ current_password: passwords.current, new_password: passwords.next })
    Object.assign(passwords, { current: '', next: '', confirm: '' })
    toast.add({
      title: 'Mot de passe modifié',
      description: 'Vos autres appareils ont été déconnectés.',
      color: 'success',
    })
  } catch (failure) {
    showError(failure)
  } finally {
    savingPassword.value = false
  }
}
</script>

<template>
  <UDashboardPanel id="account">
    <template #header>
      <UDashboardNavbar title="Mon compte">
        <template #leading><UDashboardSidebarCollapse /></template>
        <template #right>
          <UButton
            label="Se déconnecter"
            icon="i-lucide-log-out"
            color="neutral"
            variant="subtle"
            @click="auth.logout()"
          />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="Impossible de charger le compte"
        :description="engineErrorMessage(error)"
        :actions="[{ label: 'Réessayer', onClick: () => refresh() }]"
      />

      <div v-else-if="auth.user.value" class="mx-auto w-full max-w-3xl space-y-6">
        <UCard>
          <template #header>
            <h2 class="font-medium text-highlighted">Profil</h2>
            <p class="text-sm text-muted">
              Compte créé le {{ formatDate(auth.user.value.created_at) }}.
            </p>
          </template>
          <UForm :state="profile" class="space-y-4" @submit="saveProfile">
            <div class="grid gap-4 sm:grid-cols-2">
              <UFormField label="Nom affiché" name="display_name" required>
                <UInput v-model="profile.display_name" :maxlength="80" class="w-full" />
              </UFormField>
              <UFormField label="Adresse e-mail" help="Elle sert d’identifiant de connexion.">
                <UInput :model-value="auth.user.value.email" disabled class="w-full" />
              </UFormField>
            </div>
            <UButton
              type="submit"
              label="Enregistrer"
              icon="i-lucide-save"
              :disabled="!profileDirty || !profile.display_name.trim()"
              :loading="savingProfile"
            />
          </UForm>
        </UCard>

        <UCard>
          <template #header>
            <h2 class="font-medium text-highlighted">Mot de passe</h2>
            <p class="text-sm text-muted">Le changer déconnecte vos autres appareils.</p>
          </template>
          <UForm
            :state="passwords"
            :validate="validatePasswords"
            class="space-y-4"
            @submit="changePassword"
          >
            <UFormField label="Mot de passe actuel" name="current" required>
              <UInput
                v-model="passwords.current"
                type="password"
                autocomplete="current-password"
                class="w-full sm:w-1/2"
              />
            </UFormField>
            <div class="grid gap-4 sm:grid-cols-2">
              <UFormField label="Nouveau mot de passe" name="next" required>
                <UInput
                  v-model="passwords.next"
                  type="password"
                  autocomplete="new-password"
                  class="w-full"
                />
              </UFormField>
              <UFormField label="Confirmation" name="confirm" required>
                <UInput
                  v-model="passwords.confirm"
                  type="password"
                  autocomplete="new-password"
                  class="w-full"
                />
              </UFormField>
            </div>
            <UButton
              type="submit"
              label="Changer le mot de passe"
              icon="i-lucide-key-round"
              :loading="savingPassword"
            />
          </UForm>
        </UCard>

        <ConnectedAccounts />
      </div>
    </template>
  </UDashboardPanel>
</template>
