"""Die Mandantenbedingung fuer Buchungszeilen — als Ausdruck, nicht als Merkregel.

Warum dieses Modul existiert
----------------------------
``JournalLine`` traegt **keine** eigene ``mandant_id``. Der Mandant haengt am Konto:
``journal_lines.account_id -> accounts.mandant_id``. Jede Abfrage auf Buchungszeilen
muss diesen Umweg selbst gehen, und genau dort ist Befund A1-4 entstanden.

Vier Funktionen in ``app/partners/service.py`` gingen ihn zu spaet: Sie luden die
Zeilen **ohne** Filter und siebten danach in Python.

.. code-block:: python

    lines = <exakte Uebereinstimmung>       # ueber alle Mandanten
    if not lines:
        lines = <ILIKE-Teiltreffer>         # Fallback
    lines = [ln for ln in lines if ...]     # Mandantenfilter, zehn Zeilen spaeter

Der Befund stufte das als „korrekt, aber fragil" ein. Beim Umsetzen von Stufe 5 zeigte
sich, dass es schon heute falsche Ergebnisse liefert: Die Entscheidung ``if not lines``
faellt vor dem Filter. Zeilen eines **fremden** Mandanten lassen den exakten Anlauf als
erfolgreich gelten, der Fallback entfaellt, und der Filter raeumt danach alles weg — der
eigene Mandant sieht eine leere Vorschau. Siehe Befund M18 und
``tests/partners/test_fallback_und_mandant.py``.

Mit der Bedingung **in** der Query kann das nicht passieren: Was nicht zum Mandanten
gehoert, kommt nicht zurueck, und ``if not lines`` entscheidet ueber die richtige Menge.

Warum ein Ausdruck und keine Funktion, die Zeilen liefert
---------------------------------------------------------
``buchungen_des_mandanten()`` gibt eine **Bedingung** zurueck, die in jedes
``.where(...)`` passt — nicht eine Liste von Zeilen. Das ist Absicht: Die Aufrufer
haben ganz verschiedene Abfragen (Vorschau, Umhaengen, Zusammenfuehren), und eine
Funktion, die fertige Zeilen liefert, koennte deren Bedingungen nicht abbilden. Eine
Bedingung kombiniert sich mit allem.

Nebenwirkung auf die Datenmenge: Die Fallback-Suche ``partner_iban_raw ILIKE '%…%'``
lief bisher ueber die Buchungen **aller** Mandanten, bevor gesiebt wurde. Jetzt
begrenzt die Datenbank sie.

Verhaeltnis zu ``check_tenancy.py``
-----------------------------------
Die statische Pruefung meldete diese acht Abfragen als ``OFFEN`` — „kein Mandanten- und
kein Elternfilter". Mit dem Aufruf steht ``mandant_id`` im Statement, und sie zaehlt sie
als ``OK``. Die Ratsche ``--max-offen`` sinkt entsprechend mit; sonst schweigt sie beim
naechsten Neuzugang.

Was hier **nicht** steht
------------------------
``app/journal/service.py``, ``app/forecast/service.py`` und ``app/testing/service.py``
filtern an fuenf Stellen ebenfalls ueber das Konto, aber richtig — in der Query, mit
einer vorher geladenen Kennungsliste (``col(JournalLine.account_id).in_(account_ids)``).
Sie sind nicht fehlerhaft, nur ausfuehrlicher, und ihre Umstellung auf diesen Helfer ist
eine eigene Aufraeumarbeit. Sie steht hier als offener Punkt, damit die naechste
Erweiterung nicht wieder eine sechste Kopie baut.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select

from app.imports.models import JournalLine
from app.tenants.models import Account


def buchungen_des_mandanten(mandant_id: UUID) -> ColumnElement[bool]:
    """Bedingung: Diese Buchungszeile gehoert zu einem Konto von ``mandant_id``.

    Einzusetzen in jedes ``select(JournalLine).where(...)``, gleichrangig neben den
    fachlichen Bedingungen:

    .. code-block:: python

        select(JournalLine).where(
            JournalLine.partner_iban_raw == iban,
            buchungen_des_mandanten(mandant_id),
        )

    Die Einschraenkung laeuft als Unterabfrage auf ``accounts``, nicht als vorher
    geladene Kennungsliste. Das kostet keinen zweiten Aufruf und traegt sich auch dann,
    wenn ein Mandant viele Konten hat.
    """
    return col(JournalLine.account_id).in_(
        select(col(Account.id)).where(Account.mandant_id == mandant_id)
    )
