---
stage: adr-analysis
bolt: 006-import-core
created: 2026-04-06T00:00:00Z
adrs_created: [10]
---

# ADR-Analyse: Import Core (Bolt 006)

## Überblick

Während des Technical Designs wurden drei Entscheidungen identifiziert. Eine davon ist architekturell nicht-trivial und erfordert einen formalen ADR.

---

## Entscheidung 1 — Import-Verarbeitung: Synchron vs. Asynchron → **ADR-010**

**Kontext:** Das Verarbeiten einer CSV mit vielen Zeilen kann bei großen Dateien mehrere Sekunden dauern. Soll die Verarbeitung synchron im HTTP-Request oder in einem Background-Job erfolgen?

**Optionen:**
| Option | Pros | Cons |
|--------|------|------|
| Synchron (im Request) | Einfach; sofortiges Feedback; keine Queue-Infrastruktur | HTTP-Timeout bei sehr großen Dateien (>10k Zeilen); blockiert Worker |
| Asynchron (Celery/ARQ) | Keine Timeouts; skalierbar | Infrastruktur-Overhead; Polling-Logik im Frontend nötig |

**Entscheidung:** **Synchron für MVP**, asynchrones Muster erst wenn nötig. → **ADR-010**

---

## Entscheidung 2 — Dubletten-Handling: ON CONFLICT DO NOTHING

**Kontext:** Wenn dieselbe Buchungszeile doppelt importiert wird (z. B. bei erneutem Upload derselben CSV), soll die zweite Zeile mit Fehler abbrechen oder lautlos übersprungen werden?

**Entscheidung:** `ON CONFLICT DO NOTHING` — doppelte Zeilen werden lautlos übersprungen und in `skipped_count` gezählt. Kein Fehler.
**Begründung:** Der häufigste Anwendungsfall ist "versehentlich die selbe Datei nochmal hochgeladen". Ein harter Fehler wäre irritierend. `skipped_count` im `ImportRun` gibt ausreichend Transparenz. Kein ADR — konsistentes Daten-Qualitätsmuster.

---

## Entscheidung 3 — CSV-Encoding: UTF-8

**Kontext:** CSV-Dateien aus deutschen Banken kommen teils als UTF-8, teils als Latin-1 (ISO-8859-1). Welches Encoding wird angenommen?

**Entscheidung:** UTF-8 als Standard; `utf-8-sig` zum Strippen von BOM.
**Begründung:** Moderne Exporte sind UTF-8. Latin-1-Support kann bei Bedarf als Feature ergänzt werden (Encoding-Detection via `chardet`). Kein ADR — Scope-Entscheidung mit klarem Erweiterungspfad.
