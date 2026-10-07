const eur = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' })
const jpy = new Intl.NumberFormat('fr-FR', {
  style: 'currency',
  currency: 'JPY',
  currencyDisplay: 'narrowSymbol',
})
const percent = new Intl.NumberFormat('fr-FR', {
  style: 'percent',
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})
const longDate = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'medium' })
const monthName = new Intl.DateTimeFormat('fr-FR', { month: 'short', year: '2-digit' })

const EMPTY = '—'

export function formatCents(cents: number | null | undefined): string {
  return cents == null ? EMPTY : eur.format(cents / 100)
}

export function formatYen(yen: number | null | undefined): string {
  return yen == null ? EMPTY : jpy.format(yen)
}

/** Formats a fraction (0.1797) as a percentage (18,0 %). */
export function formatRatio(ratio: number | null | undefined): string {
  return ratio == null ? EMPTY : percent.format(ratio)
}

/**
 * Formats an ISO date (2026-10-05) without shifting it through the local time zone. A full
 * timestamp (2026-10-05T18:55:54Z) shows its date part.
 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return EMPTY
  const [year, month, day] = iso.slice(0, 10).split('-').map(Number)
  const date = new Date(year!, month! - 1, day)
  return Number.isNaN(date.getTime()) ? EMPTY : longDate.format(date)
}

const dateTime = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' })

/** Formats a UTC timestamp (2026-10-07T14:03:00Z) in local time. */
export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTime.format(new Date(iso)) : EMPTY
}

/** Formats a `YYYY-MM` key as a short month label (oct. 26). */
export function formatMonth(key: string): string {
  const [year, month] = key.split('-').map(Number)
  return monthName.format(new Date(year!, month! - 1, 1))
}

/** A date as `YYYY-MM-DD`, in local time. */
export function toIsoDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function todayIso(): string {
  return toIsoDate(new Date())
}

/** Text color for a signed amount: margins and ROI read red below zero. */
export function signClass(value: number | null | undefined): string {
  if (value == null || value === 0) return ''
  return value > 0 ? 'text-success' : 'text-error'
}
