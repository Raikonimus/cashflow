---
bolt: 001-identity-access
created: 2026-04-06T00:00:00Z
status: accepted
superseded_by:
---

# ADR-003: Reset-Token und Invitation-Token als SHA-256-Hash in der Datenbank speichern

## Context

Passwort-Reset-Tokens (und später Einladungs-Tokens) sind privilegierte Credentials: Wer einen gültigen Raw-Token kennt, kann das Passwort eines fremden Accounts übernehmen. Die Frage ist, wie diese Tokens in der Datenbank gespeichert werden. Bei einem DB-Dump wären Plain-Text-Tokens direkt verwertbar.

Das Pattern trifft gleichartig auf `password_reset_tokens.token_hash` (Bolt 001) und `user_invitations.token_hash` (Bolt 002) zu.

## Decision

Raw-Token werden **nie** in der Datenbank gespeichert. Stattdessen wird der **SHA-256-Hash** des Raw-Tokens gespeichert. Token-Generierung: `secrets.token_urlsafe(32)` (256 Bit Entropie). Validierung: eingehenden Raw-Token hashen, mit DB-Hash vergleichen via `hmac.compare_digest` (timing-safe).

```python
import hashlib, hmac, secrets

# Generieren:
raw_token = secrets.token_urlsafe(32)
token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
# → raw_token an User per E-Mail, token_hash in DB

# Validieren:
incoming_hash = hashlib.sha256(incoming_token.encode()).hexdigest()
is_valid = hmac.compare_digest(incoming_hash, stored_hash)
```

## Rationale

Token für einmalige, privilegierte Aktionen sind funktional äquivalent zu Passwörtern aus Security-Sicht. Das "Hashed Token"-Pattern folgt dem Prinzip der minimalen Credential-Exposition.

### Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|-------------|------|------|--------------|
| Plain-Text-Token in DB | Einfach, direkt nachschaubar für Support | DB-Dump = komplette Account-Übernahme möglich | Security Anti-Pattern, unakzeptabel |
| bcrypt-Hash wie Passwörter | Bekanntes Pattern | bcrypt ist für kurze Tokens unnötig langsam (CPU-intensiv), Token hat bereits hohe Entropie | SHA-256 ausreichend für hochentropische Tokens; bcrypt für User-Passwörter reserviert |
| HMAC-SHA256 mit Secret | Verhindert zusätzlich Hash-Präimages | Secret-Rotation würde alle offenen Tokens invalidieren | Mehraufwand ohne signifikanten Sicherheitsgewinn bei 256-Bit-Token |

## Consequences

### Positive

- DB-Dump enthüllt keine verwertbaren Tokens
- Pattern konsistent auf alle Token-Typen anwendbar (`password_reset_tokens`, `user_invitations`)
- `hmac.compare_digest` verhindert Timing-Attacken bei der Validierung
- Kein Performance-Overhead (SHA-256 ist in Nanosekunden)

### Negative

- Raw-Token ist nach Generierung nicht wiederherstellbar; ein "Resend"-Feature muss einen neuen Token generieren
- Support kann keinen Token "nachschlagen" (by design)

### Risks

- **Kein Risiko**: SHA-256 für 256-Bit-Random-Tokens ist kryptographisch solide; Preimage-Attacks sind bei dieser Entropie nicht praktikabel

## Related

- **Stories**: `001-identity-access/stories/002-password-reset.md`, `001-identity-access/stories/006-user-invitation.md`
- **Standards**: `memory-bank/standards/system-architecture.md` (Security Patterns)
- **Previous ADRs**: —
