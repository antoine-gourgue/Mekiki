<script setup lang="ts">
import { fr } from '@nuxt/ui/locale'
</script>

<template>
  <UApp :locale="fr" :toaster="{ position: 'bottom-right' }">
    <UpdateBanner />
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </UApp>
</template>
