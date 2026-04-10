# Data Stack

## Overview
SQLite als primäre Datenbank (Entwicklung & MVP), zugegriffen via SQLModel (aufgebaut auf SQLAlchemy 2.0) mit Async-Unterstützung durch aiosqlite. Alembic verwaltet Schema-Migrationen. PostgreSQL + asyncpg sind als spätere Produktions-DB vorbereitet (Dependency bereits vorhanden).

## Database

- **SQLite** (aktuell, MVP)

Relationale Datenbank, gut geeignet für lokale Entwicklung und den MVP-Betrieb. Keine Docker-Abhängigkeit. Migrations-Stand: `015` (Stand April 2026). Wechsel auf PostgreSQL ist vorbereitet — nur `DATABASE_URL` muss angepasst werden.

- **PostgreSQL** (geplant, Produktion)

Für Produktionsbetrieb vorgesehen. `asyncpg` ist bereits als Dependency in `pyproject.toml` eingetragen. Wechsel erfordert: `DATABASE_URL` auf `postgresql+asyncpg://...` setzen; `batch_alter_table`-Migrationen durch native `ALTER COLUMN` ersetzen.

## ORM / Database Client

- **SQLModel** — kombiniert Pydantic-Modelle und SQLAlchemy-Tabellendefinitionen; integriert nahtlos mit FastAPI Request/Response-Schemas
- **Alembic** — Datenbank-Migrationsverwaltung (manuelle Migrationsskripte in `migrations/versions/`)
- **aiosqlite** — Async-SQLite-Treiber für Entwicklung und Tests
- **asyncpg** — Async-PostgreSQL-Treiber (installiert, noch nicht aktiv)

## Lokale Entwicklung

- SQLite-Datei: `backend/cashflow.db`
- Connection-String via Umgebungsvariable: `DATABASE_URL=sqlite+aiosqlite:///./cashflow.db`
- Migrationen: `alembic upgrade head` (im `backend/`-Verzeichnis)
- Kein Docker erforderlich

## Decision Relationships

- SQLModel wurde gewählt um Boilerplate zu reduzieren: Eine Klassendefinition dient als Pydantic-Schema (FastAPI) und Datenbankmodell.
- aiosqlite passt zu FastAPIs Async-Endpunkten für konsistentes Async-I/O.
- SQLite ermöglicht schnellen Start ohne Infrastruktur; aber: kein `ALTER COLUMN` in Migrationen (stattdessen `batch_alter_table`).
