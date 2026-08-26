import axios from 'axios'

/**
 * Holt die lesbare Fehlermeldung aus einer API-Antwort.
 *
 * FastAPI liefert bei HTTPException einen String in `detail`, bei
 * Validierungsfehlern (422) eine Liste von {loc, msg, type}. Beides landet sonst
 * hinter einer generischen Meldung, und der eigentliche Grund ist nur noch im
 * Netzwerk-Tab zu sehen.
 */
export function extractErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) {
    return fallback
  }

  const detail = error.response?.data?.detail
  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail)) {
    const messages = detail.map((entry) => entry?.msg).filter(Boolean)
    if (messages.length > 0) {
      return messages.join(', ')
    }
  }

  return fallback
}
