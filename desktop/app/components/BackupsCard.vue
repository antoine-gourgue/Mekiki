<script setup lang="ts">
import type { Backup, Backups } from '~/types/engine'

/**
 * The copies of the database: one a day while Mekiki runs (the latest 30 kept), and those made
 * by hand. Any of them can be put back with the first account's password: the current state is
 * copied first, so a restore can be undone.
 */
const engine = useEngine()
const showError = useErrorToast()
const toast = useToast()

const state = ref<Backups | null>(null)
const creating = ref(false)
const restoring = ref<string | null>(null)
const showAll = ref(false)
const SHOWN = 5

async function load() {
  try {
    state.value = await engine.backups()
  } catch (error) {
    showError(error)
  }
}
onMounted(load)

const shown = computed(() => {
  const all = state.value?.backups ?? []
  return showAll.value ? all : all.slice(0, SHOWN)
})

function size(bytes: number) {
  return bytes >= 1_048_576
    ? `${(bytes / 1_048_576).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Mo`
    : `${Math.ceil(bytes / 1024).toLocaleString('fr-FR')} Ko`
}

async function backupNow() {
  creating.value = true
  try {
    await engine.createBackup()
    toast.add({ title: 'Sauvegarde faite', color: 'success' })
    await load()
  } catch (error) {
    showError(error)
  } finally {
    creating.value = false
  }
}

// The copy to restore, waiting for the password.
const asked = ref<Backup | null>(null)
const password = ref('')
const failure = ref<string | null>(null)

function askRestore(backup: Backup) {
  asked.value = backup
  password.value = ''
  failure.value = null
}

async function restore() {
  const backup = asked.value
  if (!backup || !password.value) return
  restoring.value = backup.name
  failure.value = null
  try {
    await engine.restoreBackup(backup.name, password.value)
    // Every page holds data from before: start again from the restored database.
    window.location.reload()
  } catch (error) {
    failure.value = engineErrorMessage(error)
    restoring.value = null
  }
}

const KIND_LABELS: Record<Backup['kind'], string | null> = {
  daily: null,
  manual: 'manuelle',
  'before-restore': 'avant restauration',
}
</script>

<template>
  <UCard id="sauvegardes" :ui="{ body: 'space-y-4 sm:p-5' }">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="font-semibold text-highlighted">Sauvegardes</h2>
        <p class="mt-1 text-sm text-dimmed">
          Une copie de la base chaque jour où Mekiki est ouvert, les 30 dernières gardées, plus vos
          copies manuelles. Les photos des cartes restent dans leur propre dossier.
        </p>
      </div>
      <UButton
        icon="i-lucide-hard-drive-download"
        label="Sauvegarder maintenant"
        variant="soft"
        :loading="creating"
        @click="backupNow"
      />
    </div>

    <UAlert
      v-if="state?.last_error"
      color="error"
      variant="subtle"
      icon="i-lucide-circle-alert"
      :title="state.last_error"
    />

    <p v-if="state && !state.backups.length" class="text-sm text-muted">
      Aucune sauvegarde pour l’instant : la première est faite dans la minute qui suit l’ouverture
      de Mekiki.
    </p>
    <ul v-else-if="state" class="divide-y divide-default rounded-lg border border-default">
      <li
        v-for="(backup, index) in shown"
        :key="backup.name"
        class="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm"
      >
        <UIcon name="i-lucide-database" class="size-4 shrink-0 text-dimmed" />
        <span class="flex-1 text-highlighted">
          {{ formatDateTime(backup.created_at) }}
          <UBadge
            v-if="index === 0"
            label="la plus récente"
            variant="soft"
            color="neutral"
            size="sm"
            class="ms-2"
          />
          <UBadge
            v-if="KIND_LABELS[backup.kind]"
            :label="KIND_LABELS[backup.kind]!"
            variant="outline"
            color="neutral"
            size="sm"
            class="ms-2"
          />
        </span>
        <span class="text-xs text-dimmed tabular-nums">{{ size(backup.size_bytes) }}</span>
        <UButton
          v-if="state.restore_allowed"
          size="sm"
          color="neutral"
          variant="outline"
          icon="i-lucide-history"
          label="Restaurer"
          :loading="restoring === backup.name"
          :disabled="restoring !== null && restoring !== backup.name"
          @click="askRestore(backup)"
        />
      </li>
    </ul>
    <UButton
      v-if="(state?.backups.length ?? 0) > SHOWN"
      size="sm"
      color="neutral"
      variant="ghost"
      :label="showAll ? 'Voir moins' : `Voir les ${state?.backups.length} sauvegardes`"
      @click="showAll = !showAll"
    />
    <p v-if="state" class="text-xs break-all text-dimmed">Dossier : {{ state.folder }}</p>

    <UModal
      :open="asked !== null"
      :title="asked ? `Revenir au ${formatDateTime(asked.created_at)} ?` : ''"
      description="Toutes les données de ce PC, de tous les comptes, reviennent à cet état : lots, stock, ventes et paramètres. Mekiki sauvegarde d’abord l’état actuel, pour pouvoir annuler."
      @update:open="(open) => !open && !restoring && (asked = null)"
    >
      <template #body>
        <form class="space-y-3" @submit.prevent="restore">
          <UFormField
            label="Votre mot de passe"
            help="Seul le premier compte créé sur ce PC peut restaurer une sauvegarde."
          >
            <UInput
              v-model="password"
              type="password"
              autocomplete="current-password"
              autofocus
              class="w-full"
            />
          </UFormField>
          <UAlert
            v-if="failure"
            color="error"
            variant="subtle"
            icon="i-lucide-circle-alert"
            :title="failure"
          />
          <div class="flex justify-end gap-2">
            <UButton
              color="neutral"
              variant="ghost"
              label="Garder l’état actuel"
              :disabled="restoring !== null"
              @click="asked = null"
            />
            <UButton
              type="submit"
              color="error"
              icon="i-lucide-history"
              label="Restaurer"
              :loading="restoring !== null"
              :disabled="!password"
            />
          </div>
        </form>
      </template>
    </UModal>
  </UCard>
</template>
