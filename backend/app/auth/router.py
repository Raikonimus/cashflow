from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_jwt_payload, require_role
from app.auth.models import User, UserRole
from app.auth.schemas import (
    AcceptInvitationRequest,
    CreateUserRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    MandantInfo,
    MandantUserAssignRequest,
    MandantUserResponse,
    MessageResponse,
    ResetPasswordRequest,
    SelectMandantRequest,
    TokenResponse,
    UpdateUserRequest,
    UserDetailResponse,
    UserResponse,
)
from app.auth.service import (
    AuthService,
    InvitationService,
    MandantAssignmentService,
    PasswordResetService,
    UserManagementService,
)
from app.core.database import get_session

log = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])
mandants_router = APIRouter(prefix="/mandants", tags=["mandants"])


# ─── Dependency factories ───────────────────────────────────────────────────


def _auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    """Baut den Anmeldedienst auf der Sitzung dieses Aufrufs."""
    return AuthService(session)


def _reset_service(
    session: AsyncSession = Depends(get_session),
) -> PasswordResetService:
    """Baut den Dienst fuer das Zuruecksetzen von Passwoertern."""
    return PasswordResetService(session)


def _user_mgmt_service(
    session: AsyncSession = Depends(get_session),
) -> UserManagementService:
    """Baut den Dienst der Nutzerverwaltung."""
    return UserManagementService(session)


def _invitation_service(
    session: AsyncSession = Depends(get_session),
) -> InvitationService:
    """Baut den Einladungsdienst."""
    return InvitationService(session)


def _mandant_assignment_service(
    session: AsyncSession = Depends(get_session),
) -> MandantAssignmentService:
    """Baut den Dienst fuer Mandantenzuordnungen."""
    return MandantAssignmentService(session)


# ─── Auth endpoints ──────────────────────────────────────────────────────────


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    svc: AuthService = Depends(_auth_service),
) -> LoginResponse:
    """Meldet an und sagt, ob noch ein Mandant zu waehlen ist.

    Siehe ``LoginResponse`` fuer die drei Faelle, die die Antwort unterscheidet.
    """
    result = await svc.login(req.email, req.password)
    return LoginResponse(
        access_token=result["access_token"],
        mandants=[MandantInfo(id=m.id, name=m.name) for m in result["mandants"]],
        requires_mandant_selection=result["requires_mandant_selection"],
    )


@router.post("/select-mandant", response_model=TokenResponse)
async def select_mandant(
    req: SelectMandantRequest,
    current_user: User = Depends(get_current_user),
    svc: AuthService = Depends(_auth_service),
) -> TokenResponse:
    """Tauscht das Token gegen eines mit dem gewaehlten Mandanten.

    Braucht ein gueltiges Token im Authorization-Header — der Aufruf haengt an
    ``get_current_user``. Auch der Wechsel im laufenden Betrieb geht hierueber.
    """
    token = await svc.select_mandant(current_user, req.mandant_id)
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: dict = Depends(get_jwt_payload),
    current_user: User = Depends(get_current_user),
    svc: AuthService = Depends(_auth_service),
) -> None:
    """Schreibt den Abmeldevorgang ins Protokoll.

    Serverseitig ist nichts zu verwerfen — die Token sind zustandslos und laufen von
    selbst ab. Der Eintrag haelt fest, fuer welchen Mandanten die Sitzung galt;
    ein unlesbarer Wert im Token wird dabei stillschweigend zu ``None``, weil das
    Abmelden nicht an einer Protokollangabe scheitern soll.
    """
    mandant_id: UUID | None = None
    raw = payload.get("mandant_id")
    if raw:
        try:
            mandant_id = UUID(raw)
        except (ValueError, AttributeError):
            pass
    await svc.logout(current_user, mandant_id)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    req: ForgotPasswordRequest,
    svc: PasswordResetService = Depends(_reset_service),
) -> MessageResponse:
    """Verschickt einen Zuruecksetzen-Link, falls die Adresse existiert.

    Die Antwort ist immer dieselbe — sonst waere sie eine Auskunft darueber, welche
    E-Mail-Adressen ein Konto haben.
    """
    await svc.request_reset(req.email)
    return MessageResponse(message="If this email exists, a reset link has been sent")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    req: ResetPasswordRequest,
    svc: PasswordResetService = Depends(_reset_service),
) -> MessageResponse:
    """Setzt das Passwort mit einem Einmaltoken neu."""
    await svc.reset_password(req.token, req.password)
    return MessageResponse(message="Password updated successfully")


@router.post("/accept-invitation", response_model=MessageResponse)
async def accept_invitation(
    req: AcceptInvitationRequest,
    svc: InvitationService = Depends(_invitation_service),
) -> MessageResponse:
    """Nimmt eine Einladung an und setzt das erste Passwort.

    Erst damit kann sich der Nutzer anmelden — vorher hat er keinen
    ``password_hash``. Eine Mandantenzuordnung entsteht dabei **nicht**; die kommt
    aus der Nutzerverwaltung.
    """
    await svc.accept_invitation(req.token, req.password)
    return MessageResponse(message="Invitation accepted. You can now log in.")


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    payload: dict = Depends(get_jwt_payload),
) -> UserResponse:
    """Der angemeldete Nutzer und der Mandant *dieser Sitzung*.

    Rolle und Aktivzustand kommen frisch aus der Datenbank, die ``mandant_id`` aus
    dem Token: Sie ist eine Eigenschaft der Sitzung, nicht des Nutzers.
    """
    mandant_id_str: str | None = payload.get("mandant_id")
    mandant_id = UUID(mandant_id_str) if mandant_id_str else None
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        role=UserRole(current_user.role),
        mandant_id=mandant_id,
        is_active=current_user.is_active,
    )


# ─── User management endpoints ───────────────────────────────────────────────


async def _als_antwort(
    users: list[User],
    inv_svc: InvitationService,
    assign_svc: MandantAssignmentService,
) -> list[UserDetailResponse]:
    """Baut die Antwort fuer eine Liste von Nutzern — samt Mandanten und Einladungsstand.

    Ein gemeinsamer Helfer, weil vier Endpunkte dieselbe Antwort brauchen. Vorher
    stand der Aufbau viermal fast gleich im Router; ein fuenftes Feld haette an vier
    Stellen nachgetragen werden muessen, und genau daraus entstehen die stillen
    Widersprueche, nach denen Frage 1 des Merge-Checks sucht.

    Die Mandanten kommen in **einer** Abfrage fuer alle Nutzer. Der Einladungsstand
    ist weiterhin eine Abfrage pro Nutzer — ein bestehender Punkt, der hier nicht
    mitbehoben wird, um die Aenderung klein zu halten.
    """
    mandanten = await assign_svc.mandants_by_user([u.id for u in users])
    antworten = []
    for user in users:
        antworten.append(
            UserDetailResponse(
                id=user.id,
                email=user.email,
                role=UserRole(user.role),
                is_active=user.is_active,
                invitation_status=await inv_svc.get_invitation_status(user.id),
                mandants=[
                    MandantInfo(id=m.id, name=m.name)
                    for m in mandanten.get(user.id, [])
                ],
            )
        )
    return antworten


async def _einzeln(
    user: User,
    inv_svc: InvitationService,
    assign_svc: MandantAssignmentService,
) -> UserDetailResponse:
    """Dasselbe fuer einen einzelnen Nutzer."""
    return (await _als_antwort([user], inv_svc, assign_svc))[0]


@users_router.get("", response_model=list[UserDetailResponse])
async def list_users(
    actor: User = Depends(require_role("mandant_admin")),
    svc: UserManagementService = Depends(_user_mgmt_service),
    inv_svc: InvitationService = Depends(_invitation_service),
    assign_svc: MandantAssignmentService = Depends(_mandant_assignment_service),
) -> list[UserDetailResponse]:
    """Die Nutzer, die der Handelnde sehen darf.

    Ein Admin sieht alle, ein Mandant-Admin nur die, die einen Mandanten mit ihm
    teilen — die Auswahl trifft ``UserManagementService.list_users``.
    """
    users = await svc.list_users(actor)
    return await _als_antwort(users, inv_svc, assign_svc)


@users_router.get("/assignable-mandants", response_model=list[MandantInfo])
async def list_assignable_mandants(
    actor: User = Depends(require_role("mandant_admin")),
    assign_svc: MandantAssignmentService = Depends(_mandant_assignment_service),
) -> list[MandantInfo]:
    """Die Mandanten, denen der Anmeldende Nutzer zuordnen darf.

    Getrennt von `GET /mandants`, das der Mandantenverwaltung gehoert und `admin`
    verlangt. Ein Mandant-Admin braucht die Auswahlliste fuer seine eigenen
    Mandanten, aber nicht die Mandantenverwaltung — deshalb ein eigener Endpunkt mit
    eigener Schwelle statt einer Aufweitung des bestehenden (Entscheidung E2).

    Die Route steht **vor** `/{user_id}`, damit die Reihenfolge der Deklaration
    keine Rolle spielen muss; `user_id` ist ohnehin als UUID typisiert und wuerde
    `assignable-mandants` nicht annehmen.
    """
    mandanten = await assign_svc.assignable_mandants(actor)
    return [MandantInfo(id=m.id, name=m.name) for m in mandanten]


@users_router.post(
    "", response_model=UserDetailResponse, status_code=status.HTTP_201_CREATED
)
async def create_user(
    req: CreateUserRequest,
    actor: User = Depends(require_role("mandant_admin")),
    svc: UserManagementService = Depends(_user_mgmt_service),
    inv_svc: InvitationService = Depends(_invitation_service),
    assign_svc: MandantAssignmentService = Depends(_mandant_assignment_service),
) -> UserDetailResponse:
    """Legt einen Nutzer an, ordnet ihn zu und laedt ihn ein."""
    user = await svc.create_user(actor, str(req.email), req.role.value, req.mandant_ids)
    return await _einzeln(user, inv_svc, assign_svc)


@users_router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user(
    user_id: UUID,
    actor: User = Depends(require_role("mandant_admin")),
    svc: UserManagementService = Depends(_user_mgmt_service),
    inv_svc: InvitationService = Depends(_invitation_service),
    assign_svc: MandantAssignmentService = Depends(_mandant_assignment_service),
) -> UserDetailResponse:
    """Ein einzelner Nutzer, sofern der Handelnde ihn sehen darf."""
    user = await svc.get_user(actor, user_id)
    return await _einzeln(user, inv_svc, assign_svc)


@users_router.patch("/{user_id}", response_model=UserDetailResponse)
async def update_user(
    user_id: UUID,
    req: UpdateUserRequest,
    actor: User = Depends(require_role("mandant_admin")),
    svc: UserManagementService = Depends(_user_mgmt_service),
    inv_svc: InvitationService = Depends(_invitation_service),
    assign_svc: MandantAssignmentService = Depends(_mandant_assignment_service),
) -> UserDetailResponse:
    """Aendert einen Nutzer — inklusive Abgleich der Mandantenzuordnungen.

    ``exclude_unset`` ist wesentlich: Nur mitgesendete Felder wirken. Fehlt
    ``mandant_ids``, bleiben die Zuordnungen unberuehrt, ein Rollenwechsel loescht
    also keine Zugriffe.
    """
    user = await svc.update_user(actor, user_id, req.model_dump(exclude_unset=True))
    return await _einzeln(user, inv_svc, assign_svc)


@users_router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    actor: User = Depends(require_role("mandant_admin")),
    svc: UserManagementService = Depends(_user_mgmt_service),
) -> None:
    """Loescht einen Nutzer. Sich selbst zu loeschen ist ausgeschlossen."""
    await svc.delete_user(actor, user_id)


@users_router.post("/{user_id}/resend-invitation", response_model=MessageResponse)
async def resend_invitation(
    user_id: UUID,
    actor: User = Depends(require_role("mandant_admin")),
    svc: UserManagementService = Depends(_user_mgmt_service),
    inv_svc: InvitationService = Depends(_invitation_service),
) -> MessageResponse:
    """Schickt die Einladung erneut und macht die vorige ungueltig.

    Bei einer schon angenommenen Einladung 400: Ein neuer Link wuerde nichts
    bewirken und den Eindruck erwecken, das Passwort sei zuruecksetzbar — dafuer
    gibt es ``/auth/forgot-password``.
    """
    user = await svc.get_user(actor, user_id)
    # Check if already accepted
    inv_status = await inv_svc.get_invitation_status(user.id)
    if inv_status == "accepted":
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has already accepted their invitation",
        )
    await inv_svc.send_invitation(user)
    return MessageResponse(message="Invitation resent")


# ─── Mandant assignment endpoints ─────────────────────────────────────────────
#
# Schwelle `mandant_admin` statt `admin` (Entscheidung E2): Ein Mandant-Admin darf
# Nutzer seinen *eigenen* Mandanten zuordnen. Welche das sind, entscheidet
# `MandantAssignmentService` — die Rollenschwelle hier laesst ihn nur an den Endpunkt,
# die Auswahl der erlaubten Mandanten passiert im Service. Deshalb bekommt er den
# Handelnden uebergeben und nicht nur die IDs.


@mandants_router.post(
    "/{mandant_id}/users",
    response_model=MandantUserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_user_to_mandant(
    mandant_id: UUID,
    req: MandantUserAssignRequest,
    actor: User = Depends(require_role("mandant_admin")),
    svc: MandantAssignmentService = Depends(_mandant_assignment_service),
) -> MandantUserResponse:
    """Ordnet einen Nutzer einem Mandanten zu.

    Fuer mehrere Zuordnungen auf einmal ist ``PATCH /users/{id}`` mit
    ``mandant_ids`` der bessere Weg: ein Aufruf, ein Endstand.
    """
    mu = await svc.assign_user(actor, mandant_id, req.user_id)
    return MandantUserResponse(
        mandant_id=mu.mandant_id,
        user_id=mu.user_id,
        created_at=mu.created_at,
    )


@mandants_router.delete(
    "/{mandant_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def unassign_user_from_mandant(
    mandant_id: UUID,
    user_id: UUID,
    actor: User = Depends(require_role("mandant_admin")),
    svc: MandantAssignmentService = Depends(_mandant_assignment_service),
) -> None:
    """Loest eine Zuordnung. Die eigene letzte bleibt (Selbstaussperrung)."""
    await svc.unassign_user(actor, mandant_id, user_id)
