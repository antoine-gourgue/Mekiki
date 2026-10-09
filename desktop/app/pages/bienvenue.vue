<script setup lang="ts">
import type { StepperItem } from '@nuxt/ui'
import type { AppSettings } from '~/types/engine'

/**
 * The guided setup a new account goes through, and anyone can run again from Paramètres:
 * each step shows the settings it needs and why, saved on "Suivant"; "Terminer" marks the
 * account as set up, which ends the matching task.
 */
const engine = useEngine()
const auth = useAuth()
const showError = useErrorToast()
const toast = useToast()
const { refresh: refreshTasks, setMuted } = useTasks()

const STEPS = [
  { value: 'bienvenue', title: 'Bienvenue', icon: 'i-lucide-hand' },
  { value: 'entreprise', title: 'Entreprise', icon: 'i-lucide-landmark' },
  { value: 'achat', title: 'Achat', icon: 'i-lucide-plane' },
  { value: 'revente', title: 'Revente', icon: 'i-lucide-receipt-euro' },
  { value: 'ebay', title: 'eBay', icon: 'i-lucide-shopping-bag' },
  { value: 'chrome', title: 'Chrome', icon: 'i-lucide-app-window' },
  { value: 'affaires', title: 'Bonnes affaires', icon: 'i-lucide-tag' },
  { value: 'pret', title: 'C’est prêt', icon: 'i-lucide-rocket' },
] satisfies StepperItem[]

const SUMMARIES: Record<string, string> = {
  entreprise: 'Nom, SIRET et rythme des déclarations URSSAF, pour la comptabilité.',
  achat: 'Taux de change, frais Neokyo, TVA et frais de dossier à l’import.',
  revente: 'Cotisations, emballage et commission de chaque plateforme.',
  ebay: 'Vos clés d’application eBay, pour les prix eBay en direct (facultatif).',
  chrome: 'Vos comptes eBay et Vinted, pour lire les ventes et publier.',
  affaires: 'Le ROI visé et les sites que Mekiki surveille pour vous.',
}

const step = ref<string>('bienvenue')
const index = computed(() => STEPS.findIndex((each) => each.value === step.value))

const settings = ref<AppSettings | null>(null)
const saved = ref('')
const loadFailure = ref<unknown>(null)

async function load() {
  loadFailure.value = null
  try {
    settings.value = await engine.getSettings()
    saved.value = JSON.stringify(settings.value)
  } catch (failure) {
    loadFailure.value = failure
  }
}
onMounted(load)

const saving = ref(false)

/** Saves what changed; `done` marks the setup finished. */
async function save(done = false): Promise<boolean> {
  if (!settings.value) return false
  const next = { ...settings.value, onboarded: done || settings.value.onboarded }
  if (JSON.stringify(next) === saved.value) return true
  saving.value = true
  try {
    settings.value = await engine.saveSettings(next)
    saved.value = JSON.stringify(settings.value)
    // Paramètres keeps its own copy: it must not show the values from before.
    clearNuxtData('settings')
    return true
  } catch (failure) {
    showError(failure)
    return false
  } finally {
    saving.value = false
  }
}

async function move(offset: number) {
  const target = STEPS[index.value + offset]
  if (target && (await save())) step.value = target.value
}

async function finish(to = '/') {
  if (!(await save(true))) return
  await refreshTasks()
  toast.add({
    title: 'Mekiki est prêt',
    description: 'Tout reste modifiable dans Paramètres.',
    color: 'success',
  })
  await navigateTo(to)
}

// "Plus tard" keeps what was entered; the task in "À faire" leads back here.
async function later() {
  if (await save()) await navigateTo('/')
}

// Windows notifications exist in the installed app only.
const inApp = ref(false)
const notifications = ref<'granted' | 'denied' | 'unknown'>('unknown')
onMounted(async () => {
  inApp.value = '__TAURI_INTERNALS__' in window
  if (!inApp.value) return
  const { isPermissionGranted } = await import('@tauri-apps/plugin-notification')
  if (await isPermissionGranted()) notifications.value = 'granted'
})

async function enableNotifications() {
  const { requestPermission, sendNotification } = await import('@tauri-apps/plugin-notification')
  notifications.value = (await requestPermission()) === 'granted' ? 'granted' : 'denied'
  if (notifications.value !== 'granted') return
  setMuted(false)
  sendNotification({
    title: 'Notifications activées',
    body: 'Mekiki vous préviendra des bonnes affaires et des ventes à expédier.',
  })
}

const START = [
  {
    to: '/suivi',
    icon: 'i-lucide-eye',
    label: 'Suivre une carte',
    text: 'Mekiki guette ses annonces au Japon.',
  },
  {
    to: '/decouverte',
    icon: 'i-lucide-wand-sparkles',
    label: 'Trouver des cartes',
    text: 'Un colis proposé selon votre budget.',
  },
  {
    to: '/lots',
    icon: 'i-lucide-package',
    label: 'Saisir un lot',
    text: 'Un colis déjà acheté, carte par carte.',
  },
]
</script>

<template>
  <UDashboardPanel id="welcome">
    <template #header>
      <PageNavbar
        title="Configuration de Mekiki"
        description="Quelques minutes, pas à pas : tout reste modifiable dans Paramètres."
      >
        <template #right>
          <UButton
            label="Plus tard"
            color="neutral"
            variant="ghost"
            :disabled="saving"
            @click="later"
          />
        </template>
      </PageNavbar>
    </template>

    <template #body>
      <UAlert
        v-if="loadFailure"
        color="error"
        variant="subtle"
        title="Impossible de charger les paramètres"
        :description="engineErrorMessage(loadFailure)"
        :actions="[{ label: 'Réessayer', onClick: () => load() }]"
      />

      <div v-else-if="settings" class="mx-auto w-full max-w-3xl space-y-6 pb-6">
        <UStepper v-model="step" :items="STEPS" :linear="false" size="sm" class="w-full" />

        <section v-if="step === 'bienvenue'" class="space-y-5">
          <div class="space-y-2">
            <h2 class="text-2xl font-semibold text-highlighted">
              Bienvenue{{ auth.user.value ? `, ${auth.user.value.display_name}` : '' }}
            </h2>
            <p class="text-muted">
              Mekiki chiffre chaque carte japonaise comme une carte de votre prochain colis : prix
              d’achat, frais Neokyo, port, TVA à l’import, frais de la plateforme de revente et
              cotisations URSSAF. Pour que ses calculs soient les vôtres, réglons ensemble ce qui
              change d’un revendeur à l’autre.
            </p>
          </div>
          <ul class="grid gap-3 sm:grid-cols-2">
            <li
              v-for="each in STEPS.slice(1, -1)"
              :key="each.value"
              class="flex gap-3 rounded-lg border border-default p-3"
            >
              <UIcon :name="each.icon" class="mt-0.5 size-5 shrink-0 text-primary" />
              <span>
                <span class="block text-sm font-medium text-highlighted">{{ each.title }}</span>
                <span class="block text-sm text-muted">{{ SUMMARIES[each.value] }}</span>
              </span>
            </li>
          </ul>
        </section>

        <section v-else-if="step === 'entreprise'" class="space-y-4">
          <p class="text-muted">
            Mekiki tient le livre des recettes et le registre des achats de votre micro-entreprise,
            et vous rappelle chaque déclaration de chiffre d’affaires à l’URSSAF. Pas encore
            immatriculé ? Laissez le SIRET vide et revenez-y plus tard.
          </p>
          <BusinessCard v-model="settings.business" />
        </section>

        <section v-else-if="step === 'achat'" class="space-y-4">
          <p class="text-muted">
            Chaque nouveau lot reprend ces valeurs ; vous les ajusterez colis par colis avec la
            facture de Neokyo et celle du transporteur. Le taux de change est celui de votre banque
            ou de votre carte : combien de yens pour un euro.
          </p>
          <BuyingSettingsCard v-model="settings" />
          <ImportSettingsCard v-model="settings" />
        </section>

        <section v-else-if="step === 'revente'" class="space-y-4">
          <p class="text-muted">
            Les cotisations URSSAF se calculent sur le chiffre d’affaires, le versement libératoire
            seulement si vous l’avez choisi. Chaque vente reprend la commission de sa plateforme :
            vérifiez celles de Cardmarket et d’eBay pour votre compte vendeur.
          </p>
          <SellingSettingsCard v-model="settings" />
        </section>

        <section v-else-if="step === 'ebay'" class="space-y-4">
          <p class="text-muted">
            Facultatif, et faisable plus tard dans Paramètres. Avec des clés d’application eBay
            (gratuites, sur le site des développeurs eBay), la fiche d’une carte montre les annonces
            eBay en cours sans passer par Chrome. Vos ventes eBay, elles, s’importent depuis le
            rapport des commandes, dans Ventes.
          </p>
          <EbayKeysCard />
        </section>

        <section v-else-if="step === 'chrome'" class="space-y-4">
          <p class="text-muted">
            Mekiki lit les ventes réussies d’eBay et publie vos annonces sur eBay et Vinted dans sa
            propre fenêtre Chrome, qui travaille hors de l’écran. Connectez-vous-y une fois à chaque
            site : votre mot de passe reste entre vous et le site.
          </p>
          <ConnectedAccounts />
        </section>

        <section v-else-if="step === 'affaires'" class="space-y-4">
          <p class="text-muted">
            Le scanner surveille les cartes que vous suivez sur Mercari et Rakuma, chiffre chaque
            annonce comme une carte d’un colis type et vous signale celles qui atteignent votre ROI
            visé.
          </p>
          <ScannerSettingsCard v-model="settings" />
        </section>

        <section v-else class="space-y-5">
          <div class="space-y-2">
            <h2 class="text-2xl font-semibold text-highlighted">Mekiki est prêt</h2>
            <p class="text-muted">Encore deux choses, puis choisissez par où commencer.</p>
          </div>

          <div class="grid gap-3 sm:grid-cols-2">
            <div class="space-y-2 rounded-lg border border-default p-4">
              <p class="flex items-center gap-2 font-medium text-highlighted">
                <UIcon name="i-lucide-bell" class="size-5 text-primary" />
                Notifications
              </p>
              <p class="text-sm text-muted">
                Une notification Windows pour chaque bonne affaire, vente à expédier ou déclaration
                qui approche. Elles se coupent depuis la page « À faire ».
              </p>
              <p v-if="!inApp" class="text-sm text-dimmed">Disponibles dans l’application.</p>
              <p
                v-else-if="notifications === 'granted'"
                class="flex items-center gap-1.5 text-sm text-success"
              >
                <UIcon name="i-lucide-circle-check" class="size-4" />
                Notifications activées
              </p>
              <template v-else>
                <UButton
                  size="sm"
                  icon="i-lucide-bell-ring"
                  label="Activer les notifications"
                  @click="enableNotifications"
                />
                <p v-if="notifications === 'denied'" class="text-sm text-dimmed">
                  Refusées : Paramètres Windows › Système › Notifications pour les autoriser.
                </p>
              </template>
            </div>

            <div class="space-y-2 rounded-lg border border-default p-4">
              <p class="flex items-center gap-2 font-medium text-highlighted">
                <UIcon name="i-lucide-hard-drive-download" class="size-5 text-primary" />
                Sauvegardes
              </p>
              <p class="text-sm text-muted">
                Mekiki copie sa base chaque jour où il est ouvert et garde les 30 dernières copies.
                Paramètres › Sauvegardes pour en faire une ou en restaurer une.
              </p>
            </div>
          </div>

          <div class="grid gap-3 sm:grid-cols-3">
            <button
              v-for="each in START"
              :key="each.to"
              type="button"
              class="flex flex-col gap-1.5 rounded-lg border border-default p-4 text-left transition-colors hover:bg-elevated/50"
              :disabled="saving"
              @click="finish(each.to)"
            >
              <UIcon :name="each.icon" class="size-5 text-primary" />
              <span class="font-medium text-highlighted">{{ each.label }}</span>
              <span class="text-sm text-muted">{{ each.text }}</span>
            </button>
          </div>
        </section>

        <div class="flex items-center justify-between gap-2 border-t border-default pt-4">
          <UButton
            v-if="index > 0"
            label="Précédent"
            icon="i-lucide-arrow-left"
            color="neutral"
            variant="ghost"
            :disabled="saving"
            @click="move(-1)"
          />
          <span v-else />
          <UButton
            v-if="step !== 'pret'"
            :label="index === 0 ? 'Commencer' : 'Suivant'"
            trailing-icon="i-lucide-arrow-right"
            :loading="saving"
            @click="move(1)"
          />
          <UButton
            v-else
            label="Aller au tableau de bord"
            icon="i-lucide-check"
            :loading="saving"
            @click="finish()"
          />
        </div>
      </div>
    </template>
  </UDashboardPanel>
</template>
