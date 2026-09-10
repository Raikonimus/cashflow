"""Fixtures fuer Stufe 4 — nur, was ``tests/conftest.py`` nicht schon hergibt.

Hier steht bewusst **keine** eigene Kopie von ``setup_db``, ``db_session`` oder
``client``. Sechs Testverzeichnisse bringen je eine mit, und das Zusammenlegen dieser
Kopien ist ein offener Punkt aus Stufe 0. Eine siebte anzulegen waere genau der
Zwilling, nach dem Frage 1 des Merge-Checks fragt (``docs/code-review-konzept.md``
§10). Dieses Verzeichnis nimmt deshalb die kanonischen Fixtures aus ``tests/conftest.py``
und laeuft auf deren Engine.
"""

from __future__ import annotations

import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.conftest import ZweiMandanten
from tests.tenancy.sonden import Pruefstand, Seite, erweitere_welt


@pytest_asyncio.fixture
async def pruefstand(
    db_session: AsyncSession, zwei_mandanten: ZweiMandanten
) -> Pruefstand:
    """Die Pruefumgebung aus Stufe 0, erweitert um die acht fehlenden Satzarten.

    Beide Seiten bekommen dieselbe Erweiterung. Das ist die Voraussetzung dafuer, dass
    ein Angriff auf ein fremdes Objekt ueberhaupt etwas belegt: Fehlt der Satz im
    fremden Mandanten, antwortet der Aufruf mit 404, ohne dass eine Pruefung
    stattgefunden haette.

    ``urheber`` ist der Admin, weil ``created_by`` einen existierenden Nutzer braucht
    und die Spalte nichts ueber Zugriffsrechte sagt — die stehen ausschliesslich in
    ``mandant_users``.
    """
    zusatz_a = await erweitere_welt(
        db_session, zwei_mandanten.a, urheber=zwei_mandanten.admin
    )
    zusatz_b = await erweitere_welt(
        db_session, zwei_mandanten.b, urheber=zwei_mandanten.admin
    )
    return Pruefstand(
        a=Seite(welt=zwei_mandanten.a, zusatz=zusatz_a, nutzer=zwei_mandanten.nutzer_a),
        b=Seite(welt=zwei_mandanten.b, zusatz=zusatz_b, nutzer=zwei_mandanten.nutzer_b),
        nutzer_beide=zwei_mandanten.nutzer_beide,
        nutzer_ohne=zwei_mandanten.nutzer_ohne,
        mandant_admin_a=zwei_mandanten.mandant_admin_a,
        admin=zwei_mandanten.admin,
        umgebung=zwei_mandanten,
    )
