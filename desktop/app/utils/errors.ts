interface EngineErrorShape {
  statusCode?: number
  data?: { detail?: unknown }
}

/** French message for a failed engine call, suitable for a toast. */
export function engineErrorMessage(error: unknown): string {
  const { statusCode, data } = (error ?? {}) as EngineErrorShape
  if (!statusCode) return 'Le moteur ne répond pas. Vérifiez qu’il est bien lancé.'
  if (statusCode === 404) return 'Élément introuvable : il a peut-être été supprimé.'
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
