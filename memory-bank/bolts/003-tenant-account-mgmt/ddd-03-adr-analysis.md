---
stage: adr-analysis
bolt: 003-tenant-account-mgmt
created: 2026-04-06T00:00:00Z
adrs_created: [6, 7]
---

# ADR-Analyse: Tenants & Accounts (Bolt 003)

## Überblick

Während des Technical Designs wurden drei Fragen identifiziert. Zwei davon sind nicht-trivial und erfordern formale ADRs.

---

## Entscheidung 1 — Mandant-Deaktivierung: Soft Cascade → **ADR-006**

**Kontext:** Wenn ein Mandant deaktiviert wird, soll der Zugriff für alle seine Benutzer sofort gesperrt werden. Außerdem sollen alle zugehörigen Accounts ebenfalls als inaktiv markiert werden, damit zukünftige Import-Jobs sie ignorieren.

**Optionen:**
| Option | Pros | Cons |
|--------|------|------|
| Hard delete Mandant + Cascade | Sauber, keine Leichen | Datenverlust, nicht reversibel |
| Hard delete nur Accounts | Accounts weg, Mandant bleibt | Inkonsistent, Journal-Orphans |
| Soft: `is_active=False` auf Mandant | Reversibel, Daten bleiben | Auth-Check muss is_active prüfen |
| Soft: Cascade auf Accounts | Imports ignorieren inaktive Accounts | Service-Code nötig (kein reiner DB-Cascade) |

**Entscheidung:** Soft Cascade — `Mandant.is_active=False` setzt auch alle `Account.is_active=False`. Datenverlust vermieden; Deaktivierung reversibel. → **ADR-006**

---

## Entscheidung 2 — Remapping: Async 202 vs. Synchron → **ADR-007**

**Kontext:** `POST /accounts/{id}/remap` soll Re-Matching aller bereits importierten Buchungen eines Accounts auslösen. Das kann bei vielen Buchungen Sekunden bis Minuten dauern.

**Optionen:**
| Option | Pros | Cons |
|--------|------|------|
| Synchron in Request | Einfach, kein Queue-Overhead | Timeout-Risiko, blockiert HTTP-Request |
| Async (Job Queue) | Skalierbar, User-freundlich | Queue-Infrastruktur nötig (Redis/Celery) |
| Async mit DB-Status-Tracking | Job-Status abfragbar, kein extra Infra im MVP | Etwas mehr Komplexität |

**Entscheidung:** Async mit DB-Status-Tracking. In diesem Bolt: Placeholder-Implementierung (202 Accepted, Log-Eintrag). Eigentliche Queue-Logik in späterem Bolt. → **ADR-007**

---

## Entscheidung 3 — IBAN-Validierung: Format vs. Nur Uniqueness

**Kontext:** Sollen IBANs beim Anlegen eines Accounts formatvalidiert werden (Prüfziffer, Länderpräfix)?

**Entscheidung:** Im MVP nur Normalisierung (strip + uppercase) und Uniqueness-Check. Kein Format-Check.
**Begründung:** Scope-Control. IBAN-Validierung (Mod-97-Prüfziffer) ist nicht-trivial und bringt keinen unmittelbaren Mehrwert für das Import-Feature. Kann in einem späteren Bolt ergänzt werden.

**Kein ADR** — triviale Scope-Entscheidung, hinreichend im Technical Design dokumentiert.
