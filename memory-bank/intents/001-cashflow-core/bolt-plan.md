---
intent: 001-cashflow-core
phase: inception
status: bolt-plan-ready
updated: 2026-04-15T00:00:00Z
---

# Cashflow Core – Bolt Plan

51 Stories → 15 Bolts über 8 Units.
Ausführungsreihenfolge folgt den Unit-Abhängigkeiten.

**Update 2026-04-15**: +3 Stories fuer die Einnahmen-&-Ausgaben-Jahresmatrix (Service-Gruppen, Matrix-API, UI-Screen).

---

## Unit 001: identity-access (Backend · DDD)

### Bolt 001 – Auth Foundation
**Type**: ddd-construction-bolt
**Stories**: 
- `001-login-jwt.md` (must)
- `002-password-reset.md` (must)
- `005-rbac-middleware.md` (must)

**Rationale**: JWT + RBAC-Middleware ist das Fundament aller anderen Bolts — muss zuerst fertig sein.
**Requires**: –
**Enables**: alle anderen Bolts

---

### Bolt 002 – User Management
**Type**: ddd-construction-bolt
**Stories**:
- `003-user-crud.md` (must)
- `004-mandant-user-assignment.md` (must)
- `006-user-invitation.md` (must)
- `007-dev-seed.md` (must)

**Rationale**: User-CRUD, Mandanten-Zuweisung, Einladungs-Flow und Dev-Seed gehören zur User-Domäne.
**Requires**: Bolt 001
**Enables**: Bolt 003

---

## Unit 002: tenant-account-mgmt (Backend · DDD)

### Bolt 003 – Tenants & Accounts
**Type**: ddd-construction-bolt
**Stories**:
- `001-mandant-crud.md` (must)
- `002-account-crud.md` (must)
- `003-column-mapping-config.md` (must)
- `004-remapping-trigger.md` (must)

**Rationale**: Mandanten und Konten + Mapping-Konfiguration bilden eine Einheit; können parallel zu Bolt 004 entwickelt werden.
**Requires**: Bolt 001
**Enables**: Bolt 005

---

## Unit 003: partner-management (Backend · DDD)

### Bolt 004 – Partner Core
**Type**: ddd-construction-bolt
**Stories**:
- `001-partner-crud.md` (must)
- `002-partner-iban-names.md` (must)
- `003-partner-name-patterns.md` (must)

**Rationale**: Partner-Stammdaten und Erkennungs-Infrastruktur; parallel zu Bolt 003 möglich.
**Requires**: Bolt 001
**Enables**: Bolt 005, Bolt 006

---

### Bolt 005 – Partner Merge
**Type**: ddd-construction-bolt
**Stories**:
- `004-partner-merge.md` (must)

**Rationale**: Merge ist komplex und baut auf fertigem Partner-Core auf (IBANs + Namen müssen vorhanden sein).
**Requires**: Bolt 004
**Enables**: Bolt 009 (UI)

---

## Unit 008: service-management (Backend · DDD)

### Bolt 013 – Service Core
**Type**: ddd-construction-bolt
**Stories**:
- `001-service-crud.md` (must)
- `002-service-matchers.md` (must)
- `003-base-service-protection.md` (must)
- `004-keyword-config.md` (must)
- `009-service-groups.md` (must)

**Rationale**: Service-Stammdaten, Matcher-API, Basisleistung-Schutz und Keyword-Konfiguration bilden das Fundament des Leistungsmanagements. Muss vor Import-Erweiterung (Bolt 014) fertig sein.
**Requires**: Bolt 004
**Enables**: Bolt 014, Bolt 015

---

### Bolt 014 – Service Assignment Engine
**Type**: ddd-construction-bolt
**Stories**:
- `005-service-auto-assignment.md` (must)
- `006-service-manual-assignment.md` (must)
- `007-service-revalidation.md` (must)
- `008-service-type-detection.md` (must)

**Rationale**: Auto-Zuordnung (Import), manuelle Zuordnung, Revalidierungs-Engine und Service-Typ-Ermittlung können als eine Einheit entwickelt werden; sie teilen denselben Matcher-Aufruf.
**Requires**: Bolt 013
**Enables**: Bolt 015, Bolt 007 (muss Review-Erstellung kennen)

---

## Unit 004: import-pipeline (Backend · DDD)

### Bolt 006 – Import Core
**Type**: ddd-construction-bolt
**Stories**:
- `001-csv-upload-endpoint.md` (must)
- `002-mapping-application.md` (must)
- `004-import-run-tracking.md` (must)

**Rationale**: Upload-Endpunkt und Mapping-Anwendung ohne Partner-Matching zuerst.
**Requires**: Bolt 003
**Enables**: Bolt 007

---

### Bolt 007 – Partner Matching & Service Assignment
**Type**: ddd-construction-bolt
**Stories**:
- `003-partner-matching.md` (must)
- `009-import-service-assignment.md` (must)

**Rationale**: Partner-Matching und direkt anschließende Service-Zuordnung beim Import werden im selben Bolt implementiert, da beides Schritt im Import-Prozess ist. Service-Assignment-Engine (Bolt 014) muss dafür bereits gebaut sein.
**Requires**: Bolt 006, Bolt 004, Bolt 014
**Enables**: Bolt 008, Bolt 009, Bolt 015

---

## Unit 005: review-queue (Backend · DDD)

### Bolt 008 – Review Queue
**Type**: ddd-construction-bolt
**Stories**:
- `001-review-items-list.md` (must)
- `002-review-item-confirm.md` (must)
- `003-review-item-reassign.md` (must)

**Rationale**: Alle 3 Stories sind eng verbunden (gleiche Entity); ein Bolt.
**Requires**: Bolt 007
**Enables**: Bolt 011 (UI)

---

### Bolt 015 – Review Queue Service Extensions
**Type**: ddd-construction-bolt
**Stories**:
- `004-service-assignment-review.md` (must)
- `005-service-type-review.md` (must)
- `006-review-archive.md` (should)

**Rationale**: Die neuen Review-Typen (service_assignment, service_type_review) und das Archiv erweitern die bestehende Review-Queue-Infrastruktur aus Bolt 008 und bauen auf der Service-Assignment-Engine (Bolt 014) auf.
**Requires**: Bolt 008, Bolt 014, Bolt 007
**Enables**: Bolt 012 (UI)

---

## Unit 006: journal-viewer (Backend · DDD)

### Bolt 009 – Journal & Audit
**Type**: ddd-construction-bolt
**Stories**:
- `001-journal-lines-query.md` (must)
- `002-bulk-assign-partner.md` (should)
- `003-audit-log-api.md` (must)
- `004-cashflow-matrix-api.md` (must)

**Rationale**: Query + Bulk-Assign + Audit-Log sind API-Endpunkte ohne komplexe Domänenlogik; ein Bolt.
**Requires**: Bolt 007
**Enables**: Bolt 011 (UI)

---

## Unit 007: cashflow-ui (Frontend · Simple)

### Bolt 010 – Auth UI
**Type**: simple-construction-bolt
**Stories**:
- `001-auth-screens.md` (must)

**Rationale**: Auth-Screens sind Voraussetzung für alle anderen Frontend-Bolts. Kann ab Bolt 001 parallel entwickelt werden.
**Requires**: Bolt 001
**Enables**: Bolt 011, 012

---

### Bolt 011 – Core UI (Admin + Accounts + Import)
**Type**: simple-construction-bolt
**Stories**:
- `002-admin-screens.md` (must)
- `003-account-management-screen.md` (must)
- `004-import-screen.md` (must)

**Rationale**: Diese Screens decken den primären Accountant-Workflow ab und hängen an Bolts 002, 003, 006.
**Requires**: Bolt 010, Bolt 002, Bolt 003, Bolt 006
**Enables**: Bolt 012

---

### Bolt 012 – Operations UI (Partner + Review + Journal + Services)
**Type**: simple-construction-bolt
**Stories**:
- `005-partner-screens.md` (must)
- `006-review-queue-screen.md` (must)
- `007-journal-screen.md` (must)
- `008-audit-log-screen.md` (must)
- `009-service-management-screen.md` (must)
- `010-service-type-review-screen.md` (must)
- `011-settings-keyword-config.md` (must)
- `012-income-expense-screen.md` (must)

**Rationale**: Restliche Screens; alle Backend-Bolts müssen fertig sein. Service-Screens und Einstellungen kommen hinzu.
**Requires**: Bolt 011, Bolt 005, Bolt 008, Bolt 009, Bolt 015
**Enables**: –

---

## Dependency Graph

```
Bolt 001 (Auth)
    ├──> Bolt 002 (User Mgmt)
    │         └──> Bolt 003 (Tenants+Accounts) ──> Bolt 006 (Import Core)
    │                                                       │
    ├──> Bolt 004 (Partner Core) ──> Bolt 005 ──────────────┤
    │         │                                             │
    │         └──> Bolt 013 (Service Core)                  │
    │                   └──> Bolt 014 (Service Engine) ─────┤
    │                                                        ▼
    │                                              Bolt 007 (Matching+ServiceAssign)
    │                                                   ├──> Bolt 008 (Review Queue)
    │                                                   │         └──> Bolt 015 (Review Ext.)
    │                                                   └──> Bolt 009 (Journal+Audit)
    │
    └──> Bolt 010 (Auth UI)
              └──> Bolt 011 (Core UI) ──────────────────────────────────────────┐
                        └──> Bolt 012 (Operations UI) <── Bolt 005,009,015 ─────┘
```

## Execution Schedule

| Phase | Bolts | Parallelisierbar |
|-------|-------|-----------------|
| 1 | Bolt 001 | Nein (Fundament) |
| 2 | Bolt 002, Bolt 003, Bolt 004, Bolt 010 | Ja (alle parallel) |
| 3 | Bolt 005, Bolt 006, Bolt 013 | Ja |
| 4 | Bolt 011, Bolt 014 | Ja |
| 5 | Bolt 007 | Nein |
| 6 | Bolt 008, Bolt 009 | Ja |
| 7 | Bolt 015 | Nein |
| 8 | Bolt 012 | Nein (braucht alles) |

**Gesamte Bolts**: 15
**Backend (DDD)**: 12 Bolts
**Frontend (Simple)**: 3 Bolts

> **Hinweis**: Unit 001 hat 6 Stories (inkl. `006-user-invitation`). Bolt 002 enthält diese Story.
