<script setup lang="ts">
import type { AuthFormField, FormError, FormSubmitEvent } from '@nuxt/ui'
import type { RegisterRequest } from '~/types/engine'

definePageMeta({ layout: 'public' })

const auth = useAuth()

const MIN_PASSWORD = 8

const fields: AuthFormField[] = [
  {
    name: 'display_name',
    type: 'text',
    label: 'Nom affiché',
    placeholder: 'Votre prénom ou le nom de votre boutique',
    autocomplete: 'nickname',
    required: true,
  },
  {
    name: 'email',
    type: 'email',
    label: 'Adresse e-mail',
    placeholder: 'vous@exemple.fr',
    autocomplete: 'email',
    required: true,
  },
  {
    name: 'password',
    type: 'password',
    label: 'Mot de passe',
    help: `${MIN_PASSWORD} caractères minimum.`,
    autocomplete: 'new-password',
    required: true,
  },
]

function validate(state: Partial<RegisterRequest>): FormError[] {
  const errors: FormError[] = []
  if (!state.display_name?.trim()) errors.push({ name: 'display_name', message: 'Requis.' })
  if (!state.email?.includes('@')) {
    errors.push({ name: 'email', message: 'Adresse e-mail invalide.' })
  }
  if ((state.password?.length ?? 0) < MIN_PASSWORD) {
    errors.push({ name: 'password', message: `${MIN_PASSWORD} caractères minimum.` })
  }
  return errors
}

const failure = ref<string | null>(null)
const loading = ref(false)

async function submit(event: FormSubmitEvent<RegisterRequest>) {
  failure.value = null
  loading.value = true
  try {
    await auth.register(event.data)
    await navigateTo('/bienvenue')
  } catch (error) {
    failure.value = engineErrorMessage(error)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthShell>
    <UAuthForm
      title="Créer un compte"
      description="Chaque revendeur a ses propres lots, favoris et paramètres."
      :fields="fields"
      :validate="validate"
      :submit="{ label: 'Créer mon compte', block: true, size: 'xl' }"
      :loading="loading"
      @submit="submit"
    >
      <template #validation>
        <UAlert
          v-if="failure"
          color="error"
          variant="subtle"
          icon="i-lucide-circle-alert"
          :title="failure"
        />
      </template>
      <template #footer>
        Déjà un compte ?
        <ULink to="/connexion" class="font-medium text-primary">Se connecter</ULink>
      </template>
    </UAuthForm>
  </AuthShell>
</template>
