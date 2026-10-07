<script setup lang="ts">
import type { ButtonProps, PageFeatureProps } from '@nuxt/ui'

definePageMeta({ layout: 'public' })

// Built and signed by the release workflow (.github/workflows/release.yml).
const INSTALLER_URL =
  'https://github.com/antoine-gourgue/Mekiki/releases/latest/download/Mekiki-Setup.exe'

// Inside the desktop app, offering to download it makes no sense.
const inDesktopApp = import.meta.client && '__TAURI_INTERNALS__' in window

const links = computed<ButtonProps[]>(() => [
  ...(inDesktopApp
    ? []
    : [
        {
          label: 'Télécharger pour Windows',
          icon: 'i-lucide-download',
          to: INSTALLER_URL,
          external: true,
          size: 'xl' as const,
        },
      ]),
  {
    label: 'Créer un compte',
    to: '/inscription',
    size: 'xl',
    trailingIcon: 'i-lucide-arrow-right',
    ...(inDesktopApp ? {} : { color: 'neutral' as const, variant: 'subtle' as const }),
  },
  { label: 'Se connecter', to: '/connexion', size: 'xl', color: 'neutral', variant: 'subtle' },
])

const features: PageFeatureProps[] = [
  {
    icon: 'i-lucide-wand-sparkles',
    title: 'Des cartes proposées pour votre budget',
    description:
      'Choisissez le jeu, le budget du colis et le nombre de cartes : Mekiki parcourt des milliers d’annonces Mercari et Rakuma et compose le colis le plus rentable.',
  },
  {
    icon: 'i-lucide-sparkles',
    title: 'Les bonnes affaires dès qu’elles paraissent',
    description:
      'Suivez les cartes qui vous intéressent : le scanner signale les annonces sous la cote Cardmarket.',
  },
  {
    icon: 'i-lucide-calculator',
    title: 'Le coût réel, carte par carte',
    description:
      'Prix, frais Neokyo, envoi, TVA et droits de douane répartis sur chaque carte du colis, au centime près.',
  },
  {
    icon: 'i-lucide-shopping-basket',
    title: 'Un panier pour préparer le colis',
    description:
      'Mettez des annonces en favori et voyez le coût du colis, la revente attendue, la marge et le ROI avant d’acheter.',
  },
  {
    icon: 'i-lucide-layers',
    title: 'Stock et ventes suivis',
    description:
      'Chaque carte achetée garde son coût de revient, chaque vente sa marge nette après commissions et frais d’envoi.',
  },
  {
    icon: 'i-lucide-shield-check',
    title: 'Votre compte, vos données',
    description:
      'Lots, favoris et paramètres ne sont visibles que par vous. Mekiki ne se connecte jamais à vos comptes vendeurs.',
  },
]
</script>

<template>
  <div>
    <UPageHero
      headline="Pokémon et One Piece · du Japon à l’Europe"
      title="Achetez au Japon, revendez en Europe, en connaissant votre vraie marge"
      description="Mekiki compare chaque annonce japonaise à la cote Cardmarket et calcule ce qu’elle vous coûtera vraiment une fois arrivée chez vous."
      :links="links"
    />

    <UPageSection
      title="Tout pour monter un colis rentable"
      description="De la recherche des annonces à la vente, chaque étape au même endroit."
      :features="features"
    />

    <UPageSection>
      <UPageCTA
        title="Prêt pour votre prochain colis ?"
        description="Créez votre compte en une minute. L’achat reste toujours manuel : Mekiki propose, vous décidez."
        variant="subtle"
        :links="[
          { label: 'Créer un compte', to: '/inscription', trailingIcon: 'i-lucide-arrow-right' },
        ]"
      />
    </UPageSection>
  </div>
</template>
