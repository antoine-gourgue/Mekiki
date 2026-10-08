<script setup lang="ts">
definePageMeta({ layout: 'public' })

// Built and signed by the release workflow (.github/workflows/release.yml).
const INSTALLER_URL =
  'https://github.com/antoine-gourgue/Mekiki/releases/latest/download/Mekiki-Setup.exe'

// Inside the desktop app, offering to download it makes no sense.
const inDesktopApp = import.meta.client && '__TAURI_INTERNALS__' in window

const steps = [
  {
    title: 'Fixez un budget',
    text: 'Le jeu, le budget du colis, le nombre de cartes et la profondeur de recherche.',
  },
  {
    title: 'Mekiki compose le colis',
    text: 'Chaque annonce chiffrée au centime : frais Neokyo, envoi, TVA, douane, puis revente nette.',
  },
  {
    title: 'Vous achetez, il revend',
    text: 'Achat sur Neokyo d’un clic, puis annonces préparées pour Vinted et eBay depuis l’app.',
  },
]

const tools = [
  {
    title: 'Recherche en japonais',
    text: 'Tapez « Dracaufeu ex » : Mekiki cherche « リザードンex » sur Mercari et Rakuma.',
  },
  {
    title: 'Cartes suivies, à l’impression près',
    text: 'Le scanner ne garde que la bonne version : miroir, parallèle, manga.',
  },
  {
    title: 'Le vrai coût de revient',
    text: 'Prix, frais, envoi, TVA et douane répartis carte par carte.',
  },
  {
    title: 'Stock, ventes et marges',
    text: 'Chaque vente garde sa marge nette après commissions et cotisations.',
  },
]

const publishSteps = [
  { label: 'Photos, titre et description', state: 'fait' },
  { label: 'Catégorie, marque et état', state: 'fait' },
  { label: 'Prix et publication', state: 'en cours' },
]
</script>

<template>
  <div>
    <section
      id="top"
      class="mx-auto flex max-w-6xl flex-wrap items-center gap-14 px-4 pt-16 pb-24 sm:px-6"
    >
      <div class="min-w-0 flex-[1_1_480px] space-y-7">
        <span
          class="inline-flex items-center gap-2 rounded-full border border-default px-3 py-1.5 text-sm text-muted"
        >
          <span class="size-1.5 rounded-full bg-success" />
          Pokémon et One Piece · du Japon à l’Europe
        </span>
        <h1
          class="text-5xl/[1.04] font-semibold tracking-tight text-highlighted sm:text-6xl/[1.02]"
        >
          Achetez au Japon.<br />
          Revendez en Europe.<br />
          <span class="text-primary">Sachez avant d’acheter.</span>
        </h1>
        <p class="max-w-xl text-lg/relaxed text-muted">
          Mekiki lit des milliers d’annonces Mercari et Rakuma, reconnaît chaque carte japonaise, la
          compare à ce qui se vend vraiment sur Cardmarket, Vinted et eBay, et vous dit combien
          payer au plus.
        </p>
        <div class="flex flex-wrap gap-3">
          <UButton
            v-if="!inDesktopApp"
            :to="INSTALLER_URL"
            external
            size="xl"
            icon="i-lucide-download"
            label="Télécharger pour Windows"
          />
          <UButton
            to="/inscription"
            size="xl"
            :color="inDesktopApp ? 'primary' : 'neutral'"
            :variant="inDesktopApp ? 'solid' : 'outline'"
            label="Créer un compte"
            trailing-icon="i-lucide-arrow-right"
          />
        </div>
        <p class="text-sm text-dimmed">
          Windows 10 et 11 · mises à jour automatiques · l’achat reste toujours manuel
        </p>
      </div>

      <figure class="min-w-0 flex-[1_1_420px]">
        <div
          class="space-y-4 rounded-2xl border border-default bg-muted p-5 shadow-2xl shadow-black/40"
        >
          <div class="flex items-center gap-4">
            <div
              class="flex h-[88px] w-16 shrink-0 items-center justify-center rounded-md bg-accented"
            >
              <UIcon name="i-lucide-image" class="size-5 text-dimmed" />
            </div>
            <div class="min-w-0">
              <p class="text-xs text-dimmed">Mercari · SV2a 201/165 · SAR</p>
              <p class="mt-1 text-xl font-semibold text-highlighted">Dracaufeu ex</p>
              <p class="mt-1 text-muted tabular-nums">28 000 ¥ · port compris</p>
            </div>
          </div>
          <div class="flex gap-3 rounded-xl border border-success/35 bg-success/10 p-4">
            <UIcon name="i-lucide-check" class="mt-0.5 size-5 shrink-0 text-success" />
            <div>
              <p class="font-semibold text-success">Bonne affaire sur Vinted</p>
              <p class="mt-1 text-sm text-muted">
                Revente comparée à 19 annonces · objectif ROI 30 %
              </p>
            </div>
          </div>
          <div class="grid grid-cols-3 gap-2.5">
            <div class="rounded-lg bg-elevated p-3">
              <p class="text-xs text-muted">Vinted</p>
              <p class="mt-1 text-lg font-semibold tabular-nums">414 €</p>
              <p class="text-[11px] text-dimmed">médiane</p>
            </div>
            <div class="rounded-lg bg-elevated p-3">
              <p class="text-xs text-muted">Cardmarket</p>
              <p class="mt-1 text-lg font-semibold tabular-nums">358 €</p>
              <p class="text-[11px] text-dimmed">moyenne 30 jours</p>
            </div>
            <div class="rounded-lg bg-elevated p-3">
              <p class="text-xs text-muted">eBay vendus</p>
              <p class="mt-1 text-lg font-semibold tabular-nums">355 €</p>
              <p class="text-[11px] text-dimmed">médiane</p>
            </div>
          </div>
          <div class="flex items-center justify-between border-t border-default pt-3.5 text-sm">
            <span class="text-muted">Payer au plus</span>
            <span class="text-base font-semibold text-highlighted tabular-nums">38 606 ¥</span>
          </div>
        </div>
        <figcaption class="mt-3 text-center text-xs text-dimmed">
          Exemple de fiche d’une annonce dans Mekiki
        </figcaption>
      </figure>
    </section>

    <section id="fonctionnement" class="border-y border-default bg-[#121116]">
      <div class="mx-auto max-w-6xl space-y-10 px-4 py-18 sm:px-6">
        <div class="max-w-2xl space-y-3">
          <p class="text-xs font-semibold tracking-[0.16em] text-primary">FONCTIONNEMENT</p>
          <h2 class="text-4xl/tight font-semibold tracking-tight text-highlighted">
            Un colis rentable en trois étapes
          </h2>
        </div>
        <ol class="grid gap-5 md:grid-cols-3">
          <li
            v-for="(step, index) in steps"
            :key="step.title"
            class="space-y-3 rounded-2xl border border-default p-6"
          >
            <span class="font-mono text-sm text-dimmed">0{{ index + 1 }}</span>
            <h3 class="text-xl font-semibold text-highlighted">{{ step.title }}</h3>
            <p class="text-muted">{{ step.text }}</p>
          </li>
        </ol>
      </div>
    </section>

    <section id="outils" class="mx-auto max-w-6xl space-y-10 px-4 py-22 sm:px-6">
      <div class="max-w-2xl space-y-3">
        <p class="text-xs font-semibold tracking-[0.16em] text-primary">OUTILS</p>
        <h2 class="text-4xl/tight font-semibold tracking-tight text-highlighted">
          Tout le métier de revendeur, au même endroit
        </h2>
      </div>
      <div
        class="grid gap-px overflow-hidden rounded-2xl border border-default bg-(--ui-border) md:grid-cols-2"
      >
        <div v-for="tool in tools" :key="tool.title" class="space-y-2.5 bg-default p-7">
          <h3 class="font-semibold text-highlighted">{{ tool.title }}</h3>
          <p class="text-sm/relaxed text-muted">{{ tool.text }}</p>
        </div>
      </div>
    </section>

    <section id="vendre" class="mx-auto max-w-6xl px-4 pb-22 sm:px-6">
      <div
        class="flex flex-wrap items-center gap-10 rounded-3xl border border-default bg-muted p-8 sm:p-12"
      >
        <div class="min-w-0 flex-[1_1_420px] space-y-4">
          <p class="text-xs font-semibold tracking-[0.16em] text-primary">VENTE EN EUROPE</p>
          <h2 class="text-3xl/tight font-semibold tracking-tight text-highlighted">
            Publiez sur Vinted et eBay sans quitter Mekiki
          </h2>
          <p class="text-muted">
            Photos, titre, description et prix préparés pour chaque site. Mekiki remplit le
            formulaire dans sa fenêtre Chrome, vous suivez l’avancée en direct.
          </p>
        </div>
        <ul class="min-w-0 flex-[1_1_340px] space-y-2.5">
          <li
            v-for="step in publishSteps"
            :key="step.label"
            class="flex items-center gap-3 rounded-xl bg-elevated px-4 py-3.5"
            :class="{ 'ring-1 ring-vermilion-500': step.state === 'en cours' }"
          >
            <span
              class="size-2 rounded-full"
              :class="step.state === 'fait' ? 'bg-success' : 'bg-vermilion-500'"
            />
            <span class="flex-1 text-sm">{{ step.label }}</span>
            <span
              class="font-mono text-xs"
              :class="step.state === 'fait' ? 'text-dimmed' : 'text-primary'"
            >
              {{ step.state }}
            </span>
          </li>
        </ul>
      </div>
    </section>

    <section class="border-t border-default">
      <div
        class="mx-auto flex max-w-6xl flex-col items-center gap-5 px-4 py-20 text-center sm:px-6"
      >
        <h2 class="text-4xl font-semibold tracking-tight text-highlighted">
          Prêt pour votre prochain colis ?
        </h2>
        <p class="text-lg text-muted">
          Mekiki propose, vous décidez. L’achat reste toujours manuel.
        </p>
        <div class="mt-2 flex flex-wrap justify-center gap-3">
          <UButton
            v-if="!inDesktopApp"
            :to="INSTALLER_URL"
            external
            size="xl"
            icon="i-lucide-download"
            label="Télécharger pour Windows"
          />
          <UButton
            to="/inscription"
            size="xl"
            :color="inDesktopApp ? 'primary' : 'neutral'"
            :variant="inDesktopApp ? 'solid' : 'outline'"
            label="Créer un compte"
          />
        </div>
      </div>
    </section>
  </div>
</template>
