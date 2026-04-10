---
id: ADR-011
title: Partner-Matching filtert inaktive Partner aus
status: accepted
date: 2026-04-07
bolt: 007-partner-matching
---

## Context

Partner können durch Merge (ADR-009) oder Mandant-Deaktivierung (ADR-006) auf `is_active=false` gesetzt werden. Ohne expliziten Filter würden IBAN- und Name-Lookups beim Import auch inaktive Partner als Treffer liefern. Das würde Buchungszeilen einem Partner zuordnen, der aus Business-Sicht nicht mehr existiert.

## Decision

**Das Matching filtert ausschließlich auf aktive Partner** (`is_active=True`). Sowohl der IBAN-Join als auch der Name-Join ergänzen `.where(Partner.is_active == True)`.

Konsequenz: Eine IBAN, die zum deaktivierten Partner gehört, erzeugt keinen IBAN-Match mehr → Fallback auf Name-Match oder Neu-Anlage.

## Alternatives Considered

- **Kein Filter**: Inaktive Partner werden zugeordnet. Führt zu Buchungen auf "gelöschte" Partner — verwirrend für Benutzer und schwer reparierbar.
- **Warnung statt Ablehnung**: Match auslösen, aber Review-Item mit Typ `inactive_partner` erzeugen. Zu komplex für MVP; kann in `008-review-queue` nachgerüstet werden.

## Consequences

- Matching ist konsistent mit dem is_active-Konzept aus ADR-006 und ADR-009.
- Nach einem Merge kann die IBAN des Quell-Partners keine Zeilen mehr attrahieren → gewolltes Verhalten.
- `find_by_iban` und `find_by_name_ilike` müssen beide den is_active-Filter tragen.

## Read When

Import-Matching-Implementierung; Queries auf `partner_ibans`/`partner_names` im Import-Kontext; Frage ob deaktivierte Partner in Matching eingehen sollen; `008-review-queue`-Bolt.
