from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator

from app.auth.models import UserRole


class LoginRequest(BaseModel):
    """Anmeldedaten."""

    email: EmailStr
    password: str


class MandantInfo(BaseModel):
    """Ein Mandant, so knapp wie die Auswahl ihn braucht: Kennung und Name."""

    id: UUID
    name: str


class LoginResponse(BaseModel):
    """Die Antwort auf das Anmelden — und die Anweisung, wie es weitergeht.

    Drei Faelle, die der Client an diesen Feldern unterscheidet:

    * ``requires_mandant_selection`` — mehrere Mandanten, es muss gewaehlt werden.
      Das Token traegt dann **keine** ``mandant_id``.
    * ``mandants`` leer — dem Nutzer ist keiner zugeordnet. Es gibt nichts zu waehlen
      und nichts zu sehen; die Oberflaeche erklaert das (Befund M6).
    * sonst — genau ein Mandant, er steht schon im Token.

    ``requires_mandant_selection`` ist genau ``len(mandants) > 1``, fuer **alle**
    Rollen. Die Sonderstellung des Admins liegt darin, *welche* Mandanten in
    ``mandants`` stehen (alle aktiven), nicht darin, ob er waehlen muss.
    """

    access_token: str
    token_type: str = "bearer"
    mandants: list[MandantInfo]
    requires_mandant_selection: bool


class SelectMandantRequest(BaseModel):
    """Der Mandant, der in das neue Token soll."""

    mandant_id: UUID


class TokenResponse(BaseModel):
    """Ein Token ohne Begleitinformation — etwa nach der Mandantenwahl."""

    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    """Anfrage fuer einen Zuruecksetzen-Link."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Einmaltoken aus der E-Mail und das neue Passwort."""

    token: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        """Mindestlaenge acht Zeichen — die Regel steht hier, nicht im Service."""
        if len(v) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen haben")
        return v


class MessageResponse(BaseModel):
    """Reine Bestaetigung ohne Daten."""

    message: str


class UserResponse(BaseModel):
    """Der angemeldete Nutzer, wie ``/auth/me`` ihn meldet.

    ``mandant_id`` kommt aus dem Token, nicht aus der Datenbank: Sie sagt, fuer
    welchen Mandanten *diese Sitzung* gilt — nicht, welche dem Nutzer zugeordnet
    sind. ``None`` heisst, dass noch nicht gewaehlt wurde oder nichts zu waehlen war.
    """

    id: UUID
    email: str
    role: UserRole
    mandant_id: UUID | None = None
    is_active: bool


class CreateUserRequest(BaseModel):
    """Ein neuer Nutzer — Einladung geht automatisch raus."""

    email: EmailStr
    role: UserRole
    # Mandanten, denen der neue Nutzer sofort zugeordnet wird. Leer zu lassen ist
    # erlaubt, fuehrt aber zu einem Nutzer ohne Mandanten — der kommt an keine Daten
    # und sieht nach dem Anmelden nur den Hinweis, dass eine Zuordnung fehlt
    # (Befund M6). Die Oberflaeche weist darauf hin.
    mandant_ids: list[UUID] = []


class UpdateUserRequest(BaseModel):
    """Teilaenderung eines Nutzers; nur gesetzte Felder wirken."""

    email: EmailStr | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    # Gesetzter Wert = Sollstand der Zuordnungen. Der Abgleich wirkt **nur** auf
    # Mandanten, die der Handelnde selbst zuordnen darf; alle uebrigen Zuordnungen
    # des Nutzers bleiben unberuehrt (siehe MandantAssignmentService.set_mandants).
    # `None` laesst die Zuordnungen unangetastet, eine leere Liste entfernt sie im
    # erlaubten Bereich.
    mandant_ids: list[UUID] | None = None


class UserDetailResponse(BaseModel):
    """Ein Nutzer, wie die Nutzerverwaltung ihn anzeigt."""

    id: UUID
    email: str
    role: UserRole
    is_active: bool
    invitation_status: str  # "pending" | "accepted" | "expired"
    # Die Mandanten dieses Nutzers. Eine leere Liste ist eine Aussage, kein fehlender
    # Wert: Der Nutzer hat keinen Mandanten und damit keinen Zugriff.
    mandants: list[MandantInfo] = []


class AcceptInvitationRequest(BaseModel):
    """Einladungstoken und das selbst gewaehlte Passwort."""

    token: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        """Mindestlaenge acht Zeichen — die Regel steht hier, nicht im Service."""
        if len(v) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen haben")
        return v


class MandantUserAssignRequest(BaseModel):
    """Der Nutzer, der dem Mandanten aus dem Pfad zugeordnet wird."""

    user_id: UUID


class MandantUserResponse(BaseModel):
    """Eine Zeile aus ``mandant_users`` — die Zugriffsentscheidung selbst."""

    mandant_id: UUID
    user_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
