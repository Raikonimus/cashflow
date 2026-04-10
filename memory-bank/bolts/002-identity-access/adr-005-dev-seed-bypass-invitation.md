---
bolt: 002-identity-access
created: 2026-04-06T00:00:00Z
status: accepted
superseded_by:
---

# ADR-005: Dev-Seed setzt Passwort direkt (bypasses Invitation Flow)

## Context

Für die lokale Entwicklungsumgebung wird ein Script (`python -m app.scripts.seed`) benötigt, das einen initialen Admin-User anlegt. Der normale User-Lifecycle sieht vor, dass ein User über einen Invitation-Token sein Passwort selbst setzt. Für den Dev-Seed müsste man sonst: (1) User anlegen, (2) Invitation-Token aus DB kopieren, (3) Invitation-Endpoint aufrufen — ein mehrschrittiger Prozess, der lokales Setup unnötig kompliziert.

## Decision

`seed.py` legt den Admin-User direkt mit `password_hash = bcrypt(SEED_ADMIN_PASSWORD)` an — **ohne** Invitation-Token und **ohne** E-Mail-Versand. Das ist ein **dev-only Shortcut**, explizit kommentiert im Code, und läuft nur wenn `ENV != production`.

```python
# DEV SHORTCUT: Bypasses invitation flow intentionally (ADR-005).
# Never replicate this pattern in production code.
user.password_hash = hash_password(password)
```

## Rationale

Der Invitation-Flow existiert für Sicherheit im Mehrbenutzerbetrieb (Admin soll Passwort des Users nicht kennen). Für den lokalen Admin-Seed gibt es keinen zweiten "Admin", der das Passwort nicht kennen dürfte. Der Entwickler kennt das Passwort aus `.env` sowieso. Der Shortcut ist sicher solange der Guard `ENV=production → Abbruch` zuverlässig ist.

### Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|-------------|------|------|--------------|
| Vollständiger Invitation-Flow im Seed | Konsistenter Code-Pfad | Mehrstufig, umständlich für lokales Setup; erfordert SMTP-Konfiguration oder Token-Extraktion aus DB | Unnötige Komplexität für Entwickler-Convenience-Feature |
| Festes Passwort im Code | Sehr einfach | Sicherheits-Anti-Pattern, würde in Code-Review auffallen | Unakzeptabel |
| Kein Seed-Script (manuelle DB-Einträge) | Kein Code-Bypass | Schlecht für Developer Experience; fehleranfällig | DX-Killer |

## Consequences

### Positive

- Lokales Setup: ein Befehl → funktionierender Admin-Login
- Kein SMTP-Server für initiales Setup nötig
- Idempotent (kein Fehler bei wiederholtem Ausführen)

### Negative

- Code-Pfad der `password_hash` direkt setzt existiert; muss klar dokumentiert und isoliert bleiben
- Zukünftige Entwickler könnten das Pattern fälschlicherweise nachahmen

### Risks

- **Accidental production run**: Mitigiert durch Guard `if settings.env == "production": sys.exit(1)` am Anfang des Scripts; Guard wird in Tests verifiziert
- **Pattern-Nachahmung**: Mitigiert durch expliziten Kommentar `# DEV SHORTCUT: ... (ADR-005)` und Verweis auf diesen ADR

## Related

- **Stories**: `001-identity-access/stories/007-dev-seed.md`
- **Standards**: `memory-bank/standards/system-architecture.md` (Security Patterns)
- **Previous ADRs**: ADR-003 (Token-Hash-Storage), ADR-004 (User-creation SMTP failure)
