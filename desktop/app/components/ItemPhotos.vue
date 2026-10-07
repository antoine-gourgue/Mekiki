<script setup lang="ts">
import type { ItemPhoto } from '~/types/engine'

/** Photos of a card for its listings: add, choose the main one, delete. */
const props = defineProps<{ itemId: number }>()
const photos = defineModel<ItemPhoto[]>({ required: true })
const emit = defineEmits<{ changed: [] }>()

const engine = useEngine()
const showError = useErrorToast()

// Photos need the session token, which an <img src> cannot send: they are fetched as blobs.
const urls = ref<Record<number, string>>({})

async function loadMissing() {
  for (const photo of photos.value) {
    if (urls.value[photo.id]) continue
    try {
      const blob = await engine.photoBlob(props.itemId, photo.id)
      urls.value = { ...urls.value, [photo.id]: URL.createObjectURL(blob) }
    } catch {
      // A missing file shows as an empty tile; deleting the photo clears it.
    }
  }
}
watch(photos, loadMissing, { immediate: true })
onBeforeUnmount(() => Object.values(urls.value).forEach((url) => URL.revokeObjectURL(url)))

// Phone photos weigh several megabytes: listings need far less than 1600 pixels.
const MAX_SIDE = 1600

async function downscale(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file)
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()
  return canvas.toDataURL('image/jpeg', 0.9)
}

const uploading = ref(false)
const input = useTemplateRef<HTMLInputElement>('input')

async function add(event: Event) {
  const files = [...((event.target as HTMLInputElement).files ?? [])]
  if (!files.length) return
  uploading.value = true
  try {
    for (const file of files) {
      photos.value = await engine.addPhoto(props.itemId, await downscale(file))
    }
    emit('changed')
  } catch (error) {
    showError(error, 'Photo refusée')
  } finally {
    uploading.value = false
    if (input.value) input.value.value = ''
  }
}

async function run(action: () => Promise<ItemPhoto[]>) {
  try {
    photos.value = await action()
    emit('changed')
  } catch (error) {
    showError(error)
  }
}
</script>

<template>
  <div class="space-y-2">
    <div class="grid grid-cols-3 gap-2 sm:grid-cols-4">
      <div
        v-for="(photo, index) in photos"
        :key="photo.id"
        class="group relative aspect-square overflow-hidden rounded-md bg-elevated"
      >
        <img v-if="urls[photo.id]" :src="urls[photo.id]" alt="" class="size-full object-cover" />
        <UBadge v-if="index === 0" label="Principale" size="sm" class="absolute top-1 left-1" />
        <div
          class="absolute inset-x-1 bottom-1 flex justify-end gap-1 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100"
        >
          <UButton
            v-if="index > 0"
            icon="i-lucide-star"
            size="xs"
            color="neutral"
            variant="solid"
            aria-label="Mettre en photo principale"
            @click="run(() => engine.movePhotoFirst(itemId, photo.id))"
          />
          <UButton
            icon="i-lucide-trash-2"
            size="xs"
            color="error"
            variant="solid"
            aria-label="Supprimer la photo"
            @click="run(() => engine.deletePhoto(itemId, photo.id))"
          />
        </div>
      </div>

      <button
        type="button"
        class="flex aspect-square flex-col items-center justify-center gap-1 rounded-md border border-dashed border-accented text-sm text-muted hover:bg-elevated/50 disabled:opacity-50"
        :disabled="uploading || photos.length >= 12"
        @click="input?.click()"
      >
        <UIcon
          :name="uploading ? 'i-lucide-loader-circle' : 'i-lucide-image-plus'"
          class="size-6"
          :class="{ 'animate-spin': uploading }"
        />
        {{ uploading ? 'Envoi…' : 'Ajouter' }}
      </button>
    </div>
    <p class="text-xs text-muted">
      Recto, verso et gros plans : 12 photos au maximum. La première est la photo principale.
    </p>
    <input
      ref="input"
      type="file"
      accept="image/jpeg,image/png,image/webp"
      multiple
      class="hidden"
      @change="add"
    />
  </div>
</template>
