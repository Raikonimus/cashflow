# System Architecture

## Overview
Monolithic application with clear feature-based layering. REST API backend, single-page React frontend. No microservices complexity — optimized for a small team moving fast.

## Architecture Style

- **Monolith** — single deployable backend unit
- Clear separation between features (auth, transactions, dashboard, etc.)
- Each feature owns its router, service, and models

## API Design

- **REST** mit JSON-Payloads
- **OpenAPI / Swagger** Docs von FastAPI automatisch generiert (intern; `/docs` nur in Dev)
- Versioniert via URL-Prefix: `/api/v1/`
- Antworten sind direkte Pydantic-Modelle — **kein** generisches Envelope (`{ "data": {}, "error": null }` wird nicht verwendet)
- HTTP-Statuscodes semantisch (200, 201, 204, 400, 401, 403, 404, 422, 500)

## State Management (Frontend)

- **React Query (TanStack Query)** — all server/API state (fetching, caching, mutations)
- **Zustand** — local UI state only (modals, sidebar, theme)
- No Redux; keep state as close to components as possible

## Caching Strategy

- None initially — React Query provides client-side caching automatically
- Redis to be added if server-side caching becomes necessary at scale

## Security Patterns

- HTTPS enforced in all non-local environments
- JWT tokens in `Authorization: Bearer` header (never in cookies or localStorage long-term)
- CORS configured to allow only known frontend origins
- No sensitive data stored in frontend state or localStorage
- Input validation via Pydantic on all API endpoints
- SQL injection prevented by SQLModel/SQLAlchemy parameterised queries
