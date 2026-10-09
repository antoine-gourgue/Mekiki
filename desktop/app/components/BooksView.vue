<script setup lang="ts">
import type { BooksPeriod, BooksSummary } from '~/types/engine'

/** One year of the books: periods to declare, thresholds, registers to download. */
const props = defineProps<{ summary: BooksSummary }>()

const engine = useEngine()
const showError = useErrorToast()

const STATES: Record<
  BooksPeriod['state'],
  { label: string; color: 'neutral' | 'warning' | 'success' }
> = {
  upcoming: { label: 'En cours', color: 'neutral' },
  due: { label: 'À déclarer', color: 'warning' },
  past: { label: 'Échéance passée', color: 'success' },
}

const URSSAF_ACTIONS = [
  {
    label: 'Déclarer sur autoentrepreneur.urssaf.fr',
    icon: 'i-lucide-arrow-up-right',
    onClick: () => openExternal('https://www.autoentrepreneur.urssaf.fr'),
  },
]

const MATCH_ACTIONS = [{ label: 'Rapprocher les ventes', icon: 'i-lucide-link', to: '/ventes' }]

function salesToMatch(count: number) {
  return `${count} vente${count > 1 ? 's' : ''} eBay à rapprocher`
}

function share(part: number, whole: number) {
  return whole > 0 ? Math.min(part / whole, 1) : 0
}

const downloading = ref<'receipts' | 'purchases' | null>(null)
const FILE_NAMES = { receipts: 'livre-des-recettes', purchases: 'registre-des-achats' } as const

async function download(book: 'receipts' | 'purchases') {
  downloading.value = book
  try {
    const csv = await engine.booksCsv(book, props.summary.year)
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    link.download = `${FILE_NAMES[book]}-${props.summary.year}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
  } catch (failure) {
    showError(failure)
  } finally {
    downloading.value = null
  }
}
</script>

<template>
  <div class="space-y-4">
    <UAlert
      v-if="summary.unmatched_count"
      color="error"
      variant="subtle"
      icon="i-lucide-triangle-alert"
      :title="`${salesToMatch(summary.unmatched_count)} avant de déclarer`"
      :description="`${formatCents(summary.unmatched_cents)} de ventes lues dans le rapport eBay n’ont pas encore leur carte : elles manquent au chiffre d’affaires ci-dessous tant qu’elles ne sont pas rapprochées.`"
      :actions="MATCH_ACTIONS"
    />

    <UAlert
      v-if="summary.next_declaration"
      color="warning"
      variant="subtle"
      icon="i-lucide-calendar-clock"
      :title="`À déclarer avant le ${formatDate(summary.next_declaration.due_on)} : ${summary.next_declaration.label}`"
      :description="`Chiffre d’affaires ${formatCents(summary.next_declaration.turnover_cents)}, cotisations estimées ${formatCents(summary.next_declaration.contributions_cents + summary.next_declaration.income_tax_cents)}.`"
      :actions="URSSAF_ACTIONS"
    />

    <div class="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
      <StatTile
        label="Chiffre d’affaires"
        :value="formatCents(summary.turnover_cents)"
        :hint="`ventes et port facturé, ${summary.year}`"
      />
      <StatTile
        label="Cotisations estimées"
        :value="formatCents(summary.contributions_cents + summary.income_tax_cents)"
        :hint="
          summary.income_tax_cents
            ? `dont ${formatCents(summary.income_tax_cents)} de versement libératoire`
            : 'cotisations sociales URSSAF'
        "
      />
      <UCard :ui="{ body: 'px-5 py-4 sm:px-5 sm:py-4 space-y-2' }">
        <p class="text-sm text-muted">Plafond de la micro-entreprise</p>
        <UProgress
          :model-value="share(summary.turnover_cents, summary.turnover_limit_cents) * 100"
          size="sm"
        />
        <p class="text-xs text-dimmed tabular-nums">
          {{ formatRatio(share(summary.turnover_cents, summary.turnover_limit_cents)) }} de
          {{ formatCents(summary.turnover_limit_cents) }}
        </p>
      </UCard>
      <UCard :ui="{ body: 'px-5 py-4 sm:px-5 sm:py-4 space-y-2' }">
        <p class="text-sm text-muted">Franchise de TVA</p>
        <UProgress
          :model-value="share(summary.turnover_cents, summary.vat_franchise_limit_cents) * 100"
          size="sm"
          :color="
            share(summary.turnover_cents, summary.vat_franchise_limit_cents) >= 0.8
              ? 'warning'
              : 'primary'
          "
        />
        <p class="text-xs text-dimmed tabular-nums">
          {{ formatRatio(share(summary.turnover_cents, summary.vat_franchise_limit_cents)) }}
          de {{ formatCents(summary.vat_franchise_limit_cents) }}
        </p>
      </UCard>
    </div>

    <UCard :ui="{ body: 'p-0 sm:p-0' }">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-xs text-dimmed">
            <th class="px-4 pt-3 pb-2 font-medium">
              {{ summary.declaration === 'monthly' ? 'Mois' : 'Trimestre' }}
            </th>
            <th class="px-2 pt-3 pb-2 text-right font-medium">Chiffre d’affaires</th>
            <th class="px-2 pt-3 pb-2 text-right font-medium">Cotisations</th>
            <th class="px-2 pt-3 pb-2 font-medium">À déclarer avant</th>
            <th class="px-4 pt-3 pb-2 text-right font-medium">État</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!summary.periods.length" class="border-t border-muted">
            <td colspan="5" class="px-4 py-2.5 text-muted">
              Rien à déclarer : votre activité a commencé après {{ summary.year }}.
            </td>
          </tr>
          <tr v-for="period in summary.periods" :key="period.start" class="border-t border-muted">
            <td class="px-4 py-2.5 font-medium text-highlighted">{{ period.label }}</td>
            <td class="px-2 py-2.5 text-right tabular-nums">
              {{ formatCents(period.turnover_cents) }}
              <span v-if="period.unmatched_count" class="block text-xs text-error">
                + {{ formatCents(period.unmatched_cents) }} à rapprocher
              </span>
            </td>
            <td class="px-2 py-2.5 text-right tabular-nums">
              {{ formatCents(period.contributions_cents + period.income_tax_cents) }}
            </td>
            <td class="px-2 py-2.5 text-muted">{{ formatDate(period.due_on) }}</td>
            <td class="px-4 py-2.5 text-right">
              <UBadge
                :label="STATES[period.state].label"
                :color="STATES[period.state].color"
                variant="soft"
              />
            </td>
          </tr>
        </tbody>
      </table>
    </UCard>

    <UCard :ui="{ body: 'space-y-3 sm:p-5' }">
      <div>
        <h2 class="font-semibold text-highlighted">Registres obligatoires</h2>
        <p class="mt-1 text-sm text-dimmed">
          Le livre des recettes et le registre des achats de {{ summary.year }}, pour Excel. La date
          de vente sert de date d’encaissement. Les achats datent chaque carte du jour de sa
          commande, l’envoi international et les taxes d’import de chaque lot du jour où ils sont
          payés ; une TVA d’import encore estimée y est signalée.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <UButton
          icon="i-lucide-file-spreadsheet"
          label="Livre des recettes"
          variant="soft"
          :loading="downloading === 'receipts'"
          @click="download('receipts')"
        />
        <UButton
          icon="i-lucide-file-spreadsheet"
          label="Registre des achats"
          variant="soft"
          :loading="downloading === 'purchases'"
          @click="download('purchases')"
        />
      </div>
    </UCard>

    <p class="text-xs text-dimmed">
      Estimations à partir de vos ventes enregistrées et de vos taux dans Paramètres › Entreprise et
      Revente. Mekiki ne déclare rien à votre place : vérifiez les montants avant de les reporter
      sur votre espace URSSAF.
    </p>
  </div>
</template>
