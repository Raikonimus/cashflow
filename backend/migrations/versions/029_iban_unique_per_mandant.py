"""IBAN und Kontonummer je Mandant eindeutig statt global

Kehrt ADR-008 um; die Entscheidung dazu steht in ADR-018.

Warum
-----
ADR-008 machte die Partner-IBAN **global** eindeutig, ueber alle Mandanten. Der
Import-Lookup filtert dagegen je Mandant — richtig, denn ein Partner gehoert einem
Mandanten. Beides zusammen ergibt einen blinden Fleck: Registriert Mandant A eine IBAN,
findet der Lookup von Mandant B sie nicht (richtig) und die Registrierung fuer B
ueberspringt sie stillschweigend (falsch). B wird ueber diese IBAN **nie** erkannt.
Befund A1-3.

Global eindeutig erzeugt also keine Eindeutigkeit im Sinne von ADR-008, sondern nimmt
dem zweiten Mandanten die IBAN-Erkennung weg.

Was diese Migration tut
-----------------------
``partner_ibans`` und ``partner_accounts`` bekommen eine eigene ``mandant_id`` — aus
dem Partner uebernommen — und ihre Eindeutigkeit wird darauf erweitert:

============================  ==========================================
vorher                        nachher
``UNIQUE (iban)``             ``UNIQUE (mandant_id, iban)``
``UNIQUE (blz, nr)``          ``UNIQUE (mandant_id, blz, nr)``
============================  ==========================================

Die Richtung ist gefahrlos: Global eindeutig ist **strenger** als je Mandant. Was
vorher erlaubt war, bleibt erlaubt; es kann keine Kollision entstehen.

Warum ``mandant_id`` doppelt gefuehrt wird
------------------------------------------
Sie steht schon am Partner. Eine Eindeutigkeit ueber Tabellengrenzen kann eine
Datenbank aber nicht ausdruecken — weder SQLite noch PostgreSQL kennen einen UNIQUE
ueber eine Fremdtabelle. Ohne die Spalte muesste die Regel in der Anwendung stehen, und
genau das ist der Zustand, den Stufe 5 abloest („Struktur statt Disziplin").

Der Preis ist eine Kopie, die auseinanderlaufen kann. Sie kann es nur, wenn ein Partner
den Mandanten wechselt — und das tut kein Pfad im System: ``partners.mandant_id`` wird
beim Anlegen gesetzt und nie geaendert (das Zusammenfuehren laeuft innerhalb eines
Mandanten, ADR-009).

**Diese Migration loescht Zeilen** — 19 in der Entwicklungsdatenbank
--------------------------------------------------------------------
``partner_ibans`` enthaelt Zeilen, deren Partner es nicht mehr gibt. SQLite setzt
Fremdschluessel nur mit ``PRAGMA foreign_keys=ON`` durch, und das ist nicht gesetzt; die
Zeilen sind beim Loeschen von Partnern zurueckgeblieben, bevor
``delete_partner_clean()`` sie mitnahm.

Sie sind auf jedem Pfad unerreichbar: Der Lookup verbindet ueber ``partners`` und
filtert auf den Mandanten, findet also nichts. Unter globaler Eindeutigkeit haben sie
ihre IBAN trotzdem fuer **alle** Mandanten belegt — genau der Schaden aus A1-3, nur ohne
Nutznieser.

Und es gibt keinen Wert zum Nachtragen: Ohne Partner gibt es keinen Mandanten. Die
Spalte liesse sich nur nullbar halten, was das Loch wieder aufmachen wuerde, das die
neue Eindeutigkeit schliessen soll.

Beim Stand vom 2026-09-10 sind es 19 von 2840 Zeilen. Achtzehn davon tragen **zwei
aneinandergeklebte IBANs mit einem Zeilenumbruch** dazwischen
(``AT69…\\nAT11…``) — Parserreste eines Imports vom 2026-04-13, siehe Befund M19. Eine
ist eine wohlgeformte IBAN und hat sie fuer jeden Mandanten blockiert.

``downgrade()`` stellt die globale Eindeutigkeit wieder her und **scheitert**, sobald
zwei Mandanten dieselbe IBAN fuehren. Das ist richtig so: Danach gibt es keinen Weg
zurueck, der nicht Daten verwirft. Die geloeschten Zeilen kommen ohnehin nicht wieder.

Revision ID: 029
Revises: 028
Create Date: 2026-09-10 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Fuegt ``mandant_id`` hinzu und erweitert die Eindeutigkeit darauf."""
    verbindung = op.get_bind()

    # 1. Unerreichbare Zeilen entfernen — siehe Modulkopf. Muss vor dem Nachtragen
    #    laufen, weil es fuer sie keinen Wert gibt und die Spalte NOT NULL wird.
    verwaist = verbindung.execute(
        sa.text(
            "SELECT COUNT(*) FROM partner_ibans pi "
            "LEFT JOIN partners p ON p.id = pi.partner_id WHERE p.id IS NULL"
        )
    ).scalar()
    if verwaist:
        print(f"029: {verwaist} verwaiste Zeilen in partner_ibans werden entfernt")
        verbindung.execute(
            sa.text(
                "DELETE FROM partner_ibans WHERE partner_id NOT IN "
                "(SELECT id FROM partners)"
            )
        )
    verwaist_konten = verbindung.execute(
        sa.text(
            "SELECT COUNT(*) FROM partner_accounts pa "
            "LEFT JOIN partners p ON p.id = pa.partner_id WHERE p.id IS NULL"
        )
    ).scalar()
    if verwaist_konten:
        print(
            f"029: {verwaist_konten} verwaiste Zeilen in partner_accounts "
            f"werden entfernt"
        )
        verbindung.execute(
            sa.text(
                "DELETE FROM partner_accounts WHERE partner_id NOT IN "
                "(SELECT id FROM partners)"
            )
        )

    # 2. Spalte anlegen — zunaechst nullbar, weil SQLite eine NOT-NULL-Spalte nur mit
    #    Vorgabewert anhaengen kann und es hier keinen sinnvollen gibt.
    #
    #    Der Fremdschluessel auf `mandants` steht mit, weil das Modell ihn deklariert
    #    (`Field(foreign_key="mandants.id")`). SQLite setzt ihn ohne
    #    `PRAGMA foreign_keys=ON` nicht durch — siehe Befund M19 —, aber das
    #    Produktionsziel ist PostgreSQL (ADR-015), und dort waere eine Tabelle ohne
    #    den Schluessel eine stille Abweichung zwischen Modell und Schema.
    for tabelle in ("partner_ibans", "partner_accounts"):
        with op.batch_alter_table(tabelle) as stapel:
            stapel.add_column(
                sa.Column(
                    "mandant_id",
                    sa.Uuid(),
                    sa.ForeignKey("mandants.id", name=f"fk_{tabelle}_mandant"),
                    nullable=True,
                )
            )

    # 3. Wert aus dem Partner uebernehmen.
    for tabelle in ("partner_ibans", "partner_accounts"):
        verbindung.execute(
            sa.text(
                f"UPDATE {tabelle} SET mandant_id = "  # noqa: S608 - fester Tabellenname
                f"(SELECT p.mandant_id FROM partners p WHERE p.id = {tabelle}.partner_id)"
            )
        )

    # 4. Pflicht machen, alte Eindeutigkeit ersetzen, Index setzen.
    with op.batch_alter_table("partner_ibans") as stapel:
        stapel.alter_column("mandant_id", nullable=False)
        stapel.drop_constraint("uq_partner_ibans_iban", type_="unique")
        stapel.create_unique_constraint(
            "uq_partner_ibans_mandant_iban", ["mandant_id", "iban"]
        )
        stapel.create_index("ix_partner_ibans_mandant_id", ["mandant_id"])

    with op.batch_alter_table("partner_accounts") as stapel:
        stapel.alter_column("mandant_id", nullable=False)
        stapel.drop_constraint("uq_partner_accounts_blz_account", type_="unique")
        stapel.create_unique_constraint(
            "uq_partner_accounts_mandant_blz_account",
            ["mandant_id", "blz", "account_number"],
        )
        stapel.create_index("ix_partner_accounts_mandant_id", ["mandant_id"])


def downgrade() -> None:
    """Stellt die globale Eindeutigkeit wieder her.

    Scheitert, sobald zwei Mandanten dieselbe IBAN oder dasselbe Konto fuehren — dann
    gibt es keinen Rueckweg ohne Datenverlust, und das soll auffallen und nicht
    stillschweigend eine Zeile verwerfen. Die in ``upgrade()`` entfernten verwaisten
    Zeilen kommen nicht zurueck.
    """
    with op.batch_alter_table("partner_accounts") as stapel:
        stapel.drop_index("ix_partner_accounts_mandant_id")
        stapel.drop_constraint(
            "uq_partner_accounts_mandant_blz_account", type_="unique"
        )
        stapel.create_unique_constraint(
            "uq_partner_accounts_blz_account", ["blz", "account_number"]
        )
        stapel.drop_column("mandant_id")

    with op.batch_alter_table("partner_ibans") as stapel:
        stapel.drop_index("ix_partner_ibans_mandant_id")
        stapel.drop_constraint("uq_partner_ibans_mandant_iban", type_="unique")
        stapel.create_unique_constraint("uq_partner_ibans_iban", ["iban"])
        stapel.drop_column("mandant_id")
