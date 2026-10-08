<script setup lang="ts">
/** Page title bar: large title, an optional line under it, actions on the right. */
defineProps<{ title: string; description?: string }>()
</script>

<template>
  <UDashboardNavbar
    :ui="{ title: 'block min-w-0 whitespace-normal', right: 'flex-wrap justify-end gap-2' }"
  >
    <template #leading
      ><UDashboardSidebarCollapse class="-ms-1.5 self-start text-dimmed"
    /></template>
    <template #title>
      <h1 class="truncate text-2xl font-semibold tracking-tight text-highlighted">{{ title }}</h1>
      <p v-if="description" class="mt-1 text-sm font-normal text-muted">{{ description }}</p>
    </template>
    <template #right><slot name="right" /></template>
  </UDashboardNavbar>
</template>
