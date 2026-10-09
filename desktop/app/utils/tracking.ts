/** Where to follow a parcel, from its tracking number. */
export interface Tracking {
  carrier: string
  url: string
}

// International postal numbers end with the country of the post that took the parcel.
const JAPAN_POST = /^[A-Z]{2}\d{9}JP$/
const FRENCH_POST = /^[A-Z]{2}\d{9}FR$/
// Colissimo and La Poste numbers inside France: "6A12345678901", "8R12345678901".
const COLISSIMO = /^\d[A-Z]\d{11}$/
const UPS = /^1Z[0-9A-Z]{16}$/

/**
 * The tracking page of a parcel. Numbers whose carrier cannot be told apart (DHL, FedEx,
 * Mondial Relay…) go to 17TRACK, which finds the carrier itself.
 */
export function trackingFor(number: string | null | undefined): Tracking | null {
  const code = (number ?? '').replace(/\s+/g, '').toUpperCase()
  if (!code) return null
  if (JAPAN_POST.test(code)) {
    return {
      carrier: 'Japan Post',
      url: `https://trackings.post.japanpost.jp/services/srv/search/direct?reqCodeNo1=${code}&locale=en`,
    }
  }
  if (FRENCH_POST.test(code) || COLISSIMO.test(code)) {
    return {
      carrier: 'La Poste',
      url: `https://www.laposte.fr/outils/suivre-vos-envois?code=${code}`,
    }
  }
  if (UPS.test(code)) {
    return { carrier: 'UPS', url: `https://www.ups.com/track?tracknum=${code}&loc=fr_FR` }
  }
  return { carrier: '17TRACK', url: `https://t.17track.net/fr#nums=${encodeURIComponent(code)}` }
}
