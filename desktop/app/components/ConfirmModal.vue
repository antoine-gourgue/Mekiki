<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    description?: string
    confirmLabel?: string
  }>(),
  { description: undefined, confirmLabel: 'Supprimer' },
)

const emit = defineEmits<{ close: [confirmed: boolean] }>()
</script>

<template>
  <UModal
    :title="title"
    :description="description"
    :close="false"
    :ui="{ footer: 'justify-end' }"
    @update:open="(open) => !open && emit('close', false)"
  >
    <template #footer>
      <UButton color="neutral" variant="ghost" label="Annuler" @click="emit('close', false)" />
      <UButton color="error" :label="confirmLabel" @click="emit('close', true)" />
    </template>
  </UModal>
</template>
