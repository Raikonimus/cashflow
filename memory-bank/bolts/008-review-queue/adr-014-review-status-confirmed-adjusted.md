---
id: ADR-014
title: ReviewItem-Status präzisiert — confirmed und adjusted statt resolved
status: accepted
date: 2026-04-07
bolt: 008-review-queue
supersedes: ADR-012 (partial)
---

## Context

ADR-012 definierte zwei Status-Werte: `open` und `resolved`. Im Technical Design von Bolt 008 zeigte sich, dass ein einzelner `resolved`-Status zu wenig Information trägt: ein Accountant kann eine Zuordnung entweder **bestätigen** (die automatische Entscheidung war korrekt) oder **korrigieren** (Reassign zu anderem Partner oder neuer Partner). Diese zwei Aktionen haben unterschiedliche Konsequenzen (ADR-013: IBAN-Registrierung nur bei Confirm) und sind für spätere Auswertung und Audit unterscheidbar.

## Decision

**Der `resolved`-Status aus ADR-012 wird durch zwei Status-Werte ersetzt**:

| Status | Bedeutung | Aktion |
|---|---|---|
| `open` | offen, wartet auf Bearbeitung | (Anlage durch PartnerMatchingService) |
| `confirmed` | bestätigt: automatische Zuordnung war korrekt | POST /{id}/confirm |
| `adjusted` | korrigiert: anderer Partner oder neuer Partner | POST /{id}/reassign oder /{id}/new-partner |

Die Tabellen-Spalte `review_items.status VARCHAR(20)` bleibt unverändert — die neuen Werte passen in das bestehende Feld.

## Rationale

- `confirmed` vs. `adjusted` erlaubt präzisere Metriken (z.B. "Wie oft war das automatische Matching korrekt?")
- ADR-013 erfordert die Unterscheidung: IBAN-Registrierung nur bei `confirmed`, nicht bei `adjusted`
- Die ursprüngliche Vereinfachung in ADR-012 war bewusst als "erweiterbar" deklariert ("Mehr Status-Werte: zu früh für MVP")

## Alternatives Considered

- **`resolved` beibehalten + `resolution_type`-Feld**: Unnötige Komplexität bei gleichem Informationsgehalt. Abgelehnt.
- **`resolved` beibehalten, Unterscheidung nur im Audit-Log**: Führt zu aufwändigem Auswertungs-Join. Abgelehnt.

## Consequences

- `review_items.status` kann die Werte `open`, `confirmed`, `adjusted` annehmen.
- Code und Queries müssen auf `status IN ('confirmed', 'adjusted')` prüfen statt `status = 'resolved'`, wenn nach "aufgelösten" Items gesucht wird.
- Kein Schema-Breaking-Change (VARCHAR(20), bisher nur `open` und `resolved` in DB).
- ADR-012 ist in Bezug auf den `resolved`-Status überholt; alle anderen Aussagen (kein Auto-Resolve, kein Hard-Delete, Roles) bleiben gültig.

## Read When

Queries auf `review_items` (Filter für offene vs. abgeschlossene Items); Metriken / Dashboards; Frontend Review-Queue-Ansicht; spätere Status-Erweiterungen.
