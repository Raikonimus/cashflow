from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import mandants_router, router as auth_router, users_router
from app.core.config import settings
from app.imports.router import imports_router
from app.journal.router import audit_router, journal_router
from app.partners.router import partners_router
from app.review.router import review_router
from app.services.router import services_router
from app.testing.router import testing_router
from app.tenants.router import accounts_router, tenants_router

app = FastAPI(
    title="CashFlow Core API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(mandants_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(accounts_router, prefix="/api/v1")
app.include_router(partners_router, prefix="/api/v1")
app.include_router(services_router, prefix="/api/v1")
app.include_router(imports_router, prefix="/api/v1")
app.include_router(review_router, prefix="/api/v1")
app.include_router(journal_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(testing_router, prefix="/api/v1")
