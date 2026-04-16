---
unit: 007-cashflow-ui
intent: 001-cashflow-core
unit_type: frontend
default_bolt_type: simple-construction-bolt
phase: inception
status: ready
created: 2026-04-06T00:00:00Z
updated: 2026-04-15T00:00:00Z
---

# Unit Brief: cashflow-ui

## Purpose

React + Vite Frontend mit allen Screens und Client-seitiger Logik. Konsumiert alle Backend-APIs und stellt die vollständige Nutzungsoberfläche bereit.

## Scope

### In Scope
- Login-Screen + Mandantenauswahl
- Passwort-Vergessen-Flow
- Navigation / Shell (Sidebar, Header mit aktivem Mandanten)
- User- & Mandantenverwaltung (Admin-Bereich)
- Kontoverwaltung
- Import-Screen (Drag & Drop, Kontoauswahl, Mapping-Editor)
- Partner-Verwaltung (Liste, Detail, Merge)
- Leistungsverwaltung (Leistungen, Matcher, Basisleistungs-Hinweise)
- Review-Queue-Screen + Archiv
- Service-Type-Review-Screen
- Einstellungen für Keyword-Konfiguration
- Einnahmen-&-Ausgaben-Screen (Jahresmatrix mit Gruppen, Summen, Collapse, Drag & Drop fuer Einnahmen, Ausgaben und Erfolgsneutrale Zahlungen)
- Buchungszeilen-Liste (Filter, Paginierung, Bulk-Aktionen)
- Audit-Log-Ansicht (Admin/Mandant-Admin)
- Zugriffsschutz: Routing nach Rolle

### Out of Scope
- Backend-Logik (alle Daten kommen via API)
- E-Mail-Versand

---

## Assigned Requirements

| FR | Requirement | Priority |
|----|-------------|----------|
| FR-1 | Login, Mandantenauswahl, Passwort-Reset UI | Must |
| FR-2 | User-Verwaltung UI (rollenspezifisch) | Must |
| FR-3 | Mandanten- & Konto-Verwaltung UI | Must |
| FR-4 | Mapping-Editor UI | Must |
| FR-5 | Import-Screen mit Drag & Drop | Must |
| FR-7 | Partner-Verwaltung UI inkl. Merge | Must |
| FR-12 | Leistungsverwaltung UI | Must |
| FR-8 | Review-Queue UI | Must |
| FR-9 | Buchungszeilen-Liste mit Filtern | Must |
| FR-10 | Bulk-Operationen UI | Should |
| FR-11 | Audit-Log UI | Must |
| FR-17 | Keyword-Konfiguration und Service-Typ-Anzeige | Must |
| FR-18 | Service-Type-Review UI | Must |
| FR-19 | Leistungszuordnungs-Review UI | Must |
| FR-20 | Review-Archiv UI | Should |
| FR-22 | Partnerliste mit deduplizierten Service-Typ-Icons | Should |
| FR-23 | Einnahmen- & Ausgaben-Jahresmatrix | Must |

---

## UI-Struktur

### Screen-Übersicht

```
/login                          Login
/login/select-mandant           Mandantenauswahl (falls > 1 Mandant)
/forgot-password                Passwort vergessen
/reset-password?token=...       Neues Passwort setzen

/                               → Redirect auf /journal

/journal                        Buchungszeilen-Liste
  ?account=&partner=&year=&month=

/import                         Import-Screen
  Step 1: Konto wählen / neues Konto
  Step 2: Mapping-Editor (falls noch kein Mapping)
  Step 3: CSV Drag & Drop Upload
  Step 4: Import-Ergebnis & Review-Link

/accounts                       Kontoliste
/accounts/new                   Neues Konto anlegen (eigener Screen)
/accounts/:id                   Konto-Detail + Mapping-Konfiguration

/partners                       Partnerliste
/partners/:id                   Partner-Detail (IBANs, Namen, Muster)
/partners/:id/merge             Partner-Merge
/partners/:id/services          Leistungsverwaltung

/review                         Review-Queue (Badge mit offenen Items)
/review/archive                 Review-Archiv
/review/service-types           Service-Type-Review

/settings/service-keywords      Keyword-Konfiguration

/cashflow/income-expense        Einnahmen-&-Ausgaben-Jahresmatrix

/admin/users                    Userverwaltung (Admin + Mandant-Admin)
/admin/mandants                 Mandantenverwaltung (Admin only)
/admin/audit                    Audit-Log (Admin + Mandant-Admin)
```

### Komponenten-Hierarchie (grob)

```
App
├── AuthProvider (JWT, aktiver Mandant, Rolle)
├── Layout (Sidebar + Header)
│   ├── Sidebar (Navigation nach Rolle)
│   └── Header (aktiver Mandant, User-Menu)
│
├── Pages
│   ├── LoginPage
│   ├── JournalPage
│   │   ├── FilterBar
│   │   ├── JournalTable (virtuelles Scrolling / Paginierung)
│   │   └── BulkActionBar
│   ├── ImportPage
│   │   ├── AccountSelector
│   │   ├── ColumnMappingEditor
│   │   └── CsvDropzone (Drag & Drop)
│   ├── AccountsPage / AccountDetailPage
│   │   └── ColumnMappingEditor
│   ├── PartnersPage / PartnerDetailPage
│   │   ├── IbanList
│   │   ├── NameList
│   │   ├── PatternList
│   │   └── MergeDialog
│   ├── ReviewQueuePage
│   │   └── ReviewItemCard
│   └── Admin
│       ├── UsersPage
│       ├── MandantsPage
│       └── AuditLogPage
│
└── Shared
    ├── components/ui (shadcn/ui)
    ├── hooks/ (useAuth, useMandant, useJournalLines, …)
    └── api/ (React Query hooks per Resource)
```

### State-Strategie
| State-Typ | Tool | Beispiel |
|-----------|------|---------|
| Server-State (API-Daten) | React Query | journal lines, partners, import runs |
| Auth-State | Zustand | JWT, aktiver Mandant, Rolle |
| UI-State | Zustand / lokal | Modal open, selected rows, filter values |

---

## Domain Concepts

### Key Operations (Client-seitig)
| Operation | Beschreibung |
|-----------|-------------|
| authenticateUser | Login → JWT speichern → Mandantenauswahl |
| uploadCsvFiles | Drag & Drop → multipart POST → Import-Status anzeigen |
| editColumnMapping | Mapping-Editor → Änderung speichern → optional Re-Mapping triggern |
| resolveReviewItem | Bestätigen / Korrektur → API-Call → Item aus Queue entfernen |
| bulkAssignPartner | Zeilen markieren → Partner suchen → Bulk-POST |
| mergePartners | Partner auswählen → Merge-Dialog → Bestätigung → POST |

---

## Story Summary

| Metric | Count |
|--------|-------|
| Total Stories | 12 |
| Must Have | 12 |
| Should Have | 0 |
| Could Have | 0 |

### Stories
- 001-auth-screens.md
- 002-admin-screens.md
- 003-account-management-screen.md
- 004-import-screen.md
- 005-partner-screens.md
- 006-review-queue-screen.md
- 007-journal-screen.md
- 008-audit-log-screen.md
- 009-service-management-screen.md
- 010-service-type-review-screen.md
- 011-settings-keyword-config.md
- 012-income-expense-screen.md
