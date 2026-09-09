"""Erkennung von Zeichensatz und Trennzeichen einer CSV-Datei.

Beide Funktionen lagen wortgleich in `imports/service.py` und `tenants/router.py`
und in einer Variante in `scripts/backfill_booking_references.py`. Am Dateneingang
ist das die unangenehmste Stelle fuer eine Kopie: Erkennt die Heuristik den
Zeichensatz einer Bank falsch, korrigiert man eine Fassung und die anderen behalten
den Fehler.
"""

import csv


def detect_encoding(raw: bytes) -> str:
    """Erkennt den Zeichensatz ueber die BOM, sonst durch Probe-Dekodieren."""
    if raw[:2] in {b"\xff\xfe", b"\xfe\xff"}:
        return "utf-16"
    if raw[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def detect_delimiter(text: str, fallback: str) -> str:
    """Erkennt das Trennzeichen via csv.Sniffer (quote-bewusst).

    Faellt auf `fallback` zurueck, wenn der Sniffer scheitert.
    """
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=";,\t|")
        return dialect.delimiter
    except csv.Error:
        return fallback
