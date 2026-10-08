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
      <PageNavbar
        title="Mon compte"
        description="Votre stock, vos lots et vos ventes ne sont visibles que par vous."
      />
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

      <div v-else-if="auth.user.value" class="flex flex-wrap items-start gap-5">
        <UCard
          class="min-w-0 flex-[1_1_280px]"
          :ui="{ body: 'flex flex-col items-center gap-3 text-center sm:p-6' }"
        >
          <span
            class="flex size-20 items-center justify-center rounded-full bg-accented text-3xl font-semibold text-highlighted ring-2 ring-vermilion-500 ring-offset-4 ring-offset-(--ui-bg-muted)"
          >
            {{ auth.user.value.display_name.slice(0, 1).toUpperCase() }}
          </span>
          <div>
            <p class="text-xl font-semibold text-highlighted">{{ auth.user.value.display_name }}</p>
            <p class="mt-1 text-sm text-muted">{{ auth.user.value.email }}</p>
          </div>
          <p class="text-sm text-dimmed">
            Compte créé le {{ formatDate(auth.user.value.created_at) }}
          </p>
          <UButton
            label="Se déconnecter"
            icon="i-lucide-log-out"
            color="primary"
            variant="outline"
            block
            class="mt-2"
            @click="auth.logout()"
          />
        </UCard>

        <div class="min-w-0 flex-[2_1_520px] space-y-4">
          <UCard :ui="{ body: 'sm:p-5' }">
            <UForm :state="profile" class="space-y-4" @submit="saveProfile">
              <h2 class="font-semibold text-highlighted">Profil</h2>
              <div class="grid gap-4 sm:grid-cols-2">
                <UFormField label="Nom affiché" name="display_name" required>
                  <UInput v-model="profile.display_name" :maxlength="80" class="w-full" />
                </UFormField>
                <UFormField label="Adresse e-mail" help="Elle sert d’identifiant de connexion.">
                  <UInput :model-value="auth.user.value.email" disabled class="w-full" />
                </UFormField>
              </div>
              <div class="flex justify-end">
                <UButton
                  type="submit"
                  label="Enregistrer"
                  :disabled="!profileDirty || !profile.display_name.trim()"
                  :loading="savingProfile"
                />
              </div>
            </UForm>
          </UCard>

          <UCard :ui="{ body: 'sm:p-5' }">
            <UForm
              :state="passwords"
              :validate="validatePasswords"
              class="space-y-4"
              @submit="changePassword"
            >
              <div>
                <h2 class="font-semibold text-highlighted">Changer le mot de passe</h2>
                <p class="mt-1 text-sm text-dimmed">Le changer déconnecte vos autres appareils.</p>
              </div>
              <UFormField label="Mot de passe actuel" name="current" required>
                <UInput
                  v-model="passwords.current"
                  type="password"
                  autocomplete="current-password"
                  class="w-full sm:w-1/2"
                />
              </UFormField>
              <div class="grid gap-4 sm:grid-cols-2">
                <UFormField
                  label="Nouveau mot de passe"
                  name="next"
                  required
                  :help="`${MIN_PASSWORD} caractères au moins`"
                >
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
              <div class="flex justify-end">
                <UButton
                  type="submit"
                  label="Changer le mot de passe"
                  color="neutral"
                  variant="outline"
                  :loading="savingPassword"
                />
              </div>
            </UForm>
          </UCard>

          <ConnectedAccounts />
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
