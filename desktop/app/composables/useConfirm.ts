import ConfirmModal from '~/components/ConfirmModal.vue'

/** Asks for confirmation in a modal; resolves to `true` only when the user confirms. */
export function useConfirm() {
  const modal = useOverlay().create(ConfirmModal)
  return async (props: { title: string; description?: string; confirmLabel?: string }) =>
    (await modal.open(props).result) === true
}
