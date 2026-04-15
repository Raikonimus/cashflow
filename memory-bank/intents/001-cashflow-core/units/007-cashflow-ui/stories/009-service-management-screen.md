---
id: 009-service-management-screen
unit: 007-cashflow-ui
intent: 001-cashflow-core
status: ready
priority: must
created: 2026-04-10T00:00:00Z
assigned_bolt: null
implemented: true
---

# Story: 009-service-management-screen

## User Story

**As an** Accountant
**I want** to manage services and their matchers for a partner
**So that** booking lines can be assigned correctly and transparently

## Acceptance Criteria

- [x] /partners/:id/services zeigt alle Leistungen des Partners inklusive Basisleistung, Typ, Steuersatz, Geltungszeitraum und Matcher-Anzahl
- [x] Neue Leistung anlegen: Name, Beschreibung, Service-Typ, Steuersatz, valid_from, valid_to
- [x] Matcher hinzufügen, bearbeiten und löschen: Pattern-Typ klar als String oder Regex erkennbar; Regex-Fehler inline sichtbar
- [x] Basisleistung ist visuell als Basisleistung markiert; Name nicht editierbar, Löschen und Matcher-Aktionen sind deaktiviert
- [x] Änderungen an Leistung oder Matchern zeigen nach Speichern einen Hinweis, dass Revalidierungsvorschläge erzeugt wurden

## Aktueller Stand 2026-04-11

- Vorhanden: eigener Screen unter `/partners/:id/services` mit Verlinkung aus der Partnerdetailseite.
- Vorhanden: Leistungen anlegen, bearbeiten und löschen inklusive `valid_from` und `valid_to`.
- Vorhanden: Basisleistung ist markiert, Name bleibt read-only, Löschen und Matcher sind gesperrt.
- Vorhanden: Matcher können pro Nicht-Basisleistung angelegt, bearbeitet und gelöscht werden; String und Regex sind klar gekennzeichnet.
- Vorhanden: Backend-Regex-Fehler werden inline im Screen sichtbar gemacht.
- Vorhanden: Nach Änderungen an Leistungen oder Matchern wird ein Hinweis auf die Review-Queue angezeigt.

## Konkretes Implementierungspaket 2026-04-11

### Zielbild

- Ein eigener Screen unter `/partners/:id/services` wird ergänzt und von der Partnerdetailseite aus verlinkt.
- Der Screen zeigt alle Leistungen inklusive Basisleistung, Geltungszeitraum und Matcher-Anzahl.
- Nicht-Basisleistungen können vollständig angelegt, bearbeitet und gelöscht werden.
- Matcher können pro Leistung angelegt, bearbeitet und gelöscht werden; String und Regex sind klar unterscheidbar.
- Nach jeder Änderung an Leistung oder Matchern erscheint ein sichtbarer Hinweis auf neu erzeugte Revalidierungs-Vorschläge.

### Umsetzungsschnitt

1. **Routing und Screen-Zuschnitt**
	- Neue Route `/partners/:partnerId/services`
	- Neue Seite `ServiceManagementPage` statt weiterer Aufblähung von `PartnerDetailPage`
	- Link oder Secondary Action von der Partnerdetailseite zur Service-Verwaltung
2. **API-Client vervollständigen**
	- `frontend/src/api/services.ts` erweitern um `updateService`, `deleteService`, `createMatcher`, `updateMatcher`, `deleteMatcher`
	- Response-Typen um `matchers` konsistent abbilden
3. **Service-CRUD im UI**
	- Formular für Anlegen/Bearbeiten mit `name`, `description`, `service_type`, `tax_rate`, `valid_from`, `valid_to`
	- Basisleistung: Name read-only, kein Delete, keine Matcher-Aktionen
	- Nicht-Basisleistung: Edit/Delete mit Inline- oder Dialog-Bearbeitung
4. **Matcher-CRUD im UI**
	- Liste pro Leistung mit Label `String` oder `Regex`
	- Erstellen/Bearbeiten/Löschen direkt im Service-Block
	- Backend-422 für ungültige Regex inline am Formular anzeigen
5. **Revalidierungs-Hinweis**
	- Nach erfolgreichem Speichern/Löschen von Leistung oder Matcher Hinweisbanner anzeigen
	- Textlich auf Review-Queue als nächsten Prüfschritt verweisen
6. **Tests**
	- Vitest/MSW für: Laden der Leistungen inkl. Matcher-Anzahl, Bearbeiten/Löschen einer Nicht-Basisleistung, geblockte Basisleistungs-Aktionen, Matcher-CRUD, Regex-Fehleranzeige, Revalidierungs-Hinweis

### Betroffene Dateien

- `frontend/src/router/index.tsx`
- `frontend/src/api/services.ts`
- `frontend/src/pages/partners/PartnerDetailPage.tsx`
- `frontend/src/pages/partners/ServiceManagementPage.tsx` (neu)
- `frontend/src/pages/partners/ServiceManagementPage.test.tsx` (neu)

### Umsetzung in zwei Scheiben

**Scheibe A: Story-fähiger Kern**

- Route + neue Seite
- `valid_from`/`valid_to`
- Service bearbeiten/löschen
- Basisleistungs-Schutz im UI
- Revalidierungs-Hinweis

**Scheibe B: Matcher-Verwaltung**

- Matcher-CRUD
- String/Regex-Kennzeichnung
- Inline-Regex-Fehler
- Matcher-Anzahl in der Liste

### Abnahmehinweis

- Umsetzung für Scheibe A und Scheibe B abgeschlossen.
- Fokussierte Frontend-Validierung: `npx vitest run src/pages/partners/PartnerDetailPage.test.tsx src/pages/partners/ServiceManagementPage.test.tsx`

## Dependencies

### Requires
- 005-partner-screens.md
- 008-service-management/001-service-crud.md
- 008-service-management/002-service-matchers.md
- 008-service-management/003-base-service-protection.md
