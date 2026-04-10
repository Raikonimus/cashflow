---
id: ADR-006
status: accepted
date: 2026-04-06
bolt: 003-tenant-account-mgmt
deciders: [construction-agent]
---

# ADR-006: Mandant-Deaktivierung als Soft Cascade (is_active=False)

## Status
Accepted

## Kontext

Ein Admin kann einen Mandanten deaktivieren. Nach der Deaktivierung sollen:
1. Alle Benutzer des Mandanten keinen Zugriff mehr haben (sofort)
2. Alle Bankkonten (Accounts) des Mandanten für Import-Jobs als inaktiv gelten
3. Die Daten erhalten bleiben (Buchungen, Konfigurationen, Partner)

Die Entscheidung lautet: Wie wird Deaktivierung technisch umgesetzt?

## Entscheidung

Wir verwenden **Soft Deaktivierung mit Service-seitigem Cascade**:

1. `Mandant.is_active` wird auf `False` gesetzt
2. In **demselben Service-Call** werden alle zugehörigen `Account.is_active` ebenfalls auf `False` gesetzt
3. Keine Daten werden gelöscht
4. Der `require_mandant_access`-Dependency aus Bolt 001 prüft bereits `MandantUser.is_active` — wir ergänzen einen Check auf `Mandant.is_active`

**Nicht** verwendet: DB-Level `ON DELETE CASCADE` für aktiven Content (Anwendung: nur für FK-Referenzen auf gelöschte Entities sinnvoll, nicht für Soft-Deaktivierung).

## Begründung

**Datensicherheit**: Buchungsdaten, Konfigurationen und Partner eines Mandanten haben eigenständigen Wert. Löschung bei Deaktivierung wäre destruktiv und nicht reversibel.

**Reversibilität**: Business-Anforderungen können sich ändern (Mandant re-aktivieren, Buchungen analysieren nach Deaktivierung). Soft-Delete ermöglicht Wiederherstellung.

**Konsistenz**: Import-Jobs prüfen `Account.is_active` vor der Verarbeitung. Wenn nur der Mandant deaktiviert wird, die Accounts aber aktiv bleiben, müssten alle Job-Queries einen Join auf `mandants` machen — unnötige Kopplung.

## Alternativen betrachtet

**Hard Delete**: Zu destruktiv. Buchungsdaten gehen verloren. Keine Undo-Möglichkeit.

**Nur Mandant deaktivieren (ohne Account-Cascade)**: Import-Jobs müssten immer auf `mandants.is_active` joinen — schlechtere Entkopplung.

**DB-Trigger für Cascade**: Zu viel Logik in der DB, schwerer zu testen und zu debuggen.

## Konsequenzen

- `MandantService.deactivate_mandant()` muss alle Accounts in einer Transaktion aktualisieren
- `require_mandant_access`-Dependency prüft zusätzlich `Mandant.is_active`
- Re-Aktivierung eines Mandanten setzt **nicht** automatisch Accounts auf aktiv (explizite Admin-Aktion erforderlich — verhindert versehentliches Wiederaktivieren von Accounts die manuell deaktiviert wurden)
- Alembic-Migration braucht keinen Cascade — das ist Service-Logik

## Read When
- Implementierung von Mandant-Deaktivierung oder -Löschung
- Prüfung ob inaktiver Mandant auf Backend-Access-Checks trifft
- Import-Jobs die Account-Aktivierungs-Status prüfen
- Re-Aktivierungs-Feature für Mandanten
