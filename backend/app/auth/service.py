"""Anmeldung, Nutzerverwaltung, Einladungen und Mandantenzuordnung.

Hier entsteht die Zugriffsentscheidung des Systems: welche Rolle jemand hat und zu
welchen Mandanten er gehoert. Ein Fehler in diesem Modul ist kein Anzeigefehler,
sondern ein Zugriff auf fremde Daten — deshalb sind die Regeln an den betroffenen
Stellen ausgeschrieben und nicht nur befolgt.

Siehe ``docs/mandantenfaehigkeit-plan.md`` fuer die Befunde M1-M14 und die
Entscheidungen E1-E4, auf die die Kommentare verweisen.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.email import send_invitation_email, send_password_reset_email
from app.auth.models import (
    Mandant,
    MandantUser,
    PasswordResetToken,
    User,
    UserInvitation,
    UserRole,
)
from app.auth.security import (
    create_access_token,
    generate_raw_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.core.config import settings
from app.partners.models import AuditLog

log = structlog.get_logger()


def _utcnow() -> datetime:
    """Jetzt, als naiver UTC-Wert — so speichern die Modelle ihre Zeitstempel."""
    return datetime.now(UTC).replace(tzinfo=None)


def _as_utc_naive(value: datetime) -> datetime:
    """Bringt einen Zeitstempel auf naives UTC, damit Vergleiche zulaessig sind.

    Werte aus der Datenbank sind naiv, Tests koennen zonenbehaftete einsetzen. Ein
    Vergleich der beiden wirft in Python einen ``TypeError``.
    """
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


class AuthService:
    """Anmelden, Mandantenwahl, Abmelden."""

    def __init__(self, session: AsyncSession) -> None:
        """Bindet den Dienst an die Sitzung des laufenden Aufrufs."""
        self.session = session

    async def login(self, email: str, password: str) -> dict:
        """Prueft die Anmeldedaten und gibt Token samt Mandantenlage zurueck.

        Jeder Fehlschlag endet in derselben 401 mit derselben Meldung, und der
        Passwortvergleich laeuft auch dann, wenn es den Nutzer nicht gibt: Sonst
        waere an der Antwortzeit ablesbar, welche E-Mail-Adressen ein Konto haben.

        Ausnahmen davon sind zwei Faelle, die dem Nutzer selbst helfen und nichts
        verraten, was er nicht schon weiss: ein deaktiviertes Konto und eine noch
        nicht angenommene Einladung.
        """
        user = await self._get_user_by_email(email)

        # Constant-time failure path: always attempt verify even if user not found
        dummy_hash = "$2b$12$mqi/bTXx0seaYIZVL7lMRO1AtXJ/thdGanrdd.l/pZNsH90CtedI2"
        if user is None:
            verify_password(password, dummy_hash)
            log.warning("login_failed", email=email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account disabled",
            )

        if user.password_hash is None:
            verify_password(password, dummy_hash)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invitation pending – set your password first",
            )

        if not verify_password(password, user.password_hash):
            log.warning("login_failed", email=email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        mandants = await self._get_mandants_for_user(user)

        # Ein Weg fuer alle Rollen — auch fuer Admins (Befund M4).
        #
        # Vorher kehrte diese Funktion fuer `admin` frueh zurueck und meldete
        # `requires_mandant_selection: False`, unabhaengig von der Anzahl der
        # Mandanten. Ein Admin mit zwei Mandanten bekam damit kein Auswahlsignal; die
        # Auswahlseite erschien nur, weil `MandantRequiredRoute` im Frontend das
        # fehlende `mandant_id` bemerkte und umleitete — ein Umweg, den niemand
        # entworfen hatte. Die Sonderstellung des Admins betrifft seine *Reichweite*
        # (siehe `_get_mandants_for_user`), nicht die Frage, ob er waehlen muss.
        #
        # Genau ein Mandant: direkt ins Token, es gibt nichts zu waehlen.
        # Keiner oder mehrere: das Token bleibt ohne `mandant_id`. Bei mehreren waehlt
        # der Client ueber /select-mandant; bei keinem gibt es nichts zu waehlen und
        # die leere `mandants`-Liste sagt dem Client, dass eine Zuordnung fehlt
        # (Befund M6).
        selected_id: UUID | None = mandants[0].id if len(mandants) == 1 else None

        token = create_access_token(
            {
                "sub": str(user.id),
                "role": user.role,
                "mandant_id": str(selected_id) if selected_id else None,
            }
        )
        await self._write_audit(
            user.id,
            selected_id,
            "auth.login",
            {"email": email, "role": user.role, "mandants": len(mandants)},
        )
        return {
            "access_token": token,
            "mandants": mandants,
            "requires_mandant_selection": len(mandants) > 1,
        }

    async def select_mandant(self, user: User, mandant_id: UUID) -> str:
        """Tauscht das Token gegen eines, das den gewaehlten Mandanten traegt.

        Geprueft wird beides, und in dieser Reihenfolge:

        1. **Darf der Nutzer?** Fuer Admins ja, fuer alle anderen nur bei einer Zeile
           in ``mandant_users`` (ADR-001).
        2. **Gibt es den Mandanten noch, und ist er aktiv?** Diese zweite Pruefung
           fehlte (Befund M9): ``_get_mandants_for_user`` filtert auf
           ``is_active``, ``select_mandant`` tat es nicht. Weil
           ``deactivate_mandant`` die Zeilen in ``mandant_users`` stehen laesst,
           liess sich eine bekannte Mandanten-ID weiter in ein gueltiges Token
           verwandeln, obwohl der Mandant abgeschaltet war.
        """
        mandant = await self.session.get(Mandant, mandant_id)
        if mandant is None or not mandant.is_active:
            # Dieselbe Antwort wie bei fehlender Berechtigung: Ob ein Mandant nicht
            # existiert oder nur abgeschaltet ist, muss ein Aussenstehender nicht
            # unterscheiden koennen.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to mandant denied",
            )

        if user.role != UserRole.admin.value:
            result = await self.session.exec(
                select(MandantUser).where(
                    MandantUser.user_id == user.id,
                    MandantUser.mandant_id == mandant_id,
                )
            )
            if result.first() is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access to mandant denied",
                )

        await self._write_audit(
            user.id,
            mandant_id,
            "auth.select_mandant",
            {"email": user.email, "role": user.role, "mandant": mandant.name},
        )
        return create_access_token(
            {"sub": str(user.id), "role": user.role, "mandant_id": str(mandant_id)}
        )

    async def logout(self, user: User, mandant_id: UUID | None) -> None:
        """Haelt das Abmelden im Protokoll fest.

        Zu verwerfen ist nichts: Die Token sind zustandslos und laufen von selbst ab.
        """
        await self._write_audit(
            user.id, mandant_id, "auth.logout", {"email": user.email, "role": user.role}
        )

    async def _write_audit(
        self, actor_id: UUID, mandant_id: UUID | None, event_type: str, payload: dict
    ) -> None:
        """Schreibt einen Protokolleintrag und schliesst die Transaktion ab.

        ``mandant_id`` darf ``None`` sein — beim Anmelden ohne Mandantenwahl gibt es
        noch keinen Bezug.
        """
        entry = AuditLog(
            mandant_id=mandant_id,
            event_type=event_type,
            actor_id=actor_id,
            payload=payload,
        )
        self.session.add(entry)
        await self.session.commit()
        log.info("audit", event_type=event_type, actor_id=str(actor_id))

    async def _get_user_by_email(self, email: str) -> User | None:
        """Sucht einen Nutzer an der Adresse; vergleicht in Kleinschreibung.

        Adressen werden beim Anlegen kleingeschrieben gespeichert, damit sich niemand
        mit derselben Adresse in anderer Schreibweise ein zweites Konto anlegt.
        """
        result = await self.session.exec(
            select(User).where(User.email == email.lower())
        )
        return result.first()

    async def _get_mandants_for_user(self, user: User) -> list[Mandant]:
        """Die Mandanten, die diesem Nutzer zur Auswahl stehen.

        **Admins bekommen alle aktiven Mandanten** — auch die, zu denen keine Zeile in
        ``mandant_users`` existiert (Befund M5, Entscheidung E3).

        Der Grund: ``require_mandant_access`` laesst einen Admin nach ADR-001 auf
        *jeden* Mandanten zugreifen. Solange diese Funktion ihm nur die verknuepften
        anbot, gab es zwei Definitionen von „welche Mandanten gehoeren zu diesem
        Nutzer", die nicht uebereinstimmten — mit der Folge, dass ein Mandant ohne
        Zuordnung ueber die Oberflaeche unerreichbar war, obwohl die Berechtigung
        reichte. Genau dieser Zustand trat am 2026-09-10 ein: ein Mandant mit 2.597
        Partnern, den niemand auswaehlen konnte.

        Fuer alle anderen Rollen bleibt es bei den verknuepften Mandanten.

        In beiden Faellen zaehlen nur **aktive** Mandanten. Ein deaktivierter erscheint
        nicht zur Auswahl, und ``select_mandant`` weist ihn zusaetzlich ab (M9).
        """
        if user.role == UserRole.admin.value:
            result = await self.session.exec(
                select(Mandant)
                .where(Mandant.is_active == True)  # noqa: E712
                .order_by(Mandant.name)
            )
            return list(result.all())

        result = await self.session.exec(
            select(Mandant)
            .join(MandantUser, Mandant.id == MandantUser.mandant_id)
            .where(
                MandantUser.user_id == user.id, Mandant.is_active == True
            )  # noqa: E712
            .order_by(Mandant.name)
        )
        return list(result.all())


class PasswordResetService:
    """Vergessene Passwoerter — Link anfordern und einloesen."""

    def __init__(self, session: AsyncSession) -> None:
        """Bindet den Dienst an die Sitzung des laufenden Aufrufs."""
        self.session = session

    async def request_reset(self, email: str) -> None:
        """Verschickt einen Zuruecksetzen-Link, falls es die Adresse gibt.

        Gibt es sie nicht, passiert nichts — und zwar ohne Fehler. Eine
        unterscheidbare Antwort waere eine Auskunft darueber, welche Adressen ein
        Konto haben. Der Link ist 60 Minuten gueltig; gespeichert wird nur sein
        SHA-256-Hash (ADR-003).
        """
        result = await self.session.exec(
            select(User).where(User.email == email.lower())
        )
        user = result.first()

        if user is None:
            return  # Silent no-op (story 002: always return 200)

        raw_token = generate_raw_token()
        token_hash_val = hash_token(raw_token)
        expires_at = _utcnow() + timedelta(minutes=60)

        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash_val,
            expires_at=expires_at,
        )
        self.session.add(reset_token)
        await self.session.commit()

        reset_url = f"{settings.frontend_url}/reset-password?token={raw_token}"
        await send_password_reset_email(user.email, reset_url)

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        """Setzt das Passwort neu und verbrennt alle offenen Token dieses Nutzers.

        Das Entwerten der uebrigen Token ist der Punkt: Wer mehrfach auf „Passwort
        vergessen" geklickt hat, hinterlaesst sonst gueltige Links in mehreren
        E-Mails, die nach der Aenderung weiter funktionieren wuerden.
        """
        incoming_hash = hash_token(raw_token)

        result = await self.session.exec(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == incoming_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > _utcnow(),
            )
        )
        reset_token = result.first()

        if reset_token is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token expired or invalid",
            )

        user = await self.session.get(User, reset_token.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token",
            )

        user.password_hash = hash_password(new_password)
        user.updated_at = _utcnow()
        reset_token.used_at = _utcnow()

        # Invalidate all remaining unused tokens for this user
        other_tokens_result = await self.session.exec(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == reset_token.user_id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.id != reset_token.id,
            )
        )
        for old_token in other_tokens_result.all():
            old_token.used_at = _utcnow()
            self.session.add(old_token)

        self.session.add(user)
        self.session.add(reset_token)
        await self.session.commit()


ROLES_MANDANT_ADMIN_CAN_CREATE = {UserRole.accountant.value, UserRole.viewer.value}


class UserManagementService:
    """Nutzer anlegen, aendern, auflisten, loeschen.

    Zwei Grenzen gelten durchgehend und unabhaengig voneinander:

    * **Rolle** — ein Mandant-Admin darf nur ``accountant`` und ``viewer`` vergeben,
      also keine Rolle auf oder ueber seiner eigenen Stufe.
    * **Mandant** — ein Mandant-Admin sieht und aendert nur Nutzer, die einen
      Mandanten mit ihm teilen.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Bindet den Dienst an die Sitzung des laufenden Aufrufs."""
        self.session = session

    async def list_users(self, actor: User) -> list[User]:
        """Die Nutzer, die ``actor`` sehen darf.

        Admin: alle. Mandant-Admin: die Nutzer seiner Mandanten. Ohne eigene
        Zuordnung eine leere Liste — nicht alle.
        """
        if actor.role == UserRole.admin.value:
            result = await self.session.exec(select(User).order_by(User.email))
            return list(result.all())
        # mandant_admin: only users sharing a mandant
        actor_mandants = await self.session.exec(
            select(MandantUser.mandant_id).where(MandantUser.user_id == actor.id)
        )
        mandant_ids = list(actor_mandants.all())
        if not mandant_ids:
            return []
        result = await self.session.exec(
            select(User)
            .join(MandantUser, User.id == MandantUser.user_id)
            .where(MandantUser.mandant_id.in_(mandant_ids))
            .order_by(User.email)
        )
        return list(result.unique().all())

    async def create_user(
        self,
        actor: User,
        email: str,
        role: str,
        mandant_ids: list[UUID] | None = None,
    ) -> User:
        """Legt einen Nutzer an, ordnet ihn zu und schickt die Einladung.

        Die Reihenfolge ist wesentlich: **erst zuordnen, dann einladen.** ADR-004
        legt fest, dass ein SMTP-Fehler die Anlage des Nutzers nicht zurueckrollt.
        Stuende die Zuordnung dahinter, wuerde sie an einem Mailfehler scheitern —
        und der Nutzer waere angelegt, aber ohne Mandanten, also genau im Zustand aus
        Befund M6.

        Ohne ``mandant_ids`` entsteht bewusst ein Nutzer ohne Mandanten; das ist das
        bisherige Verhalten und bleibt erlaubt.
        """
        # Role permission check
        if (
            actor.role == UserRole.mandant_admin.value
            and role not in ROLES_MANDANT_ADMIN_CAN_CREATE
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to assign this role",
            )
        if actor.role not in (UserRole.admin.value, UserRole.mandant_admin.value):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role"
            )

        # Duplicate check
        existing = await self.session.exec(
            select(User).where(User.email == email.lower())
        )
        if existing.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists",
            )

        user = User(email=email.lower(), role=role)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        # Zuordnung VOR dem Einladungsversand — siehe Docstring (ADR-004).
        if mandant_ids:
            assignment_svc = MandantAssignmentService(self.session)
            await assignment_svc.set_mandants(actor, user, mandant_ids)

        # Fire invitation – SMTP failure must NOT roll back user creation (ADR-004)
        invitation_svc = InvitationService(self.session)
        await invitation_svc.send_invitation(user)

        return user

    async def get_user(self, actor: User, user_id: UUID) -> User:
        """Ein einzelner Nutzer, sofern ``actor`` ihn sehen darf."""
        user = await self.session.get(User, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        await self._check_mandant_access(actor, user)
        return user

    async def update_user(self, actor: User, user_id: UUID, patch: dict) -> User:
        """Aendert einen Nutzer; ``mandant_ids`` im Patch gleicht die Zuordnungen ab.

        Der Abgleich wirkt nur innerhalb der Mandanten, die ``actor`` zuordnen darf
        (siehe ``MandantAssignmentService.set_mandants``). Fehlt ``mandant_ids`` im
        Patch, bleiben die Zuordnungen unberuehrt — ein Rollenwechsel loescht also
        keine Zugriffe.
        """
        user = await self.session.get(User, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        await self._check_mandant_access(actor, user)

        if "role" in patch and patch["role"] is not None:
            new_role = (
                patch["role"].value
                if hasattr(patch["role"], "value")
                else patch["role"]
            )
            if (
                actor.role == UserRole.mandant_admin.value
                and new_role not in ROLES_MANDANT_ADMIN_CAN_CREATE
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions",
                )
            user.role = new_role

        if "email" in patch and patch["email"] is not None:
            user.email = str(patch["email"]).lower()
        if "is_active" in patch and patch["is_active"] is not None:
            user.is_active = patch["is_active"]

        user.updated_at = _utcnow()
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        if patch.get("mandant_ids") is not None:
            assignment_svc = MandantAssignmentService(self.session)
            await assignment_svc.set_mandants(actor, user, patch["mandant_ids"])

        return user

    async def _check_mandant_access(self, actor: User, target: User) -> None:
        """Wirft 403, wenn ``actor`` diesen Nutzer nicht anfassen darf.

        Fuer Admins immer erlaubt. Sonst muessen sich die Mandanten beider
        ueberschneiden. Ein Nutzer **ohne** Zuordnung ist damit fuer einen
        Mandant-Admin nicht bearbeitbar — fuer das *Zuordnen* gilt bewusst eine
        andere, weitere Regel, siehe ``MandantAssignmentService``.
        """
        if actor.role == UserRole.admin.value:
            return
        # Mandant-Admin: both actor and target must share a mandant
        actor_mandants = await self.session.exec(
            select(MandantUser.mandant_id).where(MandantUser.user_id == actor.id)
        )
        actor_mandant_ids = {r for r in actor_mandants.all()}

        target_mandants = await self.session.exec(
            select(MandantUser.mandant_id).where(MandantUser.user_id == target.id)
        )
        target_mandant_ids = {r for r in target_mandants.all()}

        if not actor_mandant_ids.intersection(target_mandant_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

    async def delete_user(self, actor: User, user_id: UUID) -> None:
        """Loescht einen Nutzer; sich selbst zu loeschen ist ausgeschlossen."""
        user = await self.session.get(User, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        if str(user.id) == str(actor.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself"
            )
        await self._check_mandant_access(actor, user)
        await self.session.delete(user)
        await self.session.commit()


class InvitationService:
    """Einladungen versenden, annehmen und ihren Stand ermitteln."""

    def __init__(self, session: AsyncSession) -> None:
        """Bindet den Dienst an die Sitzung des laufenden Aufrufs."""
        self.session = session

    async def send_invitation(self, user: User) -> UserInvitation:
        """Erzeugt eine Einladung und verschickt sie; entwertet aeltere.

        Ein Fehler beim Versand wird geschluckt (ADR-004): Der Nutzer ist bereits
        angelegt, und ein Rollback wuerde ihn wieder entfernen. Die Einladung laesst
        sich erneut senden.
        """
        # Invalidate all pending invitations for this user
        await self._invalidate_pending(user.id)

        raw_token = generate_raw_token()
        expires_at = _utcnow() + timedelta(days=settings.invitation_expire_days)
        invitation = UserInvitation(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
        )
        self.session.add(invitation)
        await self.session.commit()
        await self.session.refresh(invitation)

        invite_url = f"{settings.frontend_url}/accept-invitation?token={raw_token}"
        # SMTP failure swallowed – user already created (ADR-004)
        await send_invitation_email(
            user.email, invite_url, settings.invitation_expire_days
        )
        return invitation

    async def accept_invitation(self, raw_token: str, password: str) -> None:
        """Nimmt eine Einladung an und setzt das erste Passwort.

        Erst danach kann sich der Nutzer anmelden. Eine Mandantenzuordnung entsteht
        hier **nicht** — sie kommt aus der Nutzerverwaltung. Ohne sie landet der
        Nutzer im Zustand aus Befund M6.
        """
        incoming_hash = hash_token(raw_token)
        result = await self.session.exec(
            select(UserInvitation).where(
                UserInvitation.token_hash == incoming_hash,
                UserInvitation.accepted_at.is_(None),
            )
        )
        invitation = result.first()

        if invitation is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token",
            )
        if _as_utc_naive(invitation.expires_at) <= _utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation expired",
            )

        user = await self.session.get(User, invitation.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token"
            )

        user.password_hash = hash_password(password)
        user.updated_at = _utcnow()
        invitation.accepted_at = _utcnow()

        self.session.add(user)
        self.session.add(invitation)
        await self.session.commit()

    async def get_invitation_status(self, user_id: UUID) -> str:
        """``"pending"``, ``"accepted"`` oder ``"expired"`` fuer die jüngste Einladung.

        Ein Nutzer ohne jede Einladung gilt als ``"accepted"``: Das sind die vor der
        Einladungsfunktion angelegten Konten, etwa der eingerichtete Admin. Sie als
        ``"pending"`` zu melden waere falsch — sie haben ein Passwort.
        """
        result = await self.session.exec(
            select(UserInvitation)
            .where(UserInvitation.user_id == user_id)
            .order_by(UserInvitation.created_at.desc())
        )
        invitation = result.first()
        if invitation is None:
            return "accepted"  # Pre-invitation users (e.g. seeded admin)
        if invitation.accepted_at is not None:
            return "accepted"
        if _as_utc_naive(invitation.expires_at) <= _utcnow():
            return "expired"
        return "pending"

    async def _invalidate_pending(self, user_id: UUID) -> None:
        """Entwertet alle offenen Einladungen dieses Nutzers.

        Umgesetzt als ``accepted_at``-Stempel: Das Feld heisst „angenommen", wird
        hier aber als „verbraucht" benutzt. Der Effekt ist der gewuenschte — der
        Token greift nicht mehr —, die Benennung bleibt schief.
        """
        result = await self.session.exec(
            select(UserInvitation).where(
                UserInvitation.user_id == user_id,
                UserInvitation.accepted_at.is_(None),
            )
        )
        for inv in result.all():
            inv.accepted_at = _utcnow()  # mark as "used" to invalidate
            self.session.add(inv)
        await self.session.commit()


class MandantAssignmentService:
    """Verwaltet die Zeilen in ``mandant_users`` — die Zugriffsentscheidung des Systems.

    Wer welchem Mandanten zugeordnet ist, entscheidet ueber jeden Datenzugriff
    (``require_mandant_access``) und ueber die Auswahl nach dem Anmelden
    (``AuthService._get_mandants_for_user``). Ein Fehler hier ist kein Anzeigefehler,
    sondern ein Zugriff auf fremde Daten. Deshalb protokolliert jede Aenderung.

    Rechte (Entscheidung E2 des Mandantenfaehigkeitsplans)
    ------------------------------------------------------
    * **admin** — darf jeden Nutzer jedem aktiven Mandanten zuordnen.
    * **mandant_admin** — darf nur *seinen eigenen* Mandanten zuordnen, und dabei nur
      Nutzer, die er ohnehin sehen kann: solche, die schon einen Mandanten mit ihm
      teilen, oder solche **ohne jede Zuordnung** (also frisch eingeladene). Ohne die
      zweite Haelfte waere der eigentliche Arbeitsablauf unmoeglich — Nutzer anlegen,
      dann zuordnen —, denn ``create_user`` legt keine Zuordnung an.
    * alle anderen Rollen — duerfen nicht zuordnen.

    Der Zuschnitt verhindert, dass ein Mandant-Admin einen fremden Nutzer in seinen
    Mandanten zieht und dadurch dessen Existenz und E-Mail-Adresse erfaehrt.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Bindet den Dienst an die Sitzung des laufenden Aufrufs."""
        self.session = session

    # ─── Rechte ──────────────────────────────────────────────────────────────

    async def assignable_mandants(self, actor: User) -> list[Mandant]:
        """Die aktiven Mandanten, denen ``actor`` Nutzer zuordnen darf.

        Diese Liste ist die einzige Quelle fuer die Rechtepruefung **und** fuer die
        Auswahl, die die Nutzerverwaltung anbietet. Beides aus derselben Funktion zu
        speisen ist Absicht: Zwei Definitionen, die auseinanderlaufen koennen, waren
        die Ursache von Befund M5.
        """
        if actor.role == UserRole.admin.value:
            result = await self.session.exec(
                select(Mandant)
                .where(Mandant.is_active == True)  # noqa: E712
                .order_by(Mandant.name)
            )
            return list(result.all())

        if actor.role == UserRole.mandant_admin.value:
            result = await self.session.exec(
                select(Mandant)
                .join(MandantUser, Mandant.id == MandantUser.mandant_id)
                .where(
                    MandantUser.user_id == actor.id,
                    Mandant.is_active == True,  # noqa: E712
                )
                .order_by(Mandant.name)
            )
            return list(result.all())

        return []

    async def _require_mandant_assignable(self, actor: User, mandant_id: UUID) -> None:
        """Wirft 403, wenn ``actor`` diesem Mandanten keine Nutzer zuordnen darf."""
        erlaubt = {m.id for m in await self.assignable_mandants(actor)}
        if mandant_id not in erlaubt:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this mandant",
            )

    async def _require_user_assignable(self, actor: User, target: User) -> None:
        """Wirft 403, wenn ``actor`` diesen *Nutzer* nicht zuordnen darf.

        Fuer Admins immer erlaubt. Fuer Mandant-Admins nur, wenn der Nutzer noch
        keinem Mandanten zugeordnet ist oder bereits einen mit dem Handelnden teilt
        (siehe Klassenbeschreibung).
        """
        if actor.role == UserRole.admin.value:
            return

        ziel_mandanten = set(
            (
                await self.session.exec(
                    select(MandantUser.mandant_id).where(
                        MandantUser.user_id == target.id
                    )
                )
            ).all()
        )
        if not ziel_mandanten:
            return  # Frisch eingeladen — genau der Fall, um den es geht.

        eigene = set(
            (
                await self.session.exec(
                    select(MandantUser.mandant_id).where(
                        MandantUser.user_id == actor.id
                    )
                )
            ).all()
        )
        if not ziel_mandanten & eigene:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this user",
            )

    # ─── Einzelne Zuordnung ──────────────────────────────────────────────────

    async def assign_user(
        self, actor: User, mandant_id: UUID, user_id: UUID
    ) -> MandantUser:
        """Ordnet einen Nutzer einem Mandanten zu und protokolliert es."""
        mandant = await self.session.get(Mandant, mandant_id)
        if mandant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Mandant not found"
            )
        user = await self.session.get(User, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        await self._require_mandant_assignable(actor, mandant_id)
        await self._require_user_assignable(actor, user)

        existing = await self.session.exec(
            select(MandantUser).where(
                MandantUser.mandant_id == mandant_id,
                MandantUser.user_id == user_id,
            )
        )
        if existing.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already assigned to this mandant",
            )

        mu = MandantUser(mandant_id=mandant_id, user_id=user_id)
        self.session.add(mu)
        await self._protokolliere(
            actor, mandant, user, "auth.mandant_assigned", commit=True
        )
        await self.session.refresh(mu)
        return mu

    async def unassign_user(self, actor: User, mandant_id: UUID, user_id: UUID) -> None:
        """Loest eine Zuordnung und protokolliert es."""
        mandant = await self.session.get(Mandant, mandant_id)
        user = await self.session.get(User, user_id)
        if mandant is None or user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
            )

        await self._require_mandant_assignable(actor, mandant_id)
        await self._require_user_assignable(actor, user)

        result = await self.session.exec(
            select(MandantUser).where(
                MandantUser.mandant_id == mandant_id,
                MandantUser.user_id == user_id,
            )
        )
        mu = result.first()
        if mu is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
            )

        alle = list(
            (
                await self.session.exec(
                    select(MandantUser.mandant_id).where(MandantUser.user_id == user_id)
                )
            ).all()
        )
        self._verhindere_selbstaussperrung(actor, user_id, len(alle) - 1)

        await self.session.delete(mu)
        await self._protokolliere(
            actor, mandant, user, "auth.mandant_unassigned", commit=True
        )

    def _verhindere_selbstaussperrung(
        self, actor: User, target_id: UUID, verbleibend: int
    ) -> None:
        """Verhindert, dass sich jemand seine letzte eigene Zuordnung nimmt.

        Geprueft wird der **Endstand**, nicht die einzelne Zeile: ``verbleibend`` ist
        die Anzahl der Zuordnungen, die der Nutzer nach der Aenderung noch haette.
        Eine Pruefung pro entfernter Zeile waere falsch — beim Entfernen aller drei
        Zuordnungen eines Nutzers saehe jede einzelne Pruefung noch drei vorhandene
        und liesse durch, obwohl am Ende null bleiben.

        Ohne Zuordnung kommt ein Nicht-Admin an keine Daten mehr und landet in der
        Sackgasse aus Befund M6 — und kann sich selbst nicht wieder eintragen, weil
        dafuer eine Zuordnung noetig waere. Fuer Admins gilt die Sperre nicht: Sie
        sehen seit Entscheidung E3 alle aktiven Mandanten, unabhaengig von
        ``mandant_users``.
        """
        if str(target_id) != str(actor.id) or actor.role == UserRole.admin.value:
            return
        if verbleibend > 0:
            return
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot remove your own last mandant assignment — "
                "you would lose access to the application"
            ),
        )

    # ─── Mehrere Zuordnungen auf einmal ──────────────────────────────────────

    async def set_mandants(
        self, actor: User, target: User, wunsch_ids: list[UUID]
    ) -> None:
        """Bringt die Zuordnungen von ``target`` auf den gewuenschten Stand.

        **Nur innerhalb der Mandanten, die ``actor`` zuordnen darf.** Zuordnungen zu
        allen anderen Mandanten bleiben unangetastet, auch wenn sie in ``wunsch_ids``
        fehlen.

        Das ist der Kern der Rechtepruefung an dieser Stelle: Ohne die Einschraenkung
        koennte ein Mandant-Admin von Mandant A einem Nutzer die Zuordnung zu Mandant B
        wegnehmen, indem er einfach nur ``[A]`` sendet. Ein Abgleich sieht harmlos aus
        und wirkt trotzdem auf Daten, die den Handelnden nichts angehen.

        Ein Mandant in ``wunsch_ids``, den ``actor`` nicht zuordnen darf, ergibt 403 —
        er wird nicht stillschweigend uebergangen, sonst meldet die Oberflaeche Erfolg
        fuer etwas, das nicht passiert ist.
        """
        erlaubte = {m.id for m in await self.assignable_mandants(actor)}
        wunsch = set(wunsch_ids)

        unerlaubt = wunsch - erlaubte
        if unerlaubt:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this mandant",
            )

        await self._require_user_assignable(actor, target)

        vorhanden = set(
            (
                await self.session.exec(
                    select(MandantUser.mandant_id).where(
                        MandantUser.user_id == target.id
                    )
                )
            ).all()
        )

        # Nur im erlaubten Bereich abgleichen — alles daneben bleibt, wie es ist.
        hinzu = wunsch - vorhanden
        weg = (vorhanden - wunsch) & erlaubte

        # Einmal gegen den Endstand pruefen, nicht je entfernte Zeile.
        self._verhindere_selbstaussperrung(
            actor, target.id, len((vorhanden - weg) | hinzu)
        )

        for mandant_id in sorted(hinzu, key=str):
            self.session.add(MandantUser(mandant_id=mandant_id, user_id=target.id))
            mandant = await self.session.get(Mandant, mandant_id)
            if mandant is not None:
                await self._protokolliere(
                    actor, mandant, target, "auth.mandant_assigned", commit=False
                )

        for mandant_id in sorted(weg, key=str):
            zeile = (
                await self.session.exec(
                    select(MandantUser).where(
                        MandantUser.mandant_id == mandant_id,
                        MandantUser.user_id == target.id,
                    )
                )
            ).first()
            if zeile is not None:
                await self.session.delete(zeile)
            mandant = await self.session.get(Mandant, mandant_id)
            if mandant is not None:
                await self._protokolliere(
                    actor, mandant, target, "auth.mandant_unassigned", commit=False
                )

        if hinzu or weg:
            await self.session.commit()

    # ─── Lesen ───────────────────────────────────────────────────────────────

    async def mandants_by_user(self, user_ids: list[UUID]) -> dict[UUID, list[Mandant]]:
        """Liefert die Mandanten mehrerer Nutzer in **einer** Abfrage.

        Bewusst als Sammelabfrage und nicht pro Nutzer: Die Nutzerliste ruft das fuer
        jede Zeile ab. ``invitation_status`` daneben ist heute noch eine Abfrage pro
        Nutzer — ein bekannter, hier nicht angefasster Punkt.
        """
        if not user_ids:
            return {}

        result = await self.session.exec(
            select(MandantUser.user_id, Mandant)
            .join(Mandant, Mandant.id == MandantUser.mandant_id)
            .where(MandantUser.user_id.in_(user_ids))
            .order_by(Mandant.name)
        )
        gruppiert: dict[UUID, list[Mandant]] = {uid: [] for uid in user_ids}
        for user_id, mandant in result.all():
            gruppiert.setdefault(user_id, []).append(mandant)
        return gruppiert

    async def _protokolliere(
        self,
        actor: User,
        mandant: Mandant,
        target: User,
        event_type: str,
        *,
        commit: bool,
    ) -> None:
        """Schreibt einen Protokolleintrag fuer eine Zuordnungsaenderung.

        ``commit=False`` fuer den Abgleich in ``set_mandants``, damit mehrere
        Aenderungen in einer Transaktion liegen: Entweder stimmt der Stand danach
        vollstaendig, oder es hat sich nichts geaendert.
        """
        self.session.add(
            AuditLog(
                mandant_id=mandant.id,
                event_type=event_type,
                actor_id=actor.id,
                payload={
                    "mandant": mandant.name,
                    "user_email": target.email,
                    "actor_email": actor.email,
                },
            )
        )
        if commit:
            await self.session.commit()
        log.info(
            "audit",
            event_type=event_type,
            actor_id=str(actor.id),
            mandant_id=str(mandant.id),
        )
