<script setup lang="ts">
import type { SelectMenuItem } from '@nuxt/ui'
import type { DiscoveryCatalog, DiscoveryDepth, DiscoverySet, Era, Game } from '~/types/engine'
import type { DiscoveryFormState } from '~/utils/discovery'

/**
 * The discovery's search form: the parcel (budget, cards, ROI), the cards wanted (name,
 * eras, sets, rarities, then more filters) and how far to search. Sets and rarities come
 * from the engine's catalog of each game.
 */
const form = defineModel<DiscoveryFormState>({ required: true })
defineProps<{ running: boolean }>()
const emit = defineEmits<{ submit: [] }>()

const engine = useEngine()
const catalogs = reactive<Partial<Record<Game, DiscoveryCatalog>>>({})
const catalog = computed(() => catalogs[form.value.game] ?? null)

async function loadCatalog(game: Game) {
  if (catalogs[game]) return
  try {
    catalogs[game] = await engine.discoveryCatalog(game)
  } catch {
    // Without the catalog, the name and the other filters still work.
  }
}
watch(() => form.value.game, loadCatalog, { immediate: true })

// Eras, sets and rarities belong to one game.
function chooseGame(game: Game) {
  if (game === form.value.game) return
  Object.assign(form.value, { game, eras: [], sets: [], rarities: [], exclude_mirrors: false })
}

const gameItems = selectItems(GAME_LABELS)
const depthItems: { value: DiscoveryDepth; label: string; description: string }[] = [
  { value: 'quick', label: 'Rapide', description: '~1 500 annonces, 1 à 2 min' },
  { value: 'deep', label: 'Approfondie', description: '~5 000 annonces, ~5 min' },
  { value: 'max', label: 'Maximale', description: '10 000+ annonces, ~15 min' },
]

function toggled<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((each) => each !== value) : [...list, value]
}

function sameEras(a: Era[], b: Era[]) {
  return a.length === b.length && a.every((era) => b.includes(era))
}
const eraPresets = [
  { label: 'Toutes', eras: [] as Era[] },
  { label: 'Récentes', hint: 'depuis 2023', eras: RECENT_ERAS },
  { label: 'Anciennes', hint: 'avant 2023', eras: OLDER_ERAS },
]

function setLabel(set: DiscoverySet) {
  return [set.printed, set.name ?? set.japanese_name].filter(Boolean).join(' · ')
}
const setsByCode = computed(
  () => new Map((catalog.value?.sets ?? []).map((set) => [set.code, set] as const)),
)

// Grouped by era, newest first; with eras chosen, only their sets (and those already chosen).
const setItems = computed<SelectMenuItem[] | SelectMenuItem[][]>(() => {
  const current = catalog.value
  if (!current) return []
  const eras = form.value.eras
  const shown = current.sets.filter(
    (set) =>
      !eras.length || !set.era || eras.includes(set.era) || form.value.sets.includes(set.code),
  )
  const item = (set: DiscoverySet) => ({
    label: setLabel(set),
    value: set.code,
    description: set.japanese_name ?? undefined,
  })
  if (!current.eras.length) return shown.map(item)
  return current.eras
    .map((era) => [
      { type: 'label' as const, label: `${era.label} · ${era.years}` },
      ...shown.filter((set) => set.era === era.id).map(item),
    ])
    .filter((group) => group.length > 1)
})

const cardFilterCount = computed(
  () =>
    Number(Boolean(form.value.name.trim())) +
    form.value.eras.length +
    form.value.sets.length +
    form.value.rarities.length,
)
const moreCount = computed(() => moreFilterCount(form.value))
const moreOpen = ref(moreCount.value > 0)

function clearCards() {
  Object.assign(form.value, { name: '', eras: [], sets: [], rarities: [] })
}
function clearMore() {
  Object.assign(form.value, {
    min_market_cents: null,
    max_market_cents: null,
    min_price_jpy: null,
    max_price_jpy: null,
    min_condition: 'all',
    max_age_days: null,
    exclude_mirrors: false,
    confident_only: false,
  })
}

// What the search will look for, in a line above the button.
const summary = computed(() => {
  const current = form.value
  const rarities = new Map((catalog.value?.rarities ?? []).map((r) => [r.id, r.label] as const))
  const eras = new Map((catalog.value?.eras ?? []).map((e) => [e.id, e.label] as const))
  const parts = [
    current.name.trim() ? `« ${current.name.trim()} »` : null,
    current.sets.length
      ? current.sets.map((code) => setsByCode.value.get(code)?.printed ?? code).join(', ')
      : current.eras.map((era) => eras.get(era) ?? era).join(', ') || null,
    current.rarities.map((id) => rarities.get(id) ?? id).join(', ') || null,
    moreCount.value
      ? `${moreCount.value} autre${moreCount.value > 1 ? 's' : ''} filtre${moreCount.value > 1 ? 's' : ''}`
      : null,
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : 'Toutes les cartes rentables'
})

const CHIP =
  'inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-[13px] font-medium transition-colors'
function chipClass(on: boolean) {
  return on
    ? 'border-primary/60 bg-primary/10 text-highlighted'
    : 'border-default text-muted hover:border-accented hover:text-highlighted'
}
</script>

<template>
  <UCard :ui="{ body: 'p-0 sm:p-0' }">
    <form @submit.prevent="emit('submit')">
      <section class="grid gap-4 p-4 sm:grid-cols-2 sm:p-5 xl:grid-cols-4">
        <UFormField label="Jeu">
          <SegmentedControl
            :model-value="form.game"
            :items="gameItems"
            label="Jeu"
            class="flex w-full *:flex-1"
            @update:model-value="chooseGame"
          />
        </UFormField>
        <UFormField label="Budget du colis" hint="tout compris">
          <MoneyInput v-model="form.budget_cents" currency="EUR" />
        </UFormField>
        <UFormField label="Nombre de cartes">
          <UInputNumber v-model="form.card_count" :min="1" :max="50" class="w-full" />
        </UFormField>
        <UFormField label="ROI minimum">
          <PercentInput v-model="form.min_roi_percent" :max="1000" />
        </UFormField>
      </section>

      <section class="space-y-4 border-t border-default p-4 sm:p-5">
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 class="text-sm font-semibold text-highlighted">Cartes recherchées</h3>
            <p class="mt-0.5 text-xs text-dimmed">
              Sans filtre, Mekiki garde toutes les cartes rentables qu’il reconnaît.
            </p>
          </div>
          <UButton
            v-if="cardFilterCount"
            color="neutral"
            variant="ghost"
            size="sm"
            icon="i-lucide-x"
            label="Effacer"
            @click="clearCards"
          />
        </div>

        <div class="grid gap-4 lg:grid-cols-2">
          <UFormField
            label="Nom de la carte"
            help="En français ou en anglais : Mekiki le cherche en japonais."
          >
            <UInput
              v-model="form.name"
              icon="i-lucide-search"
              :placeholder="
                form.game === 'pokemon' ? 'Dracaufeu, Pikachu, Mew…' : 'Luffy, Zoro, Nami…'
              "
              class="w-full"
            />
          </UFormField>
          <UFormField label="Extensions">
            <USelectMenu
              v-model="form.sets"
              multiple
              :items="setItems"
              value-key="value"
              :filter-fields="['label', 'description']"
              :search-input="{ placeholder: 'Code, nom anglais ou japonais…' }"
              :loading="!catalog"
              placeholder="Toutes les extensions"
              class="w-full"
            >
              <template #default>
                <span v-if="form.sets.length" class="truncate">
                  {{ form.sets.length }} extension{{ form.sets.length > 1 ? 's' : '' }}
                </span>
                <span v-else class="truncate text-dimmed">Toutes les extensions</span>
              </template>
            </USelectMenu>
            <div v-if="form.sets.length" class="mt-2 flex flex-wrap gap-1.5">
              <UBadge
                v-for="code in form.sets"
                :key="code"
                color="neutral"
                variant="soft"
                class="gap-1 pe-1"
              >
                {{ setsByCode.get(code) ? setLabel(setsByCode.get(code)!) : code.toUpperCase() }}
                <button
                  type="button"
                  class="rounded text-dimmed hover:text-highlighted"
                  :aria-label="`Retirer ${code.toUpperCase()}`"
                  @click="form.sets = form.sets.filter((each) => each !== code)"
                >
                  <UIcon name="i-lucide-x" class="size-3.5" />
                </button>
              </UBadge>
            </div>
          </UFormField>
        </div>

        <UFormField v-if="catalog?.eras.length" label="Époque">
          <div class="flex flex-wrap items-center gap-2">
            <button
              v-for="preset in eraPresets"
              :key="preset.label"
              type="button"
              :class="[CHIP, chipClass(sameEras(form.eras, preset.eras))]"
              @click="form.eras = [...preset.eras]"
            >
              {{ preset.label }}
              <span v-if="preset.hint" class="text-xs font-normal text-dimmed">{{
                preset.hint
              }}</span>
            </button>
            <span class="mx-1 hidden h-5 w-px bg-accented sm:block" />
            <button
              v-for="era in catalog.eras"
              :key="era.id"
              type="button"
              :class="[CHIP, chipClass(form.eras.includes(era.id))]"
              :aria-pressed="form.eras.includes(era.id)"
              @click="form.eras = toggled(form.eras, era.id)"
            >
              {{ era.label }}
              <span class="text-xs font-normal text-dimmed">{{ era.years }}</span>
            </button>
          </div>
          <template #help>
            Les cartes d’avant 2009 (Wizards, e-Card…) n’ont pas de numéro dans leurs annonces :
            Mekiki ne les reconnaît pas encore.
          </template>
        </UFormField>

        <UFormField v-if="catalog" label="Raretés">
          <div class="flex flex-wrap gap-2">
            <UTooltip
              v-for="rarity in catalog.rarities"
              :key="rarity.id"
              :text="rarity.description"
            >
              <button
                type="button"
                :class="[
                  CHIP,
                  chipClass(form.rarities.includes(rarity.id)),
                  'min-w-12 justify-center',
                ]"
                :aria-pressed="form.rarities.includes(rarity.id)"
                @click="form.rarities = toggled(form.rarities, rarity.id)"
              >
                {{ rarity.label }}
              </button>
            </UTooltip>
          </div>
        </UFormField>
      </section>

      <UCollapsible v-model:open="moreOpen" class="border-t border-default">
        <button
          type="button"
          class="group flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm font-semibold text-highlighted transition-colors hover:bg-elevated/40 sm:px-5"
        >
          <span class="flex items-center gap-2">
            <UIcon name="i-lucide-sliders-horizontal" class="size-4 text-dimmed" />
            Plus de filtres
            <UBadge v-if="moreCount" :label="String(moreCount)" variant="soft" size="sm" />
          </span>
          <UIcon
            name="i-lucide-chevron-down"
            class="size-4 text-dimmed transition-transform duration-200 group-data-[state=open]:rotate-180"
          />
        </button>
        <template #content>
          <div class="space-y-4 px-4 pb-5 sm:px-5">
            <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <UFormField label="Cote Cardmarket" hint="de la carte">
                <div class="flex items-center gap-2">
                  <MoneyInput v-model="form.min_market_cents" currency="EUR" placeholder="min" />
                  <span class="text-dimmed">à</span>
                  <MoneyInput v-model="form.max_market_cents" currency="EUR" placeholder="max" />
                </div>
              </UFormField>
              <UFormField label="Prix de l’annonce" help="Vide : selon le budget par carte.">
                <div class="flex items-center gap-2">
                  <MoneyInput v-model="form.min_price_jpy" currency="JPY" placeholder="min" />
                  <span class="text-dimmed">à</span>
                  <MoneyInput v-model="form.max_price_jpy" currency="JPY" placeholder="max" />
                </div>
              </UFormField>
              <UFormField
                label="État minimum"
                :help="
                  form.min_condition === 'new' || form.min_condition === 'like_new'
                    ? 'Écarte environ 6 annonces Mercari sur 10 : la plupart des cartes parfaites y sont en « Bon état ».'
                    : form.min_condition !== 'all'
                      ? 'Rakuma : lu sur l’annonce.'
                      : undefined
                "
              >
                <USelect v-model="form.min_condition" :items="MIN_CONDITION_ITEMS" class="w-full" />
              </UFormField>
              <UFormField label="Mise en ligne">
                <USelect
                  :model-value="form.max_age_days ?? 0"
                  :items="AGE_ITEMS"
                  class="w-full"
                  @update:model-value="form.max_age_days = $event || null"
                />
              </UFormField>
            </div>
            <div class="flex flex-wrap items-center justify-between gap-4">
              <div class="flex flex-wrap gap-x-8 gap-y-3">
                <USwitch
                  v-if="form.game === 'pokemon'"
                  v-model="form.exclude_mirrors"
                  label="Sans les miroirs"
                  description="Master Ball, Poké Ball, reverse"
                />
                <USwitch
                  v-model="form.confident_only"
                  label="Cartes sûres seulement"
                  description="Reconnues par leur numéro, pas par leur nom"
                />
              </div>
              <UButton
                v-if="moreCount"
                color="neutral"
                variant="ghost"
                size="sm"
                icon="i-lucide-x"
                label="Effacer ces filtres"
                @click="clearMore"
              />
            </div>
          </div>
        </template>
      </UCollapsible>

      <section class="flex flex-wrap gap-4 border-t border-default p-4 sm:p-5">
        <UFormField label="Profondeur" class="min-w-0 flex-[3_1_520px]">
          <URadioGroup
            v-model="form.depth"
            :items="depthItems"
            variant="card"
            orientation="horizontal"
            :ui="{
              fieldset: 'grid gap-2.5 sm:grid-cols-3',
              item: 'bg-default',
              description: 'text-xs',
            }"
          />
        </UFormField>
        <UFormField label="Sites" class="min-w-0 flex-[1_1_240px]">
          <UCheckboxGroup
            v-model="form.sources"
            :items="SCANNABLE_SOURCE_ITEMS"
            variant="card"
            orientation="horizontal"
            :ui="{
              fieldset: 'flex flex-wrap gap-2',
              item: 'bg-default py-2.5',
              description: 'text-xs',
            }"
          />
        </UFormField>
      </section>

      <footer
        class="flex flex-wrap items-center justify-between gap-3 border-t border-default bg-elevated/30 px-4 py-4 sm:px-5"
      >
        <div class="min-w-0 text-sm">
          <p class="truncate font-medium text-highlighted">{{ summary }}</p>
          <p class="text-dimmed">
            Les cartes du colis sont vérifiées sur leur site avant d’être proposées.
          </p>
        </div>
        <UButton
          type="submit"
          icon="i-lucide-wand-sparkles"
          label="Trouver des cartes"
          size="xl"
          :loading="running"
          :disabled="!form.budget_cents || !form.card_count || !form.sources.length"
        />
      </footer>
    </form>
  </UCard>
</template>
