import ResaleModal from '~/components/ResaleModal.vue'
import type { ResaleQuery } from '~/types/engine'

/** Opens the European prices of a card: eBay listings, eBay sold and Vinted links. */
export function useResaleModal() {
  const modal = useOverlay().create(ResaleModal)
  return (title: string, query: ResaleQuery) => {
    void modal.open({ title, query })
  }
}
