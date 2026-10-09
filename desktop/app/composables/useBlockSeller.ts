import type { SourcePlatform } from '~/types/engine'

/**
 * Blocks a listing's seller after confirmation, for the sellers Neokyo refuses to buy from:
 * their listings then leave every search, discovery and tracked card. Resolves to `true`
 * once blocked.
 */
export function useBlockSeller() {
  const engine = useEngine()
  const confirm = useConfirm()
  const toast = useToast()
  const showError = useErrorToast()

  return async (
    listing: { source: SourcePlatform; external_id: string },
    options: { sellerId?: string | null; reason?: string } = {},
  ) => {
    const confirmed = await confirm({
      title: 'Ne plus proposer ce vendeur ?',
      description:
        'Neokyo refuse d’acheter chez lui : ses annonces seront écartées des recherches, de la découverte et des cartes suivies, pour tous les comptes de ce PC. Vous pourrez le débloquer dans Paramètres.',
      confirmLabel: 'Bloquer le vendeur',
    })
    if (!confirmed) return false
    try {
      await engine.blockSeller({
        source: listing.source,
        external_id: listing.external_id,
        seller_id: options.sellerId ?? null,
        reason: options.reason ?? 'bloqué par Neokyo',
      })
      toast.add({
        title: 'Vendeur bloqué',
        description: 'Ses annonces ne vous seront plus proposées.',
        color: 'success',
      })
      return true
    } catch (error) {
      showError(error)
      return false
    }
  }
}
