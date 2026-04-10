---
stage: implementation-plan
bolt: 010-cashflow-ui
created: 2026-04-06T00:00:00Z
---

# Implementation Plan: Auth UI (Bolt 010)

## Übersicht

Authenfiziertes Frontend für Cashflow. Bolt 010 implementiert alle Auth-Screens und die grundlegende App-Shell (Router, geschützte Routes, Token-Storage). Kein UI für Tenant/Account/Partner-Verwaltung — das kommt in späteren Frontend-Bolts.

---

## Tech Stack

| Layer | Technologie |
|-------|------------|
| Framework | React 18 + Vite |
| Sprache | TypeScript (strict) |
| Styling | Tailwind CSS + shadcn/ui |
| State (Server) | TanStack Query (React Query v5) |
| State (Client) | Zustand (Auth-Store) |
| HTTP | axios mit Bearer-Interceptor |
| Routing | React Router v6 |
| Forms | React Hook Form + zod |
| Testing | Vitest + RTL + MSW |

---

## Verzeichnisstruktur

```
frontend/
├── src/
│   ├── api/
│   │   ├── client.ts           # axios-Instanz mit Interceptor
│   │   └── auth.ts             # API-Funktionen (login, forgotPassword, etc.)
│   ├── store/
│   │   └── auth-store.ts       # Zustand-Store (token, user, mandant)
│   ├── hooks/
│   │   └── use-auth.ts         # Wrapper-Hook für authStore + ReactQuery
│   ├── components/
│   │   └── ui/                 # shadcn/ui Komponenten (auto-generiert)
│   ├── pages/
│   │   ├── Login.tsx
│   │   ├── SelectMandant.tsx
│   │   ├── ForgotPassword.tsx
│   │   └── ResetPassword.tsx
│   ├── router/
│   │   ├── index.tsx           # React Router-Konfiguration
│   │   └── PrivateRoute.tsx    # Guard-Komponente
│   ├── App.tsx
│   └── main.tsx
├── vite.config.ts
├── tailwind.config.ts
├── package.json
└── tsconfig.json
```

---

## Screens & Flows

### 1. `/login` — Login-Screen
- Formular: E-Mail + Passwort
- Submit → `POST /api/v1/auth/login`
- Erfolg mit einem Mandanten → Token speichern → Redirect `/` (Dashboard Stub)
- Erfolg mit mehreren Mandanten → Redirect `/login/select-mandant` (Token noch kein `mandant_id`)
- Fehler → Inline-Fehlermeldung (shadcn/ui `Alert`)
- Link: "Passwort vergessen?" → `/forgot-password`

### 2. `/login/select-mandant` — Mandant wählen
- Zeigt Liste der Mandanten (aus Login-Response)
- Klick auf Mandant → `POST /api/v1/auth/select-mandant`
- Neuen Token mit `mandant_id` speichern → Redirect `/`
- Nur erreichbar wenn User mehrere Mandanten hat (sonst Redirect `/`)

### 3. `/forgot-password` — Passwort vergessen
- Formular: E-Mail
- Submit → `POST /api/v1/auth/forgot-password`
- Immer 200 (E-Mail-Enumeration prevention) → Toast: "Falls diese E-Mail-Adresse registriert ist, wurde eine E-Mail gesendet"
- Link zurück zu `/login`

### 4. `/reset-password` — Passwort zurücksetzen
- Token aus URL-Parameter `?token=...` lesen
- Formular: Neues Passwort + Bestätigung
- Submit → `POST /api/v1/auth/reset-password` mit `{token, new_password}`
- Erfolg → Redirect `/login` mit Success-Toast
- Token fehlt/abgelaufen → Fehlermeldung + Link zu `/forgot-password`

### 5. Auth Guard (`PrivateRoute`)
- Prüft ob Valid JWT im Store vorhanden
- `is_active`-Check (Token-Expiry via `jwt-decode`)
- Nicht authentifiziert → Redirect `/login`
- Mandant-Pflicht: Manche Routen erfordern gesetzten `mandant_id` → Redirect `/login/select-mandant`

---

## State Management (Zustand)

```typescript
interface AuthState {
  token: string | null
  user: UserInfo | null
  mandants: MandantInfo[]        // aus Login-Response
  selectedMandant: MandantInfo | null
  
  login(token: string, user: UserInfo, mandants: MandantInfo[]): void
  selectMandant(mandant: MandantInfo, newToken: string): void
  logout(): void
}
```

**Storage**: `localStorage` — `token` und `selectedMandant` persistent. Bei App-Start: Store aus localStorage rehydrieren.

---

## API-Schicht

### `src/api/client.ts`
```typescript
// axios-Instanz
// Request-Interceptor: Bearer-Token aus Store anhängen
// Response-Interceptor: 401 → logout() + redirect /login
```

### `src/api/auth.ts`
```typescript
// loginUser(email, password)
// selectMandant(mandantId)
// forgotPassword(email)
// resetPassword(token, newPassword)
```

---

## Formular-Validierung (zod)

| Screen | Validierungsregeln |
|--------|-------------------|
| Login | E-Mail RFC-konform; Passwort min 1 Zeichen |
| Forgot Password | E-Mail RFC-konform |
| Reset Password | Passwort min 8 Zeichen; Bestätigung ident |

---

## UX-Vorgaben (aus ux-guide.md)

- Farbe: Indigo-600 als Primary
- Font: Inter
- Dark Mode: class-Strategie (kein Toggle in diesem Bolt — Grundlage schaffen)
- Radius: `rounded-md`
- Balanced density: keine übermäßigen Abstände

---

## Testing-Plan

### Unit Tests (Vitest + RTL)
- `Login.test.tsx`: Rendert Formular; zeigt Fehler bei ungültiger Eingabe; leitet nach Erfolg um
- `SelectMandant.test.tsx`: Zeigt Mandanten-Liste; ruft `select-mandant` API bei Klick auf
- `ForgotPassword.test.tsx`: Zeigt Toast nach Submit (egal welche E-Mail)
- `ResetPassword.test.tsx`: Liest Token aus URL; Fehler bei Passwort-Mismatch; Redirect bei Erfolg
- `PrivateRoute.test.tsx`: Authenticated → rendert children; Unauthenticated → Redirect

### MSW Mock-Handlers
- `POST /api/v1/auth/login` → 200 mit Token oder 401
- `POST /api/v1/auth/select-mandant` → 200 mit neuem Token
- `POST /api/v1/auth/forgot-password` → immer 200
- `POST /api/v1/auth/reset-password` → 200 oder 400/422

---

## Abhängigkeiten zu anderen Bolts

- **Bolt 001** (Auth Foundation Backend): Alle Endpoints müssen laufen (`/login`, `/forgot-password`, `/reset-password`, `/select-mandant`)
- **Keine** weiteren Bolts für Bolt 010 benötigt

---

## Offene Fragen / ADR-Kandidaten

| Frage | Tendenz |
|-------|---------|
| JWT in `localStorage` vs. `httpOnly` Cookie | `localStorage` für MVP (SPA-freundlich), ADR falls Sicherheits-Anforderung steigt |
| Refresh-Token Strategie | Noch kein Refresh-Token (ADR-002 aus Bolt 001), Login erneut nötig bei Ablauf |
