# Tech Stack

## Overview
Full-stack web app with a Python/FastAPI backend and a React/Vite frontend. JWT-based authentication is handled in-house; deployment target is TBD (local-first development).

## Languages
- **Backend**: Python
- **Frontend**: TypeScript / JavaScript (React)

Python was chosen for its productivity and strong ecosystem. The team is comfortable with it and does not require a compiled language for this use case.

## Framework
- **Backend**: FastAPI
- **Frontend**: React + Vite

FastAPI provides async-ready endpoints, automatic OpenAPI docs, and excellent type-hint support. React + Vite was chosen for its flexibility, large ecosystem, and fast dev-server experience.

## Styling
- **Tailwind CSS**

Utility-first CSS framework, co-located styles, no naming overhead, great integration with React + Vite.

## Authentication
- **JWT (self-implemented)**

JWT tokens issued and validated by the FastAPI backend using `PyJWT` or `python-jose`. Keeps the auth stack lean and avoids third-party dependencies.

## Infrastructure & Deployment
- **TBD** (local development for now)

No deployment target decided yet. To be revisited once core features are built.

## Package Manager
- **Python**: pip + venv
- **JavaScript**: npm

## Decision Relationships
- FastAPI + JWT pair naturally: FastAPI's dependency injection makes JWT middleware straightforward.
- React + Vite + Tailwind is a well-supported combination with minimal configuration.
- npm chosen for maximum compatibility; can migrate to pnpm later if monorepo or speed is needed.
