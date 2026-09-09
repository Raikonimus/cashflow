// Beschriftungen und Formatierer der Review-Seiten.
//
// Getrennt von den Komponenten, weil eine Datei, die beides exportiert, das
// Hot-Reloading von React aushebelt (react-refresh/only-export-components).
export const reviewTypeLabels: Record<string, string> = {
  name_match: 'Partner-Prüfung',
  name_match_with_iban: 'IBAN-Abweichung',
  partner_name_match: 'Partner-Prüfung',
  no_partner_identified: 'Kein Partner',
  new_partner: 'Neuer Partner',
  service_assignment: 'Leistungs-Zuordnung',
  service_matcher_ambiguous: 'Mehrdeutiger Matcher',
  service_type_review: 'Leistungstyp',
  manual_service_assignment: 'Manuelle Leistungszuordnung',
}

export const serviceTypeLabels: Record<string, string> = {
  customer: 'Kunde',
  supplier: 'Lieferant',
  employee: 'Mitarbeiter',
  shareholder: 'Gesellschafter',
  authority: 'Behörde',
  internal_transfer: 'Interne Umbuchung',
  unknown: 'Unbekannt',
}

export const reviewStatusLabels: Record<string, string> = {
  open: 'Offen',
  confirmed: 'Bestätigt',
  adjusted: 'Korrigiert',
  rejected: 'Abgelehnt',
}

const reviewReasonLabels: Record<string, string> = {
  name_match: 'Namens-Treffer',
  iban_match: 'IBAN-Treffer',
  new_partner: 'Neuer Partner',
}

export function formatCurrency(amount: string, currency = 'EUR') {
  const value = Number(amount)
  if (Number.isNaN(value)) return amount
  return value.toLocaleString('de-DE', { style: 'currency', currency })
}

export function formatReviewReason(reason: string | undefined) {
  if (!reason) return 'Automatische Prüfung'
  if (reason in reviewReasonLabels) return reviewReasonLabels[reason]
  if (reason === 'multiple_matches') return 'Mehrere Matcher passen auf diese Buchung.'
  if (reason === 'single_match') return 'Ein Matcher passt eindeutig auf diese Buchung.'
  if (reason === 'no_match_base_service')
    return 'Keine passende Leistung gefunden, Basisleistung gewählt.'
  if (reason.startsWith('keyword:')) return `Keyword-Regel: ${reason.replace('keyword:', '')}`
  if (reason === 'amount<=0') return 'Automatisch aus negativem Betrag abgeleitet.'
  if (reason === 'amount>0') return 'Automatisch aus positivem Betrag abgeleitet.'
  return reason.replaceAll('_', ' ')
}
