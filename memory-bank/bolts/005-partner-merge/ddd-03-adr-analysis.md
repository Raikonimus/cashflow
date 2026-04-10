---
stage: adr-analysis
bolt: 005-partner-merge
created: 2026-04-06T00:00:00Z
adrs_created: [9]
---

# ADR-Analyse: Partner Merge (Bolt 005)

## Überblick

Während des Technical Designs wurde eine nicht-triviale Entscheidung identifiziert, die einen formalen ADR erfordert. Eine weitere Entscheidung ist direkt im Technical Design dokumentiert.

---

## Entscheidung 1 — Source-Partner nach Merge: Soft-Delete vs. Hard-Delete → **ADR-009**

**Kontext:** Nach einem Merge wird der Source-Partner nicht mehr benötigt. Soll er aus der Datenbank gelöscht oder nur deaktiviert werden?

**Optionen:**
| Option | Pros | Cons |
|--------|------|------|
| Hard-Delete (DELETE) | Keine "toten" Einträge in der DB | Referenzielle Integrität verletzt wenn Audit-Logs oder alte Importe auf source zeigen; nicht reversibel |
| Soft-Delete (is_active=false) | Reversibel; Audit-Log bleibt konsistent; konsistent mit ADR-006 | Source taucht evtl. in Suchen auf wenn nicht gefiltert |

**Entscheidung:** Source-Partner wird per **Soft-Delete deaktiviert** (`is_active = false`). → **ADR-009**

---

## Entscheidung 2 — Deduplizierung beim Merge: Lautlos vs. Fehler

**Kontext:** Wenn Source und Target beide dieselbe IBAN haben (z. B. durch manuelles doppeltes Anlegen), soll der Merge mit einem Fehler abbrechen oder die Duplikate lautlos ignorieren?

**Entscheidung:** Duplikate werden **lautlos ignoriert** (kein Fehler, keine Warnung).
**Begründung:** Der Zweck des Merge ist Bereinigung. Ein Fehler beim Merge wegen Duplikaten würde die Bereinigung blockieren. Das Deduplizieren ist der erwünschte Nebeneffekt. Kein ADR — Verhaltensdetail ohne langfristige architekturelle Konsequenz.

---

## Entscheidung 3 — journal_lines-Tabelle fehlt (Bolt 006 noch nicht ausgeführt)

**Kontext:** `_reassign_journal_lines()` macht ein `UPDATE journal_lines ...`. Wenn Bolt 006 noch nicht migriert worden ist, existiert die Tabelle nicht.

**Entscheidung:** `_reassign_journal_lines()` gibt bei fehlendem Table **0 zurück (kein Fehler)**. Realisiert über Exception-Handling auf `SQLAlchemyError` vom Typ `UndefinedTable`. Kein ADR — temporäres Reihenfolge-Problem das nach Migration 006 entfällt.
