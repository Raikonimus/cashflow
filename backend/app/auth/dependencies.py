from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.models import MandantUser, User, UserRole
from app.auth.security import decode_access_token
from app.core.database import get_session

log = structlog.get_logger()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

ROLE_HIERARCHY: dict[str, int] = {
    UserRole.admin.value: 4,
    UserRole.mandant_admin.value: 3,
    UserRole.accountant.value: 2,
    UserRole.viewer.value: 1,
}


async def get_jwt_payload(token: str = Depends(oauth2_scheme)) -> dict:
    """Extract and verify JWT payload without DB lookup."""
    try:
        return decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    payload: dict = Depends(get_jwt_payload),
    session: AsyncSession = Depends(get_session),
) -> User:
    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await session.get(User, UUID(user_id_str))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(min_role: str):
    """
    Dependency factory: ensures the current user has at least `min_role`.

    Usage:
        @router.post("/...", dependencies=[Depends(require_role("accountant"))])
        async def endpoint(current_user: User = Depends(require_role("accountant"))):
    """

    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        user_level = ROLE_HIERARCHY.get(current_user.role, 0)
        required_level = ROLE_HIERARCHY.get(min_role, 999)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return current_user

    return dependency


async def require_mandant_access(
    mandant_id: UUID,
    current_user: User = Depends(get_current_user),
    payload: dict = Depends(get_jwt_payload),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Prueft zwei Dinge: den **gewaehlten** Mandanten und die **Zugehoerigkeit**.

    Zwei Schranken, zwei Zwecke
    ---------------------------
    1. **Die Auswahl muss zum Pfad passen.** Alle mandantengebundenen Endpunkte nehmen
       ihre ``mandant_id`` aus dem Pfad. Ohne diesen Vergleich waere die Auswahl beim
       Anmelden bloss Anzeigezustand: Ein Nutzer mit zwei Mandanten koennte mit einem
       fuer A gewaehlten Token die Endpunkte von B ansprechen. Das war Befund M10, und
       die Entscheidung dazu fiel in Stufe 5 auf *erzwingen* — siehe ADR-019.
    2. **Der Nutzer muss dem Mandanten zugeordnet sein.** Das ist die eigentliche
       Berechtigung und steht in ``mandant_users``.

    Warum die Auswahl **vor** der Rollenausnahme geprueft wird
    ----------------------------------------------------------
    Ein Admin umgeht die Zugehoerigkeitspruefung absichtlich. Diese Ausnahme nennt der
    Code „ADR-001 / RBAC design", doch ADR-001 ist die Entscheidung *Client-only
    Logout*; einen Entscheidungssatz zur Admin-Ausnahme gibt es nicht (Befund M17). Er
    umgeht damit aber **nicht** die Auswahl: Auch ein Admin muss sagen, in welchem Mandanten er arbeitet. Sonst haette
    gerade die Rolle mit der groessten Reichweite die schwaechste Bindung an das, was
    die Oberflaeche anzeigt.

    Fuer den Admin ist das keine Einschraenkung, sondern ein Zwischenschritt: ``login``
    liefert ihm alle aktiven Mandanten, und ``select-mandant`` gibt ihm zu jedem ein
    Token. Er erreicht weiter jeden Mandanten — er muss ihn nur benennen.

    Ein Token ohne ``mandant_id`` erreicht keinen dieser Endpunkte. Das trifft genau
    die Zustaende, in denen es auch nichts anzuzeigen gibt: mehrere Mandanten und noch
    keine Auswahl, oder gar keine Zuordnung (Befund M6).
    """
    gewaehlt = payload.get("mandant_id")
    if gewaehlt is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No mandant selected",
        )
    if str(gewaehlt) != str(mandant_id):
        # Bewusst dieselbe Meldung wie bei fehlender Zugehoerigkeit: Ob der Nutzer den
        # angefragten Mandanten *duerfte* und nur einen anderen gewaehlt hat, ist seine
        # eigene Angelegenheit — die Unterscheidung nach aussen zu tragen bringt
        # nichts und macht die Antwort zur Auskunft.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to mandant denied",
        )

    if current_user.role == UserRole.admin.value:
        return

    result = await session.exec(
        select(MandantUser).where(
            MandantUser.user_id == current_user.id,
            MandantUser.mandant_id == mandant_id,
        )
    )
    if result.first() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to mandant denied",
        )
