# UX Guide

## Overview
Modernes, professionelles SaaS-Design mit Tailwind CSS. Datenorientiert, grau-blau akzentuiert, für finanzielle Anwendungen optimiert. shadcn/ui wurde **nicht** eingeführt — alle Komponenten sind direkt mit Tailwind-Klassen gebaut.

## Design System / Component Library

- **Tailwind CSS** — utility-first, alle Styles direkt im JSX
- **Keine Komponentenbibliothek** (kein shadcn/ui, kein Radix UI) — bewusste Entscheidung für volle Kontrolle und minimale Abhängigkeiten
- Wiederverwendbare Komponenten in `src/components/` (z.B. `AppLayout.tsx`)

## Colour Palette

- **Primary**: Blue (Tailwind `blue-600`)
  - Buttons, Links, aktive Nav-Elemente, Focus-Rings
- **Neutral base**: Gray (Tailwind `gray-*`)
  - Hintergründe, Borders, gedämpfter Text
- **Semantische Farben**:
  - Erfolg: `green-*`
  - Warnung: `amber-*` / `orange-*`
  - Fehler: `red-*`
  - Partner/Merge: `purple-*`
- **Dark Mode**: ❌ Noch nicht implementiert
- Keine hardcodierten Hex-Werte — immer Tailwind-Tokens

## Typography

- **Font**: Inter (Google Fonts / self-hosted via `@fontsource/inter`)
- Scale: Tailwind default (`text-sm`, `text-base`, `text-lg`, `text-xl`, `text-2xl`)
- **Financial figures**: `font-mono` (e.g. `tabular-nums`) for amounts and IBANs in tables
- Headings: `font-semibold`, body: `font-normal`

## Spacing & Density

- **Density**: Balanced — standard shadcn spacing; not spacious, not compact
  - Table rows: `py-2.5`; form fields: `h-9`; cards: `p-4`
- **Border Radius**: Slight — `rounded-md` (6 px) as default; `rounded-lg` for cards/dialogs
  - Set via `--radius: 0.375rem` in CSS variables

## Styling Approach

- Tailwind CSS utility classes co-located with JSX — no separate CSS files per component
- Global styles in `src/index.css`: base reset, CSS custom property definitions (shadcn theme)
- Dark mode class applied to `<html>` element

## Accessibility Standards

- **WCAG 2.1 AA** as the target baseline
- All interactive elements keyboard-navigable
- Radix UI primitives (via shadcn/ui) handle ARIA roles and focus management
- Colour contrast ratio ≥ 4.5:1 for normal text, ≥ 3:1 for large text
- Focus rings visible in both light and dark mode

## Responsive Design

- Mobile-first breakpoints via Tailwind (`sm`, `md`, `lg`, `xl`)
- Dashboard layout: sidebar collapses to bottom nav on mobile
- Tables: horizontal scroll on small screens; key columns always visible
