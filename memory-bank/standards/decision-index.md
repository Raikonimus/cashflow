---
last_updated: 2026-04-08T16:00:00Z
total_decisions: 17
---

# Decision Index

This index tracks all Architecture Decision Records (ADRs) created during Construction bolts.
Use this to find relevant prior decisions when working on related features.

## How to Use

**For Agents**: Scan the "Read when" fields below to identify decisions relevant to your current task. Before implementing new features, check if existing ADRs constrain or guide your approach. Load the full ADR for matching entries.

**For Humans**: Browse decisions chronologically or search for keywords. Each entry links to the full ADR with complete context, alternatives considered, and consequences.

---

## Decisions

### ADR-017: Audit-Log schreibt Login, Logout und Imports
- **Status**: accepted
- **Date**: 2026-04-08
- **Bolt**: Post-MVP Improvement
- **Summary**: `auth.login`, `auth.logout` (via neuem `POST /auth/logout`-Endpoint) und `import.completed`/`import.failed` werden in `audit_log` geschrieben. Admin-Logins haben `mandant_id=NULL` (kein fester Mandant); die `list_by_mandant`-Query schließt NULL-Einträge ein. `audit_log.mandant_id` wurde nullable gemacht (Migration 015).
- **Read when**: Audit-Log-Abfragen; Login/Logout-Implementierung; neue Events die geloggt werden sollen; Mandantenfilterung von System-Events

### ADR-016: Partner display_name als optionaler Anzeigename
- **Status**: accepted
- **Date**: 2026-04-08
- **Bolt**: Post-MVP Improvement
- **Summary**: Partner haben ein optionales `display_name`-Feld (Migration 014). Wird `display_name` gesetzt, ersetzt es `name` in allen Anzeigen, Suchen und Sortierungen (via `COALESCE(display_name, name)`). Inline-Edit direkt in der PartnerDetailPage. Nicht im Import-Mapping.
- **Read when**: Partner-Listen-Queries; Merge-Dialog-Suche; Journal-Partner-Anzeige; Export nach display_name sortieren

### ADR-015: SQLite als MVP-Datenbank, PostgreSQL als Produktions-Ziel
- **Status**: accepted
- **Date**: 2026-04-08
- **Summary**: Entwicklung und MVP laufen auf SQLite + aiosqlite (kein Docker erforderlich). asyncpg ist als Dependency vorbereitet. Migrationen verwenden `batch_alter_table` für SQLite-Kompatibilität. Wechsel auf PostgreSQL: nur `DATABASE_URL` ändern.
- **Read when**: Neue Migrationen schreiben (batch_alter_table!); Deployment-Planung; Entscheidung ob PostgreSQL-spezifische Features nutzbar

### ADR-014: ReviewItem-Status präzisiert — confirmed und adjusted statt resolved
- **Status**: accepted
- **Date**: 2026-04-07
- **Bolt**: 008-review-queue (Review Queue)
- **Path**: `bolts/008-review-queue/adr-014-review-status-confirmed-adjusted.md`
- **Summary**: ADR-012's `resolved`-Status wird durch `confirmed` (automatische Zuordnung war korrekt, IBAN wird registriert) und `adjusted` (korrigiert: Reassign oder neuer Partner) ersetzt. Bessere Metriken, konsistent mit ADR-013. Kein Schema-Breaking-Change.
- **Read when**: Queries auf `review_items`; Metriken; Frontend Review-Queue-Ansicht; spätere Status-Erweiterungen

### ADR-013: Confirm registriert IBAN automatisch in partner_ibans
- **Status**: accepted
- **Date**: 2026-04-07
- **Bolt**: 008-review-queue (Review Queue)
- **Path**: `bolts/008-review-queue/adr-013-confirm-registers-iban.md`
- **Summary**: Bei `POST /{item_id}/confirm` wird `journal_line.partner_iban_raw` normalisiert und als neuer `PartnerIban`-Eintrag gespeichert (wenn noch nicht vorhanden). Nur bei Confirm, nicht bei Reassign/NewPartner. Verhindert wiederholte Review-Arbeit für dieselbe IBAN.
- **Read when**: `008-review-queue`-Implementierung (confirm-Aktion); Tests nach Confirm ob IBAN registriert; Frontend zeigt Confirm-Aktion

### ADR-012: ReviewItem-Status-Lifecycle (open → resolved)
- **Status**: accepted
- **Date**: 2026-04-07
- **Bolt**: 007-partner-matching (Partner Matching)
- **Path**: `bolts/007-partner-matching/adr-012-review-item-status-lifecycle.md`
- **Summary**: `review_items` hat zwei Status-Werte: `open` (Anlage durch Matching) und `resolved` (manuell durch Accountant). Kein automatisches Auflösen. `resolved`-Items bleiben für Audit-Nachvollziehbarkeit in der DB. `008-review-queue`-Bolt setzt den Lifecycle um.
- **Read when**: `008-review-queue`-Implementierung; Queries auf offene Review-Items; Frage ob automatisches Auflösen möglich; Auditlog-Anforderungen für Review-Entscheidungen

### ADR-011: Partner-Matching filtert inaktive Partner aus
- **Status**: accepted
- **Date**: 2026-04-07
- **Bolt**: 007-partner-matching (Partner Matching)
- **Path**: `bolts/007-partner-matching/adr-011-matching-ignores-inactive-partners.md`
- **Summary**: IBAN- und Name-Lookup beim Import filtern auf `Partner.is_active=True`. Inaktive Partner (nach Merge oder Deaktivierung) erzeugen keinen Treffer; Fallback auf Name-Match oder Neu-Anlage. Konsistent mit ADR-006 und ADR-009.
- **Read when**: Import-Matching-Implementierung; Queries auf `partner_ibans`/`partner_names`; Frage ob deaktivierte Partner in Matching eingehen; `008-review-queue`-Bolt

### ADR-010: CSV-Import ist synchron (kein Background-Job) für MVP
- **Status**: accepted
- **Date**: 2026-04-06
- **Bolt**: 006-import-core (Import Core)
- **Path**: `bolts/006-import-core/adr-010-sync-import-mvp.md`
- **Summary**: CSV-Import verarbeitet Dateien synchron im HTTP-Request (kein Celery/ARQ). 10-MB-Limit pro Datei begrenzt den schlimmsten Fall. `ImportRun.status`-Maschine ist bereits für spätere Async-Migration vorbereitet. Gegensatz: ADR-007 (Remapping → async) betrifft alle historischen Zeilen.
- **Read when**: Hinzufügen von Background-Jobs/Task-Queue; Skalierungsprobleme mit Upload; Frontend implementiert Upload-Fortschrittsanzeige; andere Long-Running-Operations synchron vs. asynchron

### ADR-009: Partner-Merge deaktiviert Source (Soft-Delete, kein Hard-Delete)
- **Status**: accepted
- **Date**: 2026-04-06
- **Bolt**: 005-partner-merge (Partner Merge)
- **Path**: `bolts/005-partner-merge/adr-009-merge-soft-delete-source.md`
- **Summary**: Nach einem Merge wird der Source-Partner nicht gelöscht, sondern mit `is_active=false` deaktiviert. Referenzielle Integrität (journal_lines FK) und Audit-Log-Konsistenz bleiben gewahrt. Konsistent mit ADR-006 (Soft-Deaktivierung). Reversibel.
- **Read when**: Partner-Listen-Queries (is_active-Filter!); Import-Matching (inaktive ignorieren); Re-Aktivierungs-Feature; Datenbankbereinigung/Archivierung; neue Queries die auf partners joinen

### ADR-008: Partner-IBAN ist global unique (nicht pro Mandant)
- **Status**: accepted
- **Date**: 2026-04-06
- **Bolt**: 004-partner-management (Partner Core)
- **Path**: `bolts/004-partner-management/adr-008-iban-global-unique.md`
- **Summary**: Eine IBAN identifiziert weltweit eindeutig ein Bankkonto. `partner_ibans.iban` hat einen globalen UNIQUE-Constraint (kein Compound-Key mit mandant_id). Import-Matching ist deterministisch — eine IBAN gehört immer genau einem Partner.
- **Read when**: Import-Matching-Implementierung; IBAN-Lookups; Multi-Tenancy-Fragen zu geteilten Stammdaten; Entscheidung ob andere Entities globale Uniqueness brauchen

### ADR-007: Remapping-Trigger gibt 202 Accepted zurück (Async Placeholder)
- **Status**: accepted
- **Date**: 2026-04-06
- **Bolt**: 003-tenant-account-mgmt (Tenants & Accounts)
- **Path**: `bolts/003-tenant-account-mgmt/adr-007-remapping-async-202.md`
- **Summary**: Re-Matching tausender Buchungen kann Minuten dauern — synchrones Blocking würde HTTP-Timeouts auslösen. `POST /accounts/{id}/remap` gibt sofort 202 Accepted zurück. In diesem Bolt: Placeholder (Log + 202). Echte Job-Queue in späterem Bolt.
- **Read when**: Implementierung von Long-Running-Operations; Bulk-Operationen die synchron vs. asynchron sein sollen; Hinzufügen von Job-Queue-Infrastruktur; Frontend implementiert Remapping-Status-Polling

### ADR-006: Mandant-Deaktivierung als Soft Cascade (is_active=False)
- **Status**: accepted
- **Date**: 2026-04-06
- **Bolt**: 003-tenant-account-mgmt (Tenants & Accounts)
- **Path**: `bolts/003-tenant-account-mgmt/adr-006-soft-deactivation-cascade.md`
- **Summary**: Mandant-Deaktivierung löscht keine Daten. `Mandant.is_active=False` kaskadiert via Service (nicht DB-Trigger) auf alle zugehörigen Accounts. Daten bleiben erhalten; Deaktivierung ist reversibel. Re-Aktivierung setzt Accounts NICHT automatisch aktiv (explizite Admin-Aktion nötig).
- **Read when**: Mandant-Deaktivierung oder -Löschung; Prüfung von inaktiven-Mandant-Access-Checks; Import-Jobs die Account-Aktivierungs-Status prüfen; Re-Aktivierungs-Feature

### ADR-005: Dev-Seed setzt Passwort direkt (bypasses Invitation Flow)
- **Status**: accepted
- **Date**: 2026-04-06
- **Bolt**: 002-identity-access (User Management)
- **Path**: `bolts/002-identity-access/adr-005-dev-seed-bypass-invitation.md`
- **Summary**: Der normale User-Lifecycle erfordert einen Invitation-Flow zum Passwort-Setzen. `seed.py` setzt `password_hash` direkt (bcrypt) ohne Einladungs-Token und E-Mail — ein dev-only Shortcut, der nur wenn `ENV != production` läuft.
- **Read when**: Implementierung von Scripts die User direkt anlegen; Hinzufügen von Seed-/Fixture-Scripts; Frage ob password_hash direkt gesetzt werden darf; Code-Reviews die direktes Passwort-Setzen enthalten

### ADR-004: User-Anlage nicht rückgängig bei SMTP-Fehler
- **Status**: accepted
- **Date**: 2026-04-06
- **Bolt**: 002-identity-access (User Management)
- **Path**: `bolts/002-identity-access/adr-004-user-creation-smtp-failure.md`
- **Summary**: SMTP ist kein transaktionaler Dienst. Bei Einladungs-E-Mail-Fehler bleibt der User in der DB; SMTP-Fehler werden geloggt. Admin kann Einladung über Resend-Endpoint neu auslösen.
- **Read when**: Implementierung von Flows die DB-Writes und E-Mail kombinieren; Frage ob E-Mail-Fehler einen Rollback auslösen sollen; Hinzufügen von Notification-Features; Entscheidung ob Outbox-Pattern benötigt wird

### ADR-003: Reset-Token und Invitation-Token als SHA-256-Hash speichern
- **Status**: accepted
- **Date**: 2026-04-06
- **Bolt**: 001-identity-access (Auth Foundation)
- **Path**: `bolts/001-identity-access/adr-003-token-hash-storage.md`
- **Summary**: Privilegierte Einmal-Tokens (Reset, Invitation) sind in der DB einem DB-Dump-Risiko ausgesetzt. SHA-256-Hash des Raw-Tokens speichern; Raw-Token nur per E-Mail an User senden, nie persistieren.
- **Read when**: Implementierung von Token-basierten Flows (Passwort-Reset, Einladungen, Magic Links, E-Mail-Verifikation); Hinzufügen neuer Token-Typen in der DB; Security-Reviews von Credential-Speicherung

### ADR-002: Kein Refresh-Token im MVP
- **Status**: accepted
- **Date**: 2026-04-06
- **Bolt**: 001-identity-access (Auth Foundation)
- **Path**: `bolts/001-identity-access/adr-002-no-refresh-token-mvp.md`
- **Summary**: JWT-Auth mit kurzem Access-Token-TTL ist für eine interne Business-App im MVP ausreichend. Kein Refresh-Token-Mechanismus — User muss sich nach TTL-Ablauf neu einloggen.
- **Read when**: Implementierung von Frontend-Auth-Flows oder Token-Refresh-Logik; Entscheidung ob Silent-Refresh oder Axios-Interceptor nötig; Planung von "Remember me"-Features oder Session-Verlängerung

### ADR-001: Client-only Logout ohne Token-Blacklisting
- **Status**: accepted
- **Date**: 2026-04-06
- **Bolt**: 001-identity-access (Auth Foundation)
- **Path**: `bolts/001-identity-access/adr-001-client-only-logout.md`
- **Summary**: Logout in einer JWT-basierten App erfordert eine Entscheidung über Token-Invalidierung. Logout ist rein clientseitig (Token aus Browser-Speicher löschen) ohne Server-seitiges Blacklisting.
- **Read when**: Implementierung von Logout-Endpoints oder Logout-UI; Planung von "Force Logout All Devices"-Features; Hinzufügen von Redis oder Session-Store; Security-Anforderungen rund um kompromittierte Tokens
