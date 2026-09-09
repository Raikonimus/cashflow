from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.imports.models import ImportStatus


class ImportRunListItem(BaseModel):
    id: UUID
    filename: str
    row_count: int
    skipped_count: int
    error_count: int
    status: ImportStatus
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ImportRunDetailResponse(ImportRunListItem):
    account_id: UUID
    user_id: UUID
    error_details: Any | None

    model_config = {"from_attributes": True}


class PaginatedImportRunsResponse(BaseModel):
    items: list[ImportRunListItem]
    total: int
    page: int
    size: int
    pages: int
