interface EngineErrorShape {
  statusCode?: number
  data?: { detail?: unknown }
}

/** French message for a failed engine call, suitable for a toast. */
export function engineErrorMessage(error: unknown): string {
  const { statusCode, data } = (error ?? {}) as EngineErrorShape
  if (!statusCode) return 'Le moteur ne répond pas. Vérifiez qu’il est bien lancé.'
  // A missing row is named in English, for the engine's logs.
  if (statusCode === 404) return 'Élément introuvable : il a peut-être été supprimé.'
  // Otherwise a text detail is the engine's French sentence for the user, whatever the status
  // (refused values, accounts, Chrome missing, translation down…).
  const detail = typeof data?.detail === 'string' ? data.detail.trim() : ''
  if (detail) {
    const sentence = `${detail.charAt(0).toUpperCase()}${detail.slice(1)}`
    return /[.!?…]$/.test(sentence) ? sentence : `${sentence}.`
  }
  if (statusCode === 422) {
    const fields = Array.isArray(data?.detail)
      ? data.detail.map((d: { loc?: unknown[] }) => d.loc?.at(-1)).filter(Boolean)
      : []
    return fields.length
      ? `Valeurs invalides : ${fields.join(', ')}.`
      : 'Certaines valeurs sont invalides.'
  }
  return `Le moteur a renvoyé une erreur (${statusCode}).`
}
