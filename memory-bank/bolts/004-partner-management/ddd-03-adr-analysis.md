---
stage: adr-analysis
bolt: 004-partner-management
created: 2026-04-06T00:00:00Z
adrs_created: [8]
---

# ADR-Analyse: Partner Core (Bolt 004)

## Überblick

Während des Technical Designs wurde eine nicht-triviale Entscheidung identifiziert, die einen formalen ADR erfordert. Zwei weitere Entscheidungen sind hinreichend im Technical Design dokumentiert.

---

## Entscheidung 1 — IBAN Uniqueness: Global vs. Pro Mandant → **ADR-008**

**Kontext:** Eine IBAN (International Bank Account Number) identifiziert weltweit eindeutig ein Bankkonto. Die Frage ist, ob eine IBAN in Cashflow mehreren Partnern verschiedener Mandanten zugeordnet werden darf.

**Optionen:**
| Option | Pros | Cons |
|--------|------|------|
| IBAN unique pro Mandant | Mandanten voneinander unabhängig | Widerspricht Realität: IBAN ist weltweit eindeutig |
| IBAN unique global | Entspricht Realität | Partner-IBAN nicht kopierbar zwischen Mandanten |

**Entscheidung:** IBAN ist **global unique** über alle Partner aller Mandanten. → **ADR-008**

---

## Entscheidung 2 — Pagination Default Size: 20

**Kontext:** Partner-Listen können groß werden. Welche default page size?

**Entscheidung:** 20 Items per default, max 100 per Request.
**Begründung:** Standard-Konvention, ausreichend für typische Anzeige. Kein ADR — Implementierungsdetail.

---

## Entscheidung 3 — Pattern-Duplikat-Erkennung: Exact Match

**Kontext:** Soll beim Hinzufügen eines Patterns geprüft werden, ob ein semantisch äquivalentes Muster bereits existiert (z. B. zwei Regex die dasselbe matchen)?

**Entscheidung:** Nur Exact-Match auf `(partner_id, pattern, match_field)`. Kein semantischer Vergleich.
**Begründung:** Semantische Regex-Äquivalenz ist NP-hard zu berechnen. Exact-Match verhindert offensichtliche Duplikate. Kein ADR — triviale Scope-Entscheidung.
