"""
Dev-seed script: creates an initial admin user from environment variables.

Usage:
    cd backend
    python -m app.scripts.seed

Reads from .env:
    SEED_ADMIN_EMAIL    e.g. admin@local.dev
    SEED_ADMIN_PASSWORD e.g. admin1234

Guards:
    - Refuses to run when ENV=production (ADR-005)
    - Exits with clear error if env vars are missing or password too short
    - Idempotent: no error if user already exists
"""

import asyncio
import sys

from sqlmodel import select


async def _seed() -> None:
    from app.core.config import settings

    # Guard: refuse in production (ADR-005)
    if settings.env == "production":
        print("ERROR: Seed script refused to run in production environment.", file=sys.stderr)
        sys.exit(1)

    if not settings.seed_admin_email:
        print("ERROR: Missing SEED_ADMIN_EMAIL env var.", file=sys.stderr)
        sys.exit(1)

    if not settings.seed_admin_password:
        print("ERROR: Missing SEED_ADMIN_PASSWORD env var.", file=sys.stderr)
        sys.exit(1)

    if len(settings.seed_admin_password) < 8:
        print(
            "ERROR: SEED_ADMIN_PASSWORD must be at least 8 characters.",
            file=sys.stderr,
        )
        sys.exit(1)

    from app.auth.models import User, UserRole
    from app.auth.security import hash_password
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.email == settings.seed_admin_email.lower())
        )
        existing = result.scalars().first()

        if existing is not None:
            print(f"INFO: User '{settings.seed_admin_email}' already exists. Skipping.")
            return

        # DEV SHORTCUT: Bypasses invitation flow intentionally (ADR-005).
        # The invitation flow exists for multi-user security; for a local seed
        # there is no second admin who should not know the password.
        # Never replicate this pattern in production code.
        admin = User(
            email=settings.seed_admin_email.lower(),
            password_hash=hash_password(settings.seed_admin_password),
            role=UserRole.admin.value,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        print(f"INFO: Admin user '{settings.seed_admin_email}' created successfully.")


def main() -> None:
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
