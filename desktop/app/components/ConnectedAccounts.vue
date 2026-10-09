<script setup lang="ts">
import type { BrowserSite, BrowserStatus } from '~/types/engine'

/**
 * Vinted and eBay accounts, signed in inside Mekiki's own Chrome window: Mekiki reads eBay's
 * sales and publishes listings there, and never sees a password.
 */
const engine = useEngine()
const showError = useErrorToast()

const SITES: { site: BrowserSite; label: string; icon: string }[] = [
  { site: 'vinted', label: 'Vinted', icon: 'i-lucide-shirt' },
  { site: 'ebay', label: 'eBay', icon: 'i-lucide-shopping-bag' },
]

const status = ref<BrowserStatus | null>(null)
const { access: ebayAccess } = useEbaySoldAccess()
const connected = reactive<Partial<Record<BrowserSite, boolean>>>({})
const busy = ref<BrowserSite | null>(null)
// Chrome works out of sight, except while the user signs in.
const windowShown = ref(false)

onMounted(async () => {
  try {
    status.value = await engine.browserStatus()
  } catch (error) {
    showError(error)
  }
})

async function open(site: BrowserSite) {
  busy.value = site
  try {
    status.value = await engine.openSite(site)
    windowShown.value = true
  } catch (error) {
    showError(error, 'Chrome n’a pas pu s’ouvrir')
  } finally {
    busy.value = null
  }
}

async function check(site: BrowserSite) {
  busy.value = site
  try {
    connected[site] = (await engine.checkSite(site)).connected
    if (connected[site]) windowShown.value = false
    // Card panels enable their eBay reading from this.
    if (site === 'ebay' && ebayAccess.value) {
      ebayAccess.value = { ...ebayAccess.value, signedIn: connected[site] ?? null }
    }
  } catch (error) {
    showError(error, 'Vérification impossible')
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <UCard>
    <template #header>
      <h2 class="font-medium text-highlighted">Comptes Vinted et eBay</h2>
      <p class="text-sm text-muted">
        Mekiki ouvre sa propre fenêtre Chrome : connectez-vous-y une fois, il y lit les ventes eBay
        et y publie vos annonces. Votre mot de passe reste entre vous et le site.
      </p>
    </template>

    <UAlert
      v-if="status && !status.chrome_installed"
      color="warning"
      variant="subtle"
      icon="i-lucide-triangle-alert"
      title="Google Chrome n’est pas installé"
      description="Installez Chrome pour lire les ventes eBay et publier sur Vinted et eBay depuis Mekiki."
    />

    <UAlert
      v-if="status?.running && windowShown"
      color="info"
      variant="subtle"
      icon="i-lucide-app-window"
      title="La fenêtre Chrome de Mekiki est ouverte"
      description="Connectez-vous au site dans cette fenêtre, puis cliquez sur « Vérifier » : elle repassera en arrière-plan."
      class="mb-3"
    />
    <ul v-if="!status || status.chrome_installed" class="divide-y divide-default">
      <li v-for="entry in SITES" :key="entry.site" class="flex items-center gap-3 py-3">
        <UIcon :name="entry.icon" class="size-5 shrink-0 text-muted" />
        <div class="min-w-0 flex-1">
          <p class="font-medium">{{ entry.label }}</p>
          <p class="text-xs text-muted">
            <template v-if="connected[entry.site] === true">Connecté dans Chrome</template>
            <template v-else-if="connected[entry.site] === false">
              Pas connecté : cliquez sur « Se connecter », connectez-vous dans la fenêtre Chrome,
              puis sur « Vérifier ».
            </template>
            <template v-else>État inconnu : cliquez sur « Vérifier ».</template>
          </p>
        </div>
        <UBadge
          v-if="connected[entry.site] !== undefined"
          :color="connected[entry.site] ? 'success' : 'neutral'"
          variant="subtle"
          :label="connected[entry.site] ? 'Connecté' : 'Déconnecté'"
        />
        <UButton
          label="Se connecter"
          icon="i-lucide-log-in"
          color="neutral"
          variant="subtle"
          size="sm"
          :loading="busy === entry.site"
          :disabled="busy !== null"
          @click="open(entry.site)"
        />
        <UButton
          label="Vérifier"
          color="neutral"
          variant="ghost"
          size="sm"
          :disabled="busy !== null"
          @click="check(entry.site)"
        />
      </li>
    </ul>
  </UCard>
</template>
