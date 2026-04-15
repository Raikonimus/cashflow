import csv
import io
from uuid import UUID


def _detect_encoding(raw: bytes) -> str:
    """Erkennt Zeichensatz via BOM, dann Trial-decode."""
    if raw[:2] == b'\xff\xfe' or raw[:2] == b'\xfe\xff':
        return 'utf-16'
    if raw[:3] == b'\xef\xbb\xbf':
        return 'utf-8-sig'
    for enc in ('utf-8', 'cp1252', 'latin-1'):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return 'utf-8'


def _detect_delimiter(text: str, fallback: str) -> str:
    """Erkennt das CSV-Trennzeichen via csv.Sniffer (quote-bewusst).
    Fällt auf die konfigurierte Einstellung zurück wenn der Sniffer scheitert."""
    try:
        sample = text[:8192]
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        return dialect.delimiter
    except csv.Error:
        return fallback

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_mandant_access, require_role
from app.auth.models import User
from app.core.database import get_session
from app.tenants.schemas import (
    AccountResponse,
    ApplyExcludedResponse,
    ExecuteMandantCleanupRequest,
    ExecuteMandantCleanupResponse,
    ColumnMappingRequest,
    ColumnMappingResponse,
    CreateAccountRequest,
    CreateMandantRequest,
    CsvPreviewResponse,
    ExcludedIdentifierCreate,
    ExcludedIdentifierResponse,
    MandantCleanupPreviewResponse,
    MandantResponse,
    RemappingTriggerResponse,
    UpdateAccountRequest,
    UpdateMandantRequest,
)
from app.tenants.service import AccountService, MandantService

tenants_router = APIRouter(prefix="/mandants", tags=["tenants"])
accounts_router = APIRouter(prefix="/mandants", tags=["accounts"])


def _mandant_svc(session: AsyncSession = Depends(get_session)) -> MandantService:
    return MandantService(session)


def _account_svc(session: AsyncSession = Depends(get_session)) -> AccountService:
    return AccountService(session)


# ─── Mandant endpoints ────────────────────────────────────────────────────────

@tenants_router.get("", response_model=list[MandantResponse])
async def list_mandants(
    actor: User = Depends(require_role("admin")),
    svc: MandantService = Depends(_mandant_svc),
) -> list[MandantResponse]:
    mandants = await svc.list_mandants()
    return [MandantResponse.model_validate(m) for m in mandants]


@tenants_router.post("", response_model=MandantResponse, status_code=status.HTTP_201_CREATED)
async def create_mandant(
    body: CreateMandantRequest,
    actor: User = Depends(require_role("admin")),
    svc: MandantService = Depends(_mandant_svc),
) -> MandantResponse:
    mandant = await svc.create_mandant(body)
    return MandantResponse.model_validate(mandant)


@tenants_router.get("/{mandant_id}", response_model=MandantResponse)
async def get_mandant(
    mandant_id: UUID,
    actor: User = Depends(require_role("admin")),
    svc: MandantService = Depends(_mandant_svc),
) -> MandantResponse:
    mandant = await svc.get_mandant(mandant_id)
    return MandantResponse.model_validate(mandant)


@tenants_router.patch("/{mandant_id}", response_model=MandantResponse)
async def update_mandant(
    mandant_id: UUID,
    body: UpdateMandantRequest,
    actor: User = Depends(require_role("admin")),
    svc: MandantService = Depends(_mandant_svc),
) -> MandantResponse:
    mandant = await svc.update_mandant(mandant_id, body)
    return MandantResponse.model_validate(mandant)


@tenants_router.get("/{mandant_id}/cleanup-preview", response_model=MandantCleanupPreviewResponse)
async def get_mandant_cleanup_preview(
    mandant_id: UUID,
    actor: User = Depends(require_role("admin")),
    svc: MandantService = Depends(_mandant_svc),
) -> MandantCleanupPreviewResponse:
    return await svc.get_cleanup_preview(mandant_id)


@tenants_router.post("/{mandant_id}/cleanup", response_model=ExecuteMandantCleanupResponse)
async def execute_mandant_cleanup(
    mandant_id: UUID,
    body: ExecuteMandantCleanupRequest,
    actor: User = Depends(require_role("admin")),
    svc: MandantService = Depends(_mandant_svc),
) -> ExecuteMandantCleanupResponse:
    return await svc.execute_cleanup(mandant_id, body)


@tenants_router.post("/{mandant_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_mandant(
    mandant_id: UUID,
    actor: User = Depends(require_role("admin")),
    svc: MandantService = Depends(_mandant_svc),
) -> None:
    await svc.deactivate_mandant(mandant_id)


# ─── Account endpoints ────────────────────────────────────────────────────────

@accounts_router.get("/{mandant_id}/accounts", response_model=list[AccountResponse])
async def list_accounts(
    mandant_id: UUID,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: AccountService = Depends(_account_svc),
) -> list[AccountResponse]:
    accounts = await svc.list_accounts(mandant_id)
    result = []
    for acc in accounts:
        mapping = await svc.get_column_mapping(acc.id)
        resp = AccountResponse.model_validate(acc)
        resp.has_column_mapping = mapping is not None
        result.append(resp)
    return result


@accounts_router.post(
    "/{mandant_id}/accounts",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_account(
    mandant_id: UUID,
    body: CreateAccountRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: AccountService = Depends(_account_svc),
) -> AccountResponse:
    account = await svc.create_account(mandant_id, body)
    return AccountResponse.model_validate(account)


@accounts_router.get("/{mandant_id}/accounts/{account_id}", response_model=AccountResponse)
async def get_account(
    mandant_id: UUID,
    account_id: UUID,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: AccountService = Depends(_account_svc),
) -> AccountResponse:
    account = await svc.get_account(account_id, mandant_id)
    mapping = await svc.get_column_mapping(account_id)
    resp = AccountResponse.model_validate(account)
    resp.has_column_mapping = mapping is not None
    return resp


@accounts_router.patch("/{mandant_id}/accounts/{account_id}", response_model=AccountResponse)
async def update_account(
    mandant_id: UUID,
    account_id: UUID,
    body: UpdateAccountRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: AccountService = Depends(_account_svc),
) -> AccountResponse:
    account = await svc.update_account(account_id, mandant_id, body)
    mapping = await svc.get_column_mapping(account_id)
    resp = AccountResponse.model_validate(account)
    resp.has_column_mapping = mapping is not None
    return resp


@accounts_router.get(
    "/{mandant_id}/accounts/{account_id}/column-mapping",
    response_model=ColumnMappingResponse,
)
async def get_column_mapping(
    mandant_id: UUID,
    account_id: UUID,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: AccountService = Depends(_account_svc),
) -> ColumnMappingResponse:
    # Verify account belongs to mandant
    await svc.get_account(account_id, mandant_id)
    mapping = await svc.get_column_mapping(account_id)
    if mapping is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No column mapping configured for this account")
    return ColumnMappingResponse.model_validate(mapping)


@accounts_router.post(
    "/{mandant_id}/accounts/{account_id}/column-mapping/preview",
    response_model=CsvPreviewResponse,
)
async def preview_csv_columns(
    mandant_id: UUID,
    account_id: UUID,
    file: UploadFile = File(...),
    delimiter: str = Query(default=";"),
    encoding: str = Query(default="utf-8"),
    skip_rows: int = Query(default=0, ge=0),
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: AccountService = Depends(_account_svc),
) -> CsvPreviewResponse:
    """Gibt die Spaltennamen der übergebenen CSV-Datei zurück (nur Header, kein Import)."""
    await svc.get_account(account_id, mandant_id)
    content = await file.read()
    detected_encoding = _detect_encoding(content)
    try:
        decoded = content.decode(detected_encoding)
    except UnicodeDecodeError:
        decoded = content.decode('utf-8', errors='replace')

    detected = _detect_delimiter(decoded, fallback=delimiter)
    reader = csv.DictReader(io.StringIO(decoded), delimiter=detected)
    columns = list(reader.fieldnames or [])
    sample_rows: list[dict[str, str]] = []
    for row in reader:
        sample_rows.append({k: (v or "") for k, v in row.items() if k})
    return CsvPreviewResponse(columns=columns, detected_delimiter=detected, detected_encoding=detected_encoding, sample_rows=sample_rows)


@accounts_router.put(
    "/{mandant_id}/accounts/{account_id}/column-mapping",
    response_model=ColumnMappingResponse,
)
async def set_column_mapping(
    mandant_id: UUID,
    account_id: UUID,
    body: ColumnMappingRequest,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: AccountService = Depends(_account_svc),
) -> ColumnMappingResponse:
    await svc.get_account(account_id, mandant_id)
    config = await svc.set_column_mapping(account_id, body)
    return ColumnMappingResponse.model_validate(config)


@accounts_router.post(
    "/{mandant_id}/accounts/{account_id}/remap",
    response_model=RemappingTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_remapping(
    mandant_id: UUID,
    account_id: UUID,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: AccountService = Depends(_account_svc),
) -> RemappingTriggerResponse:
    await svc.get_account(account_id, mandant_id)
    await svc.trigger_remapping(account_id, actor.id)
    return RemappingTriggerResponse(message="Remapping triggered", account_id=account_id)


# ─── Excluded Identifiers ──────────────────────────────────────────────────

@accounts_router.get(
    "/{mandant_id}/accounts/{account_id}/excluded-identifiers",
    response_model=list[ExcludedIdentifierResponse],
)
async def list_excluded_identifiers(
    mandant_id: UUID,
    account_id: UUID,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: AccountService = Depends(_account_svc),
) -> list[ExcludedIdentifierResponse]:
    await svc.get_account(account_id, mandant_id)
    entries = await svc.list_excluded_identifiers(account_id)
    return [ExcludedIdentifierResponse.model_validate(e) for e in entries]


@accounts_router.post(
    "/{mandant_id}/accounts/{account_id}/excluded-identifiers",
    response_model=ExcludedIdentifierResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_excluded_identifier(
    mandant_id: UUID,
    account_id: UUID,
    body: ExcludedIdentifierCreate,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: AccountService = Depends(_account_svc),
) -> ExcludedIdentifierResponse:
    entry = await svc.add_excluded_identifier(account_id, mandant_id, body)
    return ExcludedIdentifierResponse.model_validate(entry)


@accounts_router.delete(
    "/{mandant_id}/accounts/{account_id}/excluded-identifiers/{identifier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_excluded_identifier(
    mandant_id: UUID,
    account_id: UUID,
    identifier_id: UUID,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: AccountService = Depends(_account_svc),
) -> None:
    await svc.delete_excluded_identifier(account_id, mandant_id, identifier_id)


@accounts_router.post(
    "/{mandant_id}/accounts/{account_id}/excluded-identifiers/apply",
    response_model=ApplyExcludedResponse,
)
async def apply_excluded_identifiers(
    mandant_id: UUID,
    account_id: UUID,
    actor: User = Depends(require_role("accountant")),
    _access: None = Depends(require_mandant_access),
    svc: AccountService = Depends(_account_svc),
) -> ApplyExcludedResponse:
    """Prüft alle Journal-Zeilen dieses Kontos und ordnet jene neu zu,
    die via eines ausgeschlossenen Identifikators zugewiesen wurden."""
    affected = await svc.apply_excluded_identifiers(account_id, mandant_id)
    return ApplyExcludedResponse(
        affected=affected,
        message=f"{affected} Buchungszeile(n) wurden neu zugeordnet.",
    )
