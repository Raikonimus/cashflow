---
id: ADR-008
status: accepted
date: 2026-04-06
bolt: 004-partner-management
deciders: [construction-agent]
---

# ADR-008: Partner-IBAN ist global unique (nicht pro Mandant)

## Status
Accepted

## Kontext

In Cashflow können mehrere Mandanten (Firmen) die Anwendung nutzen. Jeder Mandant verwaltet seine eigenen Partner (Geschäftspartner). Partner haben IBANs zugeordnet, über die automatisches Matching beim CSV-Import funktioniert.

Die Frage: Soll eine IBAN nur einmal pro Mandant vergeben werden dürfen, oder einmal global über alle Mandanten?

Beispiel: Der Lieferant "Amazon EU S.a.r.l." hat die IBAN `LU96013000000726000067`. Können Mandant A und Mandant B jeweils einen Partner mit dieser IBAN haben?

## Entscheidung

Eine IBAN ist **global unique** über alle Partner aller Mandanten.

Die Tabelle `partner_ibans` hat einen `UNIQUE`-Constraint auf der `iban`-Spalte (kein Compound-Key mit `mandant_id`).

## Begründung

**Realwelt-Semantik**: Eine IBAN identifiziert weltweit eindeutig ein Bankkonto. Würde Cashflow dieselbe IBAN zwei verschiedenen Partnern zuweisen (auch mandantenübergreifend), wäre die Matching-Logik inkonsistent. Import-Matching würde für die gleiche IBAN in einem Mandanten einen anderen Partner finden als in einem anderen.

**Import-Matching-Stabilität**: Der Partner-Matching-Algorithmus (Bolts 005+) soll zu einer Buchungs-IBAN genau einen Partner zurückgeben. Wenn dieselbe IBAN mehreren Partnern zugeordnet sein kann, ist das Matching nicht mehr deterministisch.

**Datenqualität**: Wenn Mandant A die IBAN von Amazon korrekt zugeordnet hat und Mandant B versucht, dieselbe IBAN einem anderen Partner (z. B. "Microsoft") zuzuordnen, ist das ein Datenfehler. Der 409-Conflict erzwingt Korrektheit.

**Ausnahmefall beachtet**: In der Praxis könnten Mandanten unterschiedliche "Namen" für denselben Lieferanten verwenden. Das ist durch `PartnerName`-Varianten lösbar, nicht durch IBAN-Duplikate.

## Alternativen betrachtet

**IBAN unique pro Mandant (Compound Key)**: Technisch einfach zu implementieren. Aber semantisch falsch — dieselbe IBAN-Nummer repräsentiert immer dasselbe reale Bankkonto.

**Keine IBAN-Uniqueness**: Führt zu undetektierbaren Matching-Konflikten beim Import.

## Konsequenzen

- `partner_ibans.iban` hat `UNIQUE`-Constraint (kein Compound-Key)
- `PartnerService.add_iban()` prüft Uniqueness global (nicht nur pro Mandant)
- HTTP 409: `"IBAN already assigned to another partner"` — auch wenn der andere Partner einem anderen Mandanten gehört
- Kein Information-Leak: Die Fehlermeldung sagt nicht welchem Mandanten/Partner die IBAN gehört
- Ein Partner kann keine IBAN haben die einem anderen Partner gehört — Daten-Migration nötig falls Legacy-Daten vorhanden

## Read When
- Implementierung von IBAN-basierten Lookups im Import-Matching
- Hinzufügen weiterer IBAN-verbrauchender Features
- Multi-Tenancy-Fragen rund um geteilte Stammdaten
- Entscheidung ob andere Entitäten (z. B. Accounts) ähnliche globale Uniqueness brauchen
