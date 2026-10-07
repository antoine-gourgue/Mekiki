<script setup lang="ts">
import type { ResaleQuery } from '~/types/engine'

/** European prices of one card, opened from a listing's menu (see useResaleModal). */
defineProps<{ query: ResaleQuery; title: string }>()
const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <UModal title="Prix en Europe" :description="title" @update:open="(o) => !o && emit('close')">
    <template #body>
      <ResalePanel :query="query" />
    </template>
  </UModal>
</template>
