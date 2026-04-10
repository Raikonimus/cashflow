---
id: ADR-013
title: Confirm registriert IBAN automatisch in partner_ibans
status: accepted
date: 2026-04-07
bolt: 008-review-queue
supersedes: null
---

## Context

Ein ReviewItem vom Typ `name_match_with_iban` entsteht, wenn eine JournalLine per Namensgleichheit einem Partner zugeordnet wurde und eine rohe IBAN vorliegt, die noch nicht im System registriert ist. Wenn ein Accountant diese Zuordnung bestätigt (`confirm`), ist unklar, ob die IBAN automatisch zum Partner hinzugefügt werden soll oder ob das ein separater manueller Schritt sein muss.

## Decision

**Confirm registriert die IBAN automatisch**: Bei einem erfolgreichen `POST /{item_id}/confirm` wird `journal_line.partner_iban_raw` normalisiert und als neuer `PartnerIban`-Eintrag für den Partner gespeichert — sofern die IBAN nicht bereits für diesen Partner registriert ist (Idempotenz).

## Rationale

- Ein Accountant, der eine Zuordnung bestätigt, erklärt damit implizit: "Diese IBAN gehört zu diesem Partner."
- Ohne automatische Registrierung würde der nächste Import mit derselben IBAN erneut ein ReviewItem erzeugen — d.h. derselbe Accountant müsste denselben Vorgang in jeder Periode wiederholt bestätigen.
- Die Automatik ist nur beim Confirm aktiv, nicht bei Reassign oder NewPartner (dort ist die Semantik unklar — IBAN könnte falsch sein).

## Alternatives Considered

- **Manuelle IBAN-Registrierung nach Confirm**: Zweistufiger Prozess ist fehleranfällig und erzeugt redundante Review-Arbeit. Abgelehnt.
- **IBAN immer registrieren (auch bei Reassign)**: Bei Reassign kann die IBAN ein Tippfehler sein — zu riskant. Nur bei Confirm ist die Semantik eindeutig.
- **IBAN nie automatisch registrieren**: Widerspricht dem Ziel, Review-Arbeit zu reduzieren. Abgelehnt.

## Consequences

- `PartnerService.add_iban()` oder gleichwertiger Code wird von `ReviewService.confirm()` aufgerufen.
- `PartnerIban.iban` ist global unique (ADR-008) — Duplikat-Check ist nötig (`ON CONFLICT IGNORE` oder Select-before-Insert).
- Bei Reassign und NewPartner: IBAN wird **nicht** automatisch registriert.

## Read When

`008-review-queue`-Implementierung (confirm-Aktion); `PartnerMatchingService`-Tests (wird die IBAN beim nächsten Import direkt per IBAN gematcht?); Frontend zeigt Confirm-Aktion an.
