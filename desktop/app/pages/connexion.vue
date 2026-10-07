<script setup lang="ts">
import type { AuthFormField, FormSubmitEvent } from '@nuxt/ui'
import type { LoginRequest } from '~/types/engine'

definePageMeta({ layout: 'public' })

const auth = useAuth()
const route = useRoute()

const fields: AuthFormField[] = [
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
    autocomplete: 'current-password',
    required: true,
  },
]

const failure = ref<string | null>(null)
const loading = ref(false)

async function submit(event: FormSubmitEvent<LoginRequest>) {
  failure.value = null
  loading.value = true
  try {
    await auth.login(event.data)
    await navigateTo(afterSignIn(route.query.redirect))
  } catch (error) {
    failure.value = engineErrorMessage(error)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <UContainer class="flex justify-center py-16">
    <UPageCard class="w-full max-w-md">
      <UAuthForm
        icon="i-lucide-log-in"
        title="Connexion"
        description="Retrouvez vos lots, votre stock et vos recherches."
        :fields="fields"
        :submit="{ label: 'Se connecter', block: true }"
        :loading="loading"
        @submit="submit"
      >
        <template #validation>
          <UAlert
            v-if="route.query.session === 'expiree' && !failure"
            color="warning"
            variant="subtle"
            icon="i-lucide-clock"
            title="Votre session a expiré"
            description="Reconnectez-vous pour continuer."
          />
          <UAlert
            v-if="failure"
            color="error"
            variant="subtle"
            icon="i-lucide-circle-alert"
            :title="failure"
          />
        </template>
        <template #footer>
          Pas encore de compte ?
          <ULink to="/inscription" class="font-medium text-primary">Créer un compte</ULink>
        </template>
      </UAuthForm>
    </UPageCard>
  </UContainer>
</template>
