---
intent: 001-cashflow-core
phase: inception
status: complete
created: 2026-04-06T00:00:00Z
updated: 2026-04-10T00:00:00Z
---

# Requirements: Cashflow Core

## Intent Overview

Ein mandantenfähiges Web-Service, das Buchungszeilen aus Bankkonten und Kreditkarten (CSV-Export) importiert, automatisch Partnerunternehmen erkennt und zuordnet sowie eine vollständige Übersicht über alle Transaktionen bietet. Der Fokus liegt auf strukturiertem Import, intelligentem Partner-Matching und einem Review-Workflow für automatische Entscheidungen mit Unsicherheit.

## Business Goals

| Goal | Success Metric | Priority |
|------|----------------|----------|
| Buchungszeilen aus CSV-Exporten verschiedenster Quellen importieren | Import läuft ohne manuelle Datenvorbereitung durch | Must |
| Partner automatisch erkennen und zuordnen | > 90 % der Buchungszeilen erhalten beim Import einen Partner | Must |
| Qualität der automatischen Entscheidungen sicherstellen | Review-Queue zeigt alle unsicheren Zuordnungen; Fehlerrate < 5 % nach Review | Must |
| Vollständige Nachvollziehbarkeit aller Nutzeraktionen | Audit-Log deckt 100 % der schreibenden Aktionen ab | Must |
| Mehrmandantenfähigkeit mit Rollentrennung | Mandant A kann nie Daten von Mandant B sehen | Must |

---

## Datenmodell (Datenbankstruktur)

### Kernentitäten

```
mandants
  id, name, created_at, updated_at

users
  id, email, password_hash (nullable -- null bis Einladung angenommen),
  role (admin|mandant_admin|accountant|viewer),
  is_active, created_at, updated_at

user_invitations
  id, user_id (FK users), token_hash, expires_at,
  accepted_at (nullable -- null = noch offen),
  created_at

mandant_users                          -- Zuweisung User ↔ Mandant (außer Admin)
  mandant_id, user_id, created_at, updated_at

audit_logs
  id, user_id, mandant_id?, action, entity_type, entity_id,
  old_value (JSONB), new_value (JSONB), ip_address, created_at

accounts                               -- Konten/Kreditkarten eines Mandanten
  id, mandant_id, name, description,
  account_type (bankkonto|kreditkarte|sonstige),
  created_at, updated_at

column_mappings                        -- CSV-Spaltenmapping pro Konto
  id, account_id, source_column, target_column,
  sort_order,                          -- für Mehrfach-Mapping (Reihenfolge bei Concat)
  created_at, updated_at
  -- target_column ∈ {valuta_date, booking_date, text, partner_name, partner_iban,
  --                   amount, currency, unused}
  -- mehrere source_columns → gleicher target_column werden mit \n verbunden
  -- "unused" markiert Spalten, für die eine bewusste Entscheidung getroffen wurde
  -- Implementiert als JSON-Array column_assignments in column_mapping_configs
  -- Geführte UI: CSV-Upload → Spalten erkennen → Dropdown-Zuordnung pro Spalte

import_runs
  id, account_id, user_id, filename, row_count, skipped_count,
  status (pending|completed|failed),
  created_at, updated_at

partners
  id, mandant_id, created_at, updated_at

partner_names
  id, partner_id, name, created_at    -- alle bekannten Namensvarianten

partner_ibans
  id, partner_id, iban, created_at    -- alle bekannten IBANs

partner_name_patterns
  id, partner_id, pattern, pattern_type (string|regex),
  created_at, updated_at             -- manuelle Zuordnungsregeln

journal_lines
  id, account_id, import_run_id, partner_id (nullable),
  service_id (FK services, nullable),         -- zugeordnete Leistung
  service_assignment_mode (auto|manual, nullable),
  valuta_date, booking_date, text,
  partner_name_raw, partner_iban_raw,
  amount, currency,
  unmapped_data (JSONB),              -- alle Spalten ohne Mapping
  created_at, updated_at

  services                               -- Leistungen eines Partners
  id, partner_id (FK partners),
  name,                                -- bei Basisleistung unveränderlich
  description (nullable),
  service_type (customer|supplier|employee|authority|unknown),
  tax_rate (numeric, Prozent),         -- Standard: 20 % für customer/supplier/unknown; 0 % für employee/authority
  valid_from (date, nullable),         -- Geltungszeitraum Start (inklusiv)
  valid_to (date, nullable),           -- Geltungszeitraum Ende (inklusiv)
  is_base_service (bool),              -- true = Basisleistung; nie löschbar, Name nie änderbar
  service_type_manual (bool),          -- true = manuell gesetzt oder freigegeben; sperrt Auto-Override
  tax_rate_manual (bool),              -- true = manuell gesetzt oder freigegeben; sperrt Auto-Override
  created_at, updated_at

  service_matchers                     -- Matcher-Regeln einer Leistung (kein Eintrag für Basisleistung)
  id, service_id (FK services),
  pattern,                             -- String oder RegEx-Ausdruck
  pattern_type (string|regex),
  created_at, updated_at

  service_type_keywords                -- Konfigurierbare Begriffe für automatische Service-Typ-Ermittlung
  id, mandant_id (FK mandants, nullable -- null = systemweite Vorgabe),
  pattern,
  pattern_type (string|regex),
  target_service_type (employee|authority),
  created_at, updated_at

  review_items
  id, mandant_id, item_type,          -- partner_name_match | service_assignment | service_type_review
  journal_line_id (FK journal_lines, nullable), -- gesetzt bei partner_name_match + service_assignment
  service_id (FK services, nullable), -- gesetzt bei service_type_review
  context (JSONB),                    -- Details je Typ (s. FR-8, FR-18, FR-19)
  status (pending|confirmed|adjusted|rejected),
  resolved_by_user_id (nullable),
  resolved_at (nullable),
  created_at, updated_at
```

---

## Functional Requirements

### FR-1: Authentifizierung & Session-Management
- **Description**: Nutzer können sich mit E-Mail + Passwort einloggen. JWT-Token wird ausgestellt. Bei mehreren zugewiesenen Mandanten wählt der Nutzer nach dem Login einen Mandanten aus. Passwort-Vergessen-Funktion sendet Reset-Link per E-Mail. Neu angelegte Nutzer erhalten eine Einladungsmail mit zeitlich begrenztem Link zum Festlegen des Passworts (kein initiales Passwort durch den Admin).
- **Acceptance Criteria**:
  - Login gibt JWT zurück (Ablaufzeit konfigurierbar)
  - Nutzer mit > 1 Mandant erhält nach Login Mandanten-Auswahl
  - Passwort-Reset-Mail wird innerhalb von 30 s verschickt; Link ist 1 h gültig
  - Fehlgeschlagene Logins werden ins Audit-Log geschrieben
  - Neuer Nutzer erhält Einladungsmail automatisch bei Anlage; Einladung ist `INVITATION_EXPIRE_DAYS` Tage gültig (Default: 7)
  - Nutzer mit offener Einladung können sich nicht einloggen (kein Passwort gesetzt)
  - Admin/Mandant-Admin kann Einladung erneut versenden
- **Priority**: Must

### FR-2: Benutzerverwaltung mit rollenbasiertem Zugriff
- **Description**: Vier Rollen mit abgestuften Rechten:
  - **Admin**: Vollzugriff auf alle Mandanten, alle User
  - **Mandant-Admin**: Vollzugriff auf zugewiesene Mandanten; darf nur Accountants & Viewer verwalten (kann keine weiteren Mandant-Admins anlegen)
  - **Accountant**: Import und Datenpflege für zugewiesene Mandanten
  - **Viewer**: Nur-Lesen für zugewiesene Mandanten
- **Acceptance Criteria**:
  - Admin kann beliebigen User mit beliebiger Rolle anlegen/deaktivieren
  - Mandant-Admin kann nur Accountant und Viewer in seinen Mandanten anlegen/ändern/deaktivieren; 403 beim Versuch Mandant-Admin oder Admin anzulegen
  - Viewer erhält 403 auf alle schreibenden Endpunkte
  - Mandantenzugriff wird bei jedem Request serverseitig geprüft
- **Priority**: Must

### FR-3: Mandanten- & Kontoverwaltung
- **Description**: Mandanten (Unternehmen) können verwaltet werden. Jeder Mandant hat n Konten (Bankkonten, Kreditkarten, Sonstige). Konten haben Namen, Beschreibung und Typ.
- **Acceptance Criteria**:
  - Mandanten: Anlegen, Bearbeiten, Deaktivieren
  - Konten: Anlegen, Bearbeiten, Löschen (nur wenn keine Buchungszeilen vorhanden)
  - Kontotyp muss einer der drei definierten Typen sein
- **Priority**: Must

### FR-4: CSV-Spalten-Mapping pro Konto
- **Description**: Jedes Konto hat ein Mapping von CSV-Quellspalten auf interne Zielspalten. Mehrere Quellspalten können auf dieselbe Zielspalte gemappt werden (Inhalt wird mit Newline verbunden). Das Mapping wird beim ersten Import eines neuen Kontos definiert. Später kann es angepasst werden.
- **Acceptance Criteria**:
  - Mapping-Editor zeigt CSV-Quellspalten (aus hochgeladenem File) und Zielspalten
  - Drag & Drop oder Dropdown-Auswahl für Zuordnung
  - Mehrfach-Mapping auf gleiche Zielspalte möglich, mit definierbarer Reihenfolge
  - Bei Mapping-Änderung: optionale Neuverarbeitung aller bisherigen Buchungszeilen des Kontos
  - Quellspalten ohne Mapping werden im `unmapped_data`-JSONB-Feld gespeichert
- **Priority**: Must

### FR-5: CSV-Import von Buchungszeilen
- **Description**: Accountant lädt eine oder mehrere CSV-Dateien für ein Konto hoch. Das System wendet das bestehende Mapping an, erkennt Partner und legt Buchungszeilen an.
- **Acceptance Criteria**:
  - Drag & Drop Upload im Browser (einzelne oder mehrere CSV-Dateien)
  - Upload-Dialog erfordert Auswahl eines bestehenden Kontos oder Anlage eines neuen
  - Bei fehlendem Mapping wird der Nutzer zum Mapping-Editor weitergeleitet
  - Import-Run wird mit User, Datum, Dateiname, Zeilenanzahl gespeichert
  - Dubletten werden erkannt und übersprungen: eine Zeile gilt als Dublette wenn `(account_id, valuta_date, booking_date, amount, partner_iban_raw, partner_name_raw)` bereits für diesen Mandanten existiert; wird als `skipped` im ImportRun gezählt, nicht als Fehler
- **Priority**: Must

### FR-6: Automatische Partner-Erkennung beim Import
- **Description**: Zu jeder Buchungszeile wird ein Partner ermittelt. Zuordnungslogik (in Reihenfolge):
  1. IBAN der Buchungszeile trifft auf bekannte `partner_ibans` → Partner zugeordnet (sicher)
  2. Keine IBAN-Treffer, aber Name exakt in `partner_names` → Partner zugeordnet + Review-Item (Typ: partner_name_match) wenn IBAN der Zeile noch nicht in `partner_ibans` des Partners
  3. Kein Treffer → Neuer Partner angelegt mit diesem Namen und ggf. dieser IBAN
- **Acceptance Criteria**:
  - Buchungszeilen mit bekannter IBAN erhalten sofort den richtigen Partner (kein Review-Item)
  - Buchungszeilen mit neuem Namen, aber exakter Namensübereinstimmung → Review-Item wird erzeugt
  - Buchungszeilen ohne jeden Treffer → neuer Partner, kein Review-Item
  - Nach Import: `partner_id` in `journal_lines` gesetzt (oder null wenn kein Treffer)
- **Priority**: Must

### FR-7: Partner-Stammdatenverwaltung
- **Description**: Partner haben mehrere IBANs und mehrere Namensvarianten. Manuell können String- oder Regex-Muster als Erkennungsregeln definiert werden. Partner können manuell mit einem anderen Partner zusammengefasst werden.
- **Acceptance Criteria**:
  - Partnerdetail-Ansicht zeigt alle IBANs, Namensvarianten und Muster
  - Neue IBAN / neuer Name manuell hinzufügbar
  - Regex-Muster werden vor Speicherung auf Gültigkeit geprüft
  - Zusammenfassen: Alle Buchungszeilen des aufgelösten Partners werden auf den Ziel-Partner umgeschrieben; aufgelöster Partner wird deaktiviert (nicht gelöscht)
  - Zusammenfassen ist ins Audit-Log geschrieben
- **Priority**: Must

### FR-8: Review Queue
- **Description**: Die Review-Queue listet automatische Entscheidungen mit Unsicherheit. Aktuell ein Typ: `partner_name_match` (Partner wurde per Namensgleichheit — nicht IBAN — zugeordnet, neue IBAN). Jeder Eintrag kann bestätigt, angepasst (anderer Partner) oder als neuer Partner markiert werden.
- **Acceptance Criteria**:
  - Review-Queue zeigt alle `pending` Items sortiert nach Erstellungsdatum
  - `partner_name_match`: zeigt Buchungszeile, zugeordneten Partner, Grund der Zuordnung
  - Aktionen: „Bestätigen" (Status → confirmed), „Anderer Partner" (Dropdown), „Neuer Partner"
  - Nach Entscheidung: `journal_line.partner_id` wird aktualisiert; Item-Status auf `confirmed`/`adjusted`

- **Priority**: Must

### FR-9: Buchungszeilen-Anzeige mit Filtern
- **Description**: Alle Nutzer können Buchungszeilen ihres Mandanten einsehen, mit Filtern nach Jahr, Monat, Konto, Partner, und mehr.
- **Acceptance Criteria**:
  - Filter: Jahr, Monat/Jahr, Konto, Partner, Status (mit/ohne Partner)
  - Paginierung oder virtuelles Scrolling für große Datenmengen
  - Spalten: Valutadatum, Buchungsdatum, Text, Partner, IBAN, Betrag, Währung, Konto
  - Viewer hat nur Lesezugriff; keine Bulk-Aktionen
- **Priority**: Must

### FR-10: Bulk-Operationen auf Buchungszeilen
- **Description**: Accountant und Admin können mehrere Buchungszeilen gleichzeitig einem anderen Partner zuweisen.
- **Acceptance Criteria**:
  - Mehrfachauswahl in der Buchungszeilen-Ansicht
  - Bulk-Aktion: Partner zuweisen (Autocomplete-Suche)
  - Änderungen werden in Audit-Log festgehalten
- **Priority**: Should

### FR-11: Audit-Log
- **Description**: Alle schreibenden Nutzeraktionen und Logins werden protokolliert. Einträge sind unveränderlich.
- **Acceptance Criteria**:
  - Jeder Login (erfolgreich und fehlgeschlagen) wird geloggt
  - Jede CREATE/UPDATE/DELETE-Aktion auf Entities wird geloggt mit old/new Value
  - Audit-Log ist im UI für Admin und Mandant-Admin einsehbar
  - Audit-Log-Einträge können nicht gelöscht oder bearbeitet werden
- **Priority**: Must

---

## Leistungsmanagement

**Implementierungsstand 2026-04-11**

- Backend-seitig sind Service-CRUD, Basisleistung-Schutz, automatische/manuelle Zuordnung, Revalidierung, Service-Type-Detection und Review-Typen weitgehend vorhanden.
- Im Frontend sind Partnerdetail, dedizierte Service-Verwaltung inklusive Matcher-CRUD, Keyword-Konfiguration in den Einstellungen, Review-Queue, Service-Type-Review, Archiv und die deduplizierte Service-Typ-Anzeige in der Partnerliste vorhanden.
- Für FR-17 und FR-22 bestehen aktuell keine bekannten UI-Lücken mehr.

**Priorisiertes Rest-Backlog 2026-04-11**

Kein offenes Rest-Backlog aus dem Audit von `intent.2.txt`.

### FR-12: Leistungs-Stammdatenverwaltung
- **Description**: Zu jedem Partner existiert eine unveränderliche Basisleistung (is_base_service = true), die automatisch beim Anlegen eines Partners erzeugt wird. Darüber hinaus können beliebig viele weitere Leistungen angelegt werden. Jede Leistung hat: Name, Beschreibung, Service-Typ (customer | supplier | employee | authority | unknown), Steuersatz (%), optionalen Geltungszeitraum (valid_from, valid_to, jeweils inklusiv). Die Basisleistung ist nicht löschbar, ihr Name ist nicht änderbar und sie besitzt keine Matcher. Beim Anlegen, Ändern oder Löschen einer Leistung werden alle Buchungszeilen des betroffenen Partners neu validiert; die Revalidierung erzeugt ausschließlich Vorschläge und speichert keine neue Zuordnung automatisch.
- **Acceptance Criteria**:
  - Beim Anlegen eines Partners wird automatisch eine Basisleistung erstellt
  - Basisleistung ist nicht löschbar (HTTP 409 bei Versuch)
  - Name der Basisleistung ist nicht änderbar (HTTP 422 bei Versuch)
  - Basisleistung besitzt keine Matcher; Anlegen eines Matchers für die Basisleistung wird abgelehnt (HTTP 422)
  - Leistungen können angelegt, bearbeitet (außer Basisleistung-Name) und gelöscht werden
  - Service-Typ-Enum: customer, supplier, employee, authority, unknown
  - Beim Anlegen/Ändern/Löschen einer Leistung: Revalidierung aller Buchungszeilen des betroffenen Partners (→ FR-14)
  - Revalidierung erzeugt ausschließlich Vorschläge im UI und überschreibt keine bestehende Zuordnung automatisch
- **Priority**: Must

### FR-13: Service Matcher
- **Description**: Für jede (Nicht-Basis-)Leistung können Matcher-Regeln gepflegt werden. Jeder Matcher ist entweder ein case-insensitiver Contains-String oder ein regulärer Ausdruck (RegEx). Matcher werden gegen den Buchungszeilentext und den Partnernamen geprüft. RegEx-Ausdrücke werden beim Speichern auf syntaktische Korrektheit validiert. Im UI sind String- und Regex-Matcher klar unterscheidbar (z. B. durch Icon oder Label).
- **Acceptance Criteria**:
  - Matcher können für eine Leistung angelegt, bearbeitet und gelöscht werden
  - `pattern_type` ∈ {string, regex}
  - Bei `pattern_type = regex`: Syntaxprüfung vor dem Speichern; bei ungültigem Ausdruck HTTP 422 mit Fehlerbeschreibung
  - String-Matcher sind case-insensitiv (Contains)
  - Änderungen an Matchern einer Leistung lösen eine Revalidierung aller Buchungszeilen des Partners aus (→ FR-14)
- **Priority**: Must

### FR-14: Automatische Leistungszuordnung beim Import
- **Description**: Nach der Partner-Erkennung (→ FR-6) wird jede Buchungszeile einer Leistung des zugeordneten Partners automatisch zugeordnet. Regeln (in Reihenfolge):
  1. Nur Leistungen des zugeordneten Partners werden berücksichtigt
  2. Die Basisleistung wird nie direkt gematcht
  3. Leistungen außerhalb des Geltungszeitraums (valid_from/valid_to, inklusiv) werden ausgeschlossen
  4. Verbleibende Leistungen: alle Matcher prüfen
  5. Genau 1 Treffer → Leistung zugeordnet (service_assignment_mode = auto)
  6. 0 Treffer → Basisleistung zugeordnet (service_assignment_mode = auto)
  7. > 1 Treffer → Basisleistung zugeordnet (service_assignment_mode = auto) + Review-Item (Typ: service_assignment) erzeugt
- **Acceptance Criteria**:
  - `journal_lines.service_id` und `service_assignment_mode` werden beim Import gesetzt
  - Basisleistung wird nie über Matcher erreicht
  - Buchungszeile wird nur Leistungen des Partners zugeordnet (Mandanten-Isolation)
  - Buchungsdatum muss innerhalb des Geltungszeitraums liegen; außerhalb → Leistung wird nicht berücksichtigt
  - Bei > 1 Treffern: Review-Item (service_assignment) mit context.matching_services = [service_id, ...]
  - Hat ein Partner noch keine Leistungen außer der Basisleistung: Buchungszeile erhält direkt die Basisleistung
- **Priority**: Must

### FR-15: Manuelle Leistungszuordnung
- **Description**: Jede Buchungszeile kann manuell einer Leistung des zugehörigen Partners zugeordnet werden. Voraussetzung: Das Buchungsdatum der Zeile liegt innerhalb des Geltungszeitraums der Leistung.
- **Acceptance Criteria**:
  - Manuelle Zuordnung setzt `service_assignment_mode = manual`
  - Bei Verletzung des Geltungszeitraums wird die Zuordnung abgelehnt (HTTP 422)
  - Nur Leistungen des Partners der Buchungszeile sind auswählbar
- **Priority**: Must

### FR-16: Revalidierung bei Matcher- oder Leistungsänderungen
- **Description**: Wenn Service Matcher eines Partners geändert werden oder Leistungen angelegt/geändert/gelöscht werden, werden alle Buchungszeilen dieses Partners erneut geprüft. Die Revalidierung erzeugt ausschließlich Vorschläge; bestehende gespeicherte Zuordnungen (auch manuelle) werden nicht automatisch geändert. Im UI werden pro betroffener Buchungszeile folgende Informationen angezeigt: bisherige Zuordnung, neu vorgeschlagene Zuordnung, Grund der Änderung. Der Nutzer kann die vorgeschlagene Änderung annehmen, ablehnen oder korrigieren (z. B. per Dropdown). Manuell festgelegte Zuordnungen werden ebenfalls angezeigt (nicht automatisch übernommen).
- **Acceptance Criteria**:
  - Revalidierung wird serverseitig ausgelöst bei Änderungen an: service_matchers, services (anlegen/ändern/löschen)
  - Bestehende service_id und service_assignment_mode werden nicht automatisch überschrieben
  - Vorschläge werden als Review-Items (Typ: service_assignment) gespeichert: context enthält current_service_id, proposed_service_id, reason (string)
  - Bei Vorschlag identisch mit aktueller Zuordnung: kein Review-Item
  - Bereits vorhandene offene Review-Items derselben Zeile werden durch neue ersetzt
- **Priority**: Must

### FR-17: Automatische Service-Typ-Ermittlung
- **Description**: Der Service-Typ einer Leistung wird, sofern er Unknown ist, automatisch ermittelt: Zunächst werden Buchungszeilen, die dieser Leistung zugeordnet sind, auf konfigurierbare Begriffe geprüft (case-insensitiv Contains oder RegEx). Begriffe sind pro Ziel-Service-Typ (employee, authority) konfigurierbar und in den Einstellungen verwaltbar. Wird kein Begriff gefunden, entscheidet der Betrag: negative oder null → supplier, positiv → customer. Sobald der Service-Typ automatisch von Unknown auf einen anderen Wert geändert wird, wird der neue Service-Typ sofort auf der Leistung gespeichert und zusätzlich ein Review-Item (Typ: service_type_review) zur Kontrolle erzeugt. Standard-Steuersatz bei automatischer Zuweisung: customer/supplier/unknown → 20 %, employee/authority → 0 %. Ein manuell gesetzter oder bereits freigegebener Service-Typ (service_type_manual = true) wird nicht automatisch überschrieben. Ein manuell geänderter oder bereits freigegebener Steuersatz (tax_rate_manual = true) wird nicht automatisch gesetzt.
- **Acceptance Criteria**:
  - Automatische Ermittlung nur wenn `service_type = unknown` und `service_type_manual = false`
  - Keyword-Liste ist pro Mandant konfigurierbar (Einstellungen), Fallback auf systemweite Vorgaben
  - Keyword-Prüfung: pattern_type ∈ {string, regex}; Regex wird vor Speichern auf Syntax geprüft
  - Betrag-Fallback: amount < 0 oder amount = 0 → supplier; amount > 0 → customer
  - Automatische Änderung setzt `service_type` sofort auf den ermittelten Wert und erzeugt zusätzlich ein Review-Item (service_type_review) pro Leistung
  - Bei `service_type_manual = true`: keine automatische Änderung, kein Review-Item
  - Standard-Steuersatz wird nur gesetzt wenn `tax_rate_manual = false`
- **Priority**: Must

### FR-18: Review-Inbox – Service-Type-Review
- **Description**: Ein Service-Type-Review-Eintrag entsteht, wenn der Service-Typ einer Leistung automatisch geändert wurde (→ FR-17). Pro Leistung existiert genau ein offener Eintrag. Der Nutzer sieht: den aktuell automatisch gesetzten Service-Typ, die Begründung und alle aktuell dieser Leistung zugeordneten Buchungszeilen. Er kann den Service-Typ korrigieren, den Steuersatz anpassen und den Eintrag freigeben. Mit Freigabe wird die aktuelle Festlegung bestätigt; `service_type_manual = true` und, wenn der Steuersatz bestätigt oder angepasst wurde, `tax_rate_manual = true` gesetzt.
- **Acceptance Criteria**:
  - Review-Item (service_type_review) hat service_id; context enthält previous_type, auto_assigned_type, reason, current_journal_line_ids
  - Nur ein pending service_type_review pro Leistung; bei erneuter Auslösung wird bestehender Eintrag aktualisiert
  - Bei automatischer Änderung wird `service_type` vor Freigabe bereits auf den ermittelten Wert gesetzt
  - Freigabe-Aktion ohne Korrektur: belässt den aktuellen `service_type` und setzt `service_type_manual = true`; optional `tax_rate_manual = true`
  - Freigabe-Aktion mit Korrektur: setzt den korrigierten `service_type`, setzt `service_type_manual = true`; optional tax_rate + `tax_rate_manual = true`
  - Review-Item wechselt bei Freigabe auf status = confirmed bzw. adjusted
  - Bestätigte/korrigierte Einträge werden ins Archiv verschoben (→ FR-20)
- **Priority**: Must

### FR-19: Review-Inbox – Leistungszuordnungs-Review
- **Description**: Ein Leistungszuordnungs-Review-Eintrag entsteht bei: (a) mehr als einem Matcher-Treffer beim Import (→ FR-14) oder (b) einem Revalidierungs-Vorschlag, der von der aktuellen Zuordnung abweicht (→ FR-16). Pro Buchungszeile existiert genau ein offener Eintrag dieses Typs. Der Nutzer sieht: bisherige Zuordnung, vorgeschlagene Zuordnung, Grund. Er kann die Zuordnung bestätigen, anpassen oder ablehnen.
- **Acceptance Criteria**:
  - Review-Item (service_assignment) hat journal_line_id; context enthält current_service_id, proposed_service_id, reason
  - Nur ein pending service_assignment pro Buchungszeile; bei erneuter Auslösung wird bestehender Eintrag aktualisiert
  - Aktionen: bestätigen (→ `journal_line.service_id = proposed_service_id`; `service_assignment_mode = manual`; status = confirmed), anpassen (→ Nutzer wählt andere service_id; `service_assignment_mode = manual`; status = adjusted), ablehnen (→ keine Änderung an der gespeicherten Zuordnung; status = rejected)
  - Bestätigte, korrigierte oder abgelehnte Einträge werden ins Archiv verschoben (→ FR-20)
- **Priority**: Must

### FR-20: Review-Archiv
- **Description**: Alle bestätigten, korrigierten oder abgelehnten Review-Items (aller Typen) werden in ein Archiv verschoben. Das Archiv ist für Accountants und Admins einsehbar und wird als paginierte Liste dargestellt.
- **Acceptance Criteria**:
  - Filter: item_type, resolved_by_user_id, Zeitraum
  - Sortierung: resolved_at absteigend (Standard)
  - Paginierung: konfigurierbare Seitengröße
  - Archiv-Einträge sind nicht mehr aktionierbar
- **Priority**: Should

### FR-21: Partner-Zusammenlegung mit Leistungs-Revalidierung
- **Description**: Wenn zwei Partner zusammengelegt werden, werden alle Buchungszeilen des aufgelösten Partners dem verbleibenden Partner zugeordnet. Anschließend wird die Leistungszugehörigkeit aller betroffenen Buchungszeilen gegen die Leistungen des verbleibenden Partners neu geprüft. Die Revalidierung erzeugt ausschließlich Vorschläge; bestehende gespeicherte Leistungszuordnungen werden nicht automatisch überschrieben.
- **Acceptance Criteria**:
  - Beim Partner-Merge werden alle Buchungszeilen des aufgelösten Partners auf den verbleibenden Partner umgeschrieben
  - Nach dem Merge wird die Revalidierung für alle betroffenen Buchungszeilen ausgelöst
  - Revalidierung verwendet ausschließlich Leistungen des verbleibenden Partners
  - Abweichungen werden als `service_assignment`-Review-Items gespeichert; bestehende Zuordnungen werden nicht automatisch geändert
  - Der Merge und die daraus ausgelöste Revalidierung werden im Audit-Log festgehalten
- **Priority**: Must

### FR-22: Partnerliste mit deduplizierten Service-Typ-Icons
- **Description**: In der Partnerliste werden die Service-Typen aller Leistungen eines Partners als Icons angezeigt. Gleiche Service-Typen werden dabei zusammengefasst und nicht mehrfach dargestellt.
- **Acceptance Criteria**:
  - Für jeden Partner werden alle in dessen Leistungen vorkommenden Service-Typen als Icons angezeigt
  - Gleiche Service-Typen werden dedupliziert dargestellt
  - Die Basisleistung wird in die Icon-Ermittlung einbezogen
  - Änderungen an Service-Typen werden nach Freigabe oder manueller Änderung in der Partnerliste sichtbar
- **Priority**: Should

---

## Non-Functional Requirements

### Performance
| Requirement | Metric | Target |
|-------------|--------|--------|
| API-Antwortzeit | p95 Latenz | < 300 ms für Listenabfragen |
| Import-Durchsatz | Zeilen pro Sekunde | ≥ 500 Zeilen/s (serverseitig) |
| UI-Ladezeit | Initial Load | < 2 s |

### Scalability
| Requirement | Metric | Target |
|-------------|--------|--------|
| Buchungszeilen pro Mandant | Records | bis 500.000 ohne Performanceeinbruch |
| Gleichzeitige Nutzer | Sessions | bis 50 gleichzeitig |

### Security
| Requirement | Standard | Notes |
|-------------|----------|-------|
| Authentifizierung | JWT (Bearer) | Token-Ablauf + Refresh |
| Autorisierung | RBAC | Mandanten-Isolation serverseitig erzwungen |
| Input-Validierung | Pydantic | Alle API-Endpunkte |
| SQL Injection | SQLModel ORM | Kein Raw-SQL ohne Parameterisierung |
| Audit | Vollständig | Alle schreibenden Aktionen geloggt |

### Reliability
| Requirement | Metric | Target |
|-------------|--------|--------|
| Datenverlust | Import-Fehler | Transaktion: entweder vollständig oder rollback |
| Rückwärtskompatibilität | Mapping-Änderung | `unmapped_data` ermöglicht Re-Import ohne Datenverlust |

### Compliance
| Requirement | Standard | Notes |
|-------------|----------|-------|
| Datentrennung | Mandanten-Isolation | Kein Cross-Tenant-Datenzugriff möglich |
| Nachvollziehbarkeit | Audit-Log | Unveränderliche Aktionshistorie |

---

## Constraints

### Technische Constraints (Intent-spezifisch)
- CSV-Format variiert je Quellkonto; kein einheitliches Schema vorausgesetzt
- `unmapped_data` muss als JSONB gespeichert werden, um späteres Re-Mapping zu ermöglichen
- Partner-Matching muss innerhalb eines Mandanten-Kontexts isoliert bleiben

### Business Constraints
- Daten verschiedener Mandanten dürfen niemals vermischt werden
- Audit-Log-Einträge sind gesetzlich relevant und dürfen nicht manipulierbar sein
