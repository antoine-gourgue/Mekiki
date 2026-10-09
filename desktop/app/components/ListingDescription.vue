<script setup lang="ts">
import type { TranslationOut } from '~/types/engine'

/**
 * A listing's description as its seller wrote it, translated into French: on opening with
 * a DeepL key, on demand with the free service (its daily quota is small). Google Translate
 * stays one click away.
 */
const props = defineProps<{ text: string }>()

const engine = useEngine()
// Whether a DeepL key is saved, asked once per session.
const deepl = useState<boolean | null>('translation-deepl', () => null)

const translation = ref<TranslationOut | null>(null)
const failure = ref<string | null>(null)
const translating = ref(false)
const showOriginal = ref(false)

async function translate() {
  translating.value = true
  failure.value = null
  try {
    translation.value = await engine.translate(props.text)
  } catch (error) {
    failure.value = engineErrorMessage(error)
  } finally {
    translating.value = false
  }
}

watch(
  () => props.text,
  async () => {
    translation.value = null
    failure.value = null
    showOriginal.value = false
    if (deepl.value == null) {
      try {
        deepl.value = (await engine.translationStatus()).deepl_configured
      } catch {
        deepl.value = false
      }
    }
    if (deepl.value) await translate()
  },
  { immediate: true },
)

const googleUrl = computed(
  () =>
    `https://translate.google.com/?sl=ja&tl=fr&op=translate&text=${encodeURIComponent(props.text.slice(0, 4000))}`,
)
</script>

<template>
  <section class="space-y-2.5">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="text-xs font-semibold tracking-[0.12em] text-dimmed uppercase">
        Description du vendeur
      </h3>
      <div class="flex items-center gap-1">
        <UButton
          v-if="translation"
          color="neutral"
          variant="ghost"
          size="xs"
          :label="showOriginal ? 'Voir la traduction' : 'Voir l’original'"
          @click="showOriginal = !showOriginal"
        />
        <UButton
          color="neutral"
          variant="ghost"
          size="xs"
          icon="i-lucide-languages"
          trailing-icon="i-lucide-arrow-up-right"
          label="Google Traduction"
          @click="openExternal(googleUrl)"
        />
      </div>
    </div>

    <div class="rounded-lg border border-default bg-elevated/30 p-3.5 text-sm">
      <p v-if="translating" class="flex items-center gap-2 text-muted">
        <UIcon name="i-lucide-loader-circle" class="size-4 animate-spin" />
        Traduction en cours…
      </p>
      <template v-else-if="translation && !showOriginal">
        <p class="whitespace-pre-line text-toned">{{ translation.text }}</p>
        <p class="mt-2 text-xs text-dimmed">
          Traduction automatique
          {{ translation.provider === 'deepl' ? 'DeepL' : 'MyMemory' }} : vérifiez les points
          importants sur l’original.
        </p>
      </template>
      <template v-else>
        <p class="line-clamp-[12] whitespace-pre-line text-toned" lang="ja">{{ text }}</p>
        <div v-if="!translation" class="mt-3 flex flex-wrap items-center gap-2">
          <UButton
            size="sm"
            icon="i-lucide-languages"
            label="Traduire en français"
            @click="translate"
          />
          <span v-if="failure" class="text-xs text-error">{{ failure }}</span>
        </div>
      </template>
    </div>
  </section>
</template>
