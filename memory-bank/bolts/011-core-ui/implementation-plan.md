# Stage 1: Implementation Plan — Bolt 011 Core UI

## Übersicht

Bolt 011 implementiert die drei Core-Screens des Cashflow-Frontends:
- `/admin` — User- und Mandantenverwaltung (Admin/Mandant-Admin)
- `/accounts` — Kontoverwaltung + Mapping-Editor
- `/import` — Import-Wizard (Konto-Auswahl → Mapping → CSV-Upload → Ergebnis)

Bolt 010 hat bereits die App-Shell, Router, Auth-Store, axios-Client und alle Auth-Screens fertiggestellt.

---

## Tech Stack (identisch mit Bolt 010)

| Layer | Technologie |
|---|---|
| Framework | React 18 + Vite |
| Sprache | TypeScript (strict) |
| Styling | Tailwind CSS + shadcn/ui |
| State (Server) | TanStack Query (React Query v5) |
| State (Client) | Zustand |
| HTTP | axios mit Bearer-Interceptor (bestehend) |
| Routing | React Router v6 |
| Forms | React Hook Form + zod |
| Testing | Vitest + RTL + MSW |

---

## Verzeichnisstruktur (Ergänzungen zu Bolt 010)

```
frontend/src/
├── api/
│   ├── users.ts           # GET/POST/PATCH /users, /mandants
│   ├── accounts.ts        # GET/POST /accounts, GET/POST /mappings
│   └── imports.ts         # POST /imports, GET /imports
├── pages/
│   ├── admin/
│   │   ├── UsersPage.tsx
│   │   ├── MandantsPage.tsx        # Admin only
│   │   └── UserDialog.tsx
│   ├── accounts/
│   │   ├── AccountsPage.tsx
│   │   ├── AccountDetailPage.tsx
│   │   ├── AccountNewPage.tsx
│   │   └── MappingEditor.tsx
│   └── import/
│       ├── ImportPage.tsx          # Wizard-Shell
│       ├── steps/
│       │   ├── StepSelectAccount.tsx
│       │   ├── StepMapping.tsx     # Reuses MappingEditor
│       │   ├── StepUpload.tsx
│       │   └── StepResult.tsx
```

---

## Screens im Detail

### 1. `/admin/users` — User-Verwaltung

**Sichtbarkeit**: Admin + Mandant-Admin (RequireRole-Guard)

**Komponenten**:
- `UsersPage` — Tabelle: E-Mail, Rolle, Mandanten (Badge), Status (Chip), Aktions-Buttons
- `UserDialog` — Modal: E-Mail (neu), Rolle (Dropdown, rollenspezifisch gefiltert), Mandanten-Auswahl (Multi-Select für Admin, locked für Mandant-Admin)
- Aktionen: Anlegen (POST), Deaktivieren (PATCH is_active=false)

**API-Calls**:
- `GET /api/v1/users` → Liste
- `POST /api/v1/users` → Anlegen
- `PATCH /api/v1/users/:id` → Deaktivieren

---

### 2. `/admin/mandants` — Mandantenverwaltung (Admin only)

**Sichtbarkeit**: nur Admin

**Komponenten**:
- `MandantsPage` — Tabelle: Name, Erstellt-Datum, Status; Button „Mandant anlegen"
- Inline-Formular oder Modal: Name → POST /mandants

**API-Calls**:
- `GET /api/v1/mandants`
- `POST /api/v1/mandants`

---

### 3. `/accounts` — Kontoverwaltung

**Komponenten**:
- `AccountsPage` — Tabelle: Name, Mapping-Status (Badge: konfiguriert / ausstehend)
- `AccountNewPage` — Formular (Name, Beschreibung); eigener Screen (kein Modal)
- `AccountDetailPage` — Konto-Info + eingebetteter `MappingEditor`

**MappingEditor** (wiederverwendbare Komponente):
- Upload einer Muster-CSV → kolonnen-Vorschau
- Dropdown-Mapping: Quellspalte → Zielspalte (valuta_date, booking_date, amount, partner_name, partner_iban, description)
- Speichern → `POST /accounts/:id/mapping` → optional Bestätigungs-Dialog für Re-Mapping

**API-Calls**:
- `GET /api/v1/mandants/:id/accounts`
- `POST /api/v1/mandants/:id/accounts`
- `GET/POST /api/v1/mandants/:id/accounts/:id/mapping`

---

### 4. `/import` — Import-Wizard (4 Schritte)

**Step 1 — Konto-Auswahl**:
- Dropdown mit bestehenden Konten
- Link „Neues Konto anlegen" → `/accounts/new?redirect=/import`; nach Speichern zurück mit vorausgewähltem Konto

**Step 2 — Mapping (nur wenn kein Mapping vorhanden)**:
- Inline `MappingEditor`-Komponente

**Step 3 — Upload**:
- Drag & Drop Zone (mehrere CSVs); Dateiliste mit Remove-Button
- „Import starten" → `POST /accounts/:id/imports` with multipart; Ladeindikator

**Step 4 — Ergebnis**:
- Importierte Zeilen, Anzahl Review-Items, Link zu Review-Queue (`/review`)

---

## Routing-Plan (Ergänzung zu Bolt 010)

```tsx
<Route path="/admin" element={<RequireRole min="mandant_admin" />}>
  <Route index element={<Navigate to="/admin/users" />} />
  <Route path="users" element={<UsersPage />} />
  <Route path="mandants" element={<RequireRole min="admin"><MandantsPage /></RequireRole>} />
</Route>
<Route path="/accounts" element={<RequireRole min="viewer" />}>
  <Route index element={<AccountsPage />} />
  <Route path="new" element={<AccountNewPage />} />
  <Route path=":id" element={<AccountDetailPage />} />
</Route>
<Route path="/import" element={<RequireRole min="accountant"><ImportPage /></RequireRole>} />
```

---

## Test-Strategie

- **Unit-Tests** (Vitest + RTL): `MappingEditor`, `UserDialog`, Import-Steps (StepUpload mit MSW-Mock)
- **Routing-Tests**: RequireRole-Guard schützt /admin, /import; Viewer sieht /accounts read-only
- **MSW-Mocks**: alle API-Endpunkte mocken; kein echter Backend-Aufruf in Tests
