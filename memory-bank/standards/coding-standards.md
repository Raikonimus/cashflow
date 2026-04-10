# Coding Standards

## Overview
Code style and quality standards for a Python/FastAPI + React/Vite full-stack project. Emphasis on consistency, readability, and automated enforcement.

## Code Formatting

- **Python**: Black — opinionated, zero-config auto-formatter
- **JavaScript/React**: Prettier — standard config, run on save

Both formatters are non-negotiable; CI must enforce them.

## Linting

- **Python**: Ruff — replaces Flake8, isort, and more; configured in `pyproject.toml`
- **JavaScript/React**: ESLint — with `eslint-plugin-react` and `eslint-plugin-react-hooks`

## Naming Conventions

| Context | Variables | Functions | Classes | Constants |
|---------|-----------|-----------|---------|-----------|
| Python | `snake_case` | `snake_case` | `PascalCase` | `UPPER_SNAKE_CASE` |
| JavaScript | `camelCase` | `camelCase` | `PascalCase` | `UPPER_SNAKE_CASE` |
| React Components | — | — | `PascalCase` (filename matches) | — |

## File & Folder Organisation

**Backend (FastAPI) — Feature-based:**
```
backend/
  app/
    auth/
      router.py
      service.py
      models.py
    transactions/
      router.py
      service.py
      models.py
    main.py
```

**Frontend (React) — Feature-based:**
```
frontend/
  src/
    features/
      auth/
      transactions/
      dashboard/
    shared/
      components/
      hooks/
    main.tsx
```

## Testing Strategy

- **Python**: pytest + pytest-asyncio for async FastAPI routes
  - Unit tests alongside source: `tests/` per feature
  - Aim for unit + integration tests on all API endpoints
- **JavaScript/React**: Vitest + React Testing Library
  - Component tests co-located: `*.test.tsx`
  - Focus on user-visible behaviour, not implementation details

## Error Handling

- **Backend**: Custom exception classes inheriting from a base `AppException`; mapped to `HTTPException` in FastAPI exception handlers
- **Frontend**: React Error Boundaries for component trees; API errors surfaced via a central error state/toast pattern
- Never expose internal stack traces to the client

## Logging

- **Python**: `logging` module + `structlog` for structured JSON output
  - Log level configured via environment variable (`LOG_LEVEL`)
  - Include `request_id`, `user_id` in log context where available
- **Frontend**: `console.error` for errors only; no debug logs in production builds
