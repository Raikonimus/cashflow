from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator

from app.auth.models import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MandantInfo(BaseModel):
    id: UUID
    name: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    mandants: list[MandantInfo]
    requires_mandant_selection: bool


class SelectMandantRequest(BaseModel):
    mandant_id: UUID


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen haben")
        return v


class MessageResponse(BaseModel):
    message: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    role: UserRole
    mandant_id: Optional[UUID] = None
    is_active: bool


class CreateUserRequest(BaseModel):
    email: EmailStr
    role: UserRole


class UpdateUserRequest(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserDetailResponse(BaseModel):
    id: UUID
    email: str
    role: UserRole
    is_active: bool
    invitation_status: str  # "pending" | "accepted" | "expired"


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen haben")
        return v


class MandantUserAssignRequest(BaseModel):
    user_id: UUID


class MandantUserResponse(BaseModel):
    mandant_id: UUID
    user_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
