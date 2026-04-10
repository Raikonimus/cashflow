---
id: ADR-009
status: accepted
date: 2026-04-06
bolt: 005-partner-merge
deciders: [construction-agent]
---

# ADR-009: Partner-Merge deaktiviert Source (Soft-Delete, kein Hard-Delete)

## Status
Accepted

## Kontext

Nach einem erfolgreichen Partner-Merge muss der Source-Partner aus dem normalen Betrieb entfernt werden — er soll nicht mehr beim Import-Matching gefunden werden, nicht mehr in Listen auftauchen und nicht mehr als Merge-Quelle dienen können.

Die Frage: Soll der Source-Partner hart aus der Datenbank gelöscht (`DELETE`) oder nur deaktiviert werden (`is_active = false`)?

Relevanter Kontext: ADR-006 hat für die Mandant-Deaktivierung ebenfalls Soft-Delete gewählt. `journal_lines` referenzieren `partner_id`. Der Audit-Log-Eintrag des Merge enthält `source_partner_id`.

## Entscheidung

Der Source-Partner wird per **Soft-Delete** deaktiviert: `is_active = false`, `updated_at = now()`.

Er bleibt in der Datenbank erhalten, ist jedoch über keine reguläre API-Abfrage mehr abrufbar (alle `list_partners`-Queries filtern auf `is_active = true`).

## Rationale

**Referenzielle Integrität**: `journal_lines.partner_id` zeigt auf `partners.id`. Nach dem Merge wurden alle Buchungszeilen auf den Target umgeschrieben. Buchungszeilen die *vor* dem Merge importiert wurden und noch nicht re-gematcht wurden könnten jedoch theoretisch noch auf source zeigen. Ein Hard-Delete würde die FK-Constraint verletzen (oder erfordert `ON DELETE SET NULL`, was Datenverlust bedeutet).

**Audit-Log-Konsistenz**: Der Audit-Log-Eintrag speichert `source_partner_id`. Bei Hard-Delete wäre diese UUID orphan — der Log wäre nicht mehr vollständig nachvollziehbar.

**Reversibilität**: Deaktivierung kann rückgängig gemacht werden (Admin setzt `is_active = true` zurück). Ist ein Merge irrtümlich ausgeführt worden, kann der Source-Partner reaktiviert werden und Buchungszeilen manuell zurückgemigriert werden.

**Konsistenz mit ADR-006**: Das gesamte Cashflow-Datenmodell bevorzugt Soft-Delete für fachliche Entitäten. Hard-Deletes würden Ausnahmebehandlung in Queries erfordern (LEFT JOIN statt INNER JOIN für historische Daten).

### Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|-------------|------|------|--------------|
| Hard-Delete (DELETE FROM partners WHERE id=source_id) | Keine "toten" Einträge | FK-Failure bei nicht-gemigrierten journal_lines; Audit-Log zeigt orphan UUID; irreversibel | Datenintegrität nicht gewährleistet |
| ON DELETE CASCADE auf journal_lines | Automatische Bereinigung | Löscht Buchungszeilen die noch auf source zeigen — Datenverlust | Katastrophales Risiko |
| ON DELETE SET NULL auf journal_lines | Kein FK-Failure | Buchungszeilen ohne Partner → Matching-Informationsverlust | Datenverlust, inkonsistenter Zustand |

## Consequences

### Positive
- Referenzielle Integrität bleibt ohne Constraint-Änderungen gewahrt
- Audit-Log bleibt vollständig nachvollziehbar
- Merge ist de facto reversibel
- Konsistent mit dem etablierten Soft-Delete-Muster (ADR-006)

### Negative
- `is_active`-Filter muss in allen Partner-Queries konsequent verwendet werden
- Inaktive Partner akkumulieren sich in der DB (keine automatische Bereinigung)

### Risks
- Vergessen des `is_active`-Filters in neuen Queries → inaktive/gemergte Partner tauchen auf. **Mitigation**: Alle Partner-Queries nutzen `WHERE is_active = true` per Konvention; Code-Review-Checkliste.

## Related

- **Stories**: `004-partner-merge.md`
- **Previous ADRs**: ADR-006 (Soft-Deaktivierung bei Mandanten), ADR-008 (IBAN global unique)
- **Read when**: Implementierung der Partner-Liste (is_active-Filter); Import-Matching-Queries (sollen inaktive Partner ignorieren); Re-Aktivierungs-Feature für Partner; Datenbankbereinigung/Archivierung
