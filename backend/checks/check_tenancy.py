"""Statische Pruefung der Mandantentrennung.

Das System erzwingt die Trennung nicht strukturell: Es gibt keine Row-Level-Security
und keinen Query-Interceptor. Jede Query muss ihren Mandantenbezug selbst mitbringen.
Dieses Skript prueft, ob sie das tut.

Zwei Klassen von Tabellen:

* **direkt gebunden** — die Tabelle hat eine Spalte ``mandant_id``. Eine Query auf sie
  ist sicher, wenn ``mandant_id`` im Statement vorkommt.
* **transitiv gebunden** — der Mandant haengt an einer Elterntabelle (``Service`` ->
  ``Partner`` -> ``mandant_id``). Sicher ist die Query nur, wenn sie entweder auf die
  Elterntabelle joint und dort filtert, oder wenn der Elternschluessel vorher
  validiert wurde. Letzteres kann ein statisches Skript nicht sehen — solche Stellen
  werden als PRUEFEN gemeldet und von Hand gelesen.

Aufruf:  python checks/check_tenancy.py [--strict] [--max-offen N]

``--strict`` setzt den Exit-Code auf 1, wenn

* ein Endpunkt mit zweiter Kennung im Pfad die ``mandant_id`` nicht an den Service
  durchreicht (Pruefung 2) — diese Pruefung ist exakt und steht auf null, oder
* die Zahl der OFFEN-Befunde ueber ``--max-offen`` steigt.

Warum eine Ratsche statt einer Null: Die OFFEN-Klasse aus Pruefung 1 enthaelt
Fehlalarme, die sich statisch nicht ausschliessen lassen — Funktionen, die den
Mandanten nachtraeglich in Python filtern, und bewusst globale Abfragen nach ADR-008.
Alle 43 wurden am 2026-09-09 einzeln gelesen (siehe docs/code-review-befunde.md).
Die Zahl darf nur sinken; steigt sie, ist eine ungepruefte Query dazugekommen.

Der Nachteil ist bekannt: Wird gleichzeitig einer behoben und einer hinzugefuegt,
bleibt die Zahl gleich und die Ratsche schweigt. Dagegen hilft nur, die Zahl beim
Beheben mitzusenken.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
APP = BACKEND / "app"

# Tabellen ohne jeden Mandantenbezug — Pruefung nicht anwendbar.
GLOBAL_TABLES = {"User", "PasswordResetToken", "UserInvitation", "Mandant"}

# Elternschluessel, ueber die der Mandant transitiv haengt.
PARENT_KEYS = {
    "partner_id",
    "account_id",
    "import_run_id",
    "journal_line_id",
    "service_id",
    "group_id",
}


@dataclass(frozen=True)
class Model:
    name: str
    direct: bool  # hat eine eigene mandant_id-Spalte
    parents: tuple[str, ...]  # Fremdschluessel auf potenzielle Elterntabellen


def load_models() -> dict[str, Model]:
    """Liest die Tabellenmodelle aus den models.py der Feature-Module."""
    models: dict[str, Model] = {}
    for path in sorted(APP.glob("*/models.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(
                kw.arg == "table" and getattr(kw.value, "value", False)
                for kw in node.keywords
            ):
                continue
            fields = [
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            ]
            models[node.name] = Model(
                name=node.name,
                direct="mandant_id" in fields,
                parents=tuple(f for f in fields if f in PARENT_KEYS),
            )
    return models


def parents_of(node: ast.AST) -> dict[ast.AST, ast.AST]:
    table: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(node):
        for child in ast.iter_child_nodes(parent):
            table[child] = parent
    return table


def enclosing_statement(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST:
    """Das vollstaendige Statement, in dem eine Query steht — die Kette
    ``select(...).join(...).where(...)`` verteilt sich ueber mehrere Zeilen."""
    current = node
    while current in parents and not isinstance(parents[current], ast.stmt):
        current = parents[current]
    return parents.get(current, current)


def names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def attributes_in(node: ast.AST) -> set[str]:
    return {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def guarded_after_get(call: ast.Call, func: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """Muster ``obj = session.get(Model, id)`` gefolgt von ``obj.mandant_id != mandant_id``.

    Das ist die uebliche und korrekte Form: laden, dann Zugehoerigkeit pruefen.
    """
    stmt = enclosing_statement(call, parents)
    target = None
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        if isinstance(stmt.targets[0], ast.Name):
            target = stmt.targets[0].id
    if target is None:
        return False
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "mandant_id"
            and isinstance(node.value, ast.Name)
            and node.value.id == target
        ):
            return True
    return False


def guarded_by_filter_variable(stmt: ast.AST, func: ast.AST) -> bool:
    """Muster ``base_filter = [Model.mandant_id == mandant_id, ...]`` und spaeter
    ``select(Model).where(*base_filter)`` — der Filter steht in einer Variablen."""
    referenced = {
        n.id
        for call in ast.walk(stmt)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr in {"where", "filter"}
        for arg in call.args
        for n in ast.walk(arg)
        if isinstance(n, ast.Name)
    }
    if not referenced:
        return False
    for node in ast.walk(func):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {t.id for t in targets if isinstance(t, ast.Name)}
            if names & referenced and "mandant_id" in attributes_in(node):
                return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            # base_filter.append(Model.mandant_id == mandant_id)
            if node.func.attr in {"append", "extend"} and isinstance(node.func.value, ast.Name):
                if node.func.value.id in referenced and "mandant_id" in attributes_in(node):
                    return True
    return False


def enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST | None:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current
    return None


@dataclass
class Finding:
    verdict: str  # OK | PRUEFEN | OFFEN | GLOBAL
    file: str
    line: int
    kind: str  # select | get
    models: tuple[str, ...]
    note: str

    def __str__(self) -> str:
        models = ", ".join(self.models) or "?"
        return (
            f"{self.verdict:8s} {self.file}:{self.line:<5d} "
            f"{self.kind:6s} {models:34s} {self.note}"
        )


def classify(
    stmt: ast.AST,
    touched: list[Model],
    kind: str,
    models: dict[str, Model],
    *,
    get_guarded: bool = False,
    filter_guarded: bool = False,
) -> tuple[str, str]:
    attrs = attributes_in(stmt)
    scoped = [m for m in touched if m.name not in GLOBAL_TABLES]
    if not scoped:
        return "GLOBAL", "keine mandantengebundene Tabelle"

    if "mandant_id" in attrs or "mandant_id" in names_in(stmt):
        return "OK", "mandant_id im Statement"
    if get_guarded:
        return "OK", "geladen und danach gegen mandant_id geprueft"
    if filter_guarded:
        return "OK", "Filter mit mandant_id kommt aus einer Variablen"

    direct = [m for m in scoped if m.direct]
    if direct:
        names = ", ".join(m.name for m in direct)
        return "OFFEN", f"{names} hat mandant_id, wird aber nicht gefiltert"

    # nur transitiv gebundene Tabellen: joint die Query auf einen Elternschluessel?
    used_parents = sorted(attrs & PARENT_KEYS)
    if used_parents:
        return "PRUEFEN", f"transitiv ueber {', '.join(used_parents)} — Elternwert validiert?"
    if kind == "get":
        return "PRUEFEN", "session.get() kennt keinen Filter — Zugehoerigkeit danach geprueft?"
    return "OFFEN", "kein Mandanten- und kein Elternfilter"


def scan(path: Path, models: dict[str, Model]) -> list[Finding]:
    source = path.read_text()
    tree = ast.parse(source)
    parents = parents_of(tree)
    rel = str(path.relative_to(BACKEND))
    findings: list[Finding] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        kind = ""
        if isinstance(node.func, ast.Name) and node.func.id == "select":
            kind = "select"
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            # session.get(Model, id) — erstes Argument ist ein Modellname
            if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in models:
                kind = "get"
        if not kind:
            continue

        stmt = enclosing_statement(node, parents)
        touched = [models[n] for n in sorted(names_in(stmt)) if n in models]
        if not touched:
            continue
        func = enclosing_function(node, parents)
        get_guarded = (
            kind == "get" and func is not None and guarded_after_get(node, func, parents)
        )
        filter_guarded = func is not None and guarded_by_filter_variable(stmt, func)
        verdict, note = classify(
            stmt,
            touched,
            kind,
            models,
            get_guarded=get_guarded,
            filter_guarded=filter_guarded,
        )
        findings.append(
            Finding(
                verdict=verdict,
                file=rel,
                line=node.lineno,
                kind=kind,
                models=tuple(m.name for m in touched),
                note=note,
            )
        )
    return findings



# ---------------------------------------------------------------------------
# Pruefung 2: Endpunkte mit einer zweiten Kennung im Pfad
# ---------------------------------------------------------------------------
# `require_mandant_access` prueft ausschliesslich die `mandant_id` aus dem Pfad.
# Steht dort eine zweite Kennung (`account_id`, `partner_id`, ...), muss der Service
# pruefen, dass sie zum selben Mandanten gehoert. Genau diese Pruefung fehlte in
# zwei Import-Endpunkten (Lesezugriff) und in `excluded-identifiers/apply` (Schreibzugriff).

ROUTER_VARS = {"svc", "service", "forecast_svc", "journal_svc", "account_svc"}


def check_endpoints() -> list[str]:
    befunde: list[str] = []
    for path in sorted(APP.glob("*/router.py")):
        source = path.read_text()
        tree = ast.parse(source)
        prefixes = {
            node.targets[0].id: next(
                (kw.value.value for kw in node.value.keywords if kw.arg == "prefix"), ""
            )
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "id", "") == "APIRouter"
            and isinstance(node.targets[0], ast.Name)
        }
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                    continue
                router = getattr(dec.func.value, "id", "")
                if router not in prefixes:
                    continue
                full = prefixes[router] + (dec.args[0].value if dec.args else "")
                params = re.findall(r"\{(\w+)\}", full)
                weitere = [p for p in params if p != "mandant_id" and p.endswith("_id")]
                if "mandant_id" not in params or not weitere:
                    continue
                calls = [
                    c
                    for c in ast.walk(node)
                    if isinstance(c, ast.Call)
                    and isinstance(c.func, ast.Attribute)
                    and getattr(c.func.value, "id", "") in ROUTER_VARS
                ]
                weiter = any(
                    any(getattr(a, "id", "") == "mandant_id" for a in c.args)
                    or any(getattr(k.value, "id", "") == "mandant_id" for k in c.keywords)
                    for c in calls
                )
                if calls and not weiter:
                    befunde.append(
                        f"OFFEN    {dec.func.attr.upper():6s} {full}  "
                        f"({node.name}) — mandant_id erreicht den Service nie"
                    )
    return befunde


# ---------------------------------------------------------------------------
# Pruefung 3: Service-Methoden, die eine Eltern-Kennung nicht validieren
# ---------------------------------------------------------------------------

PARENT_ARGS = {
    "partner_id", "account_id", "service_id", "group_id", "line_id",
    "journal_line_id", "item_id", "run_id", "snapshot_id", "keyword_id",
}


def check_service_methods() -> list[str]:
    befunde: list[str] = []
    for path in sorted(APP.glob("*/service.py")):
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            args = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
            eltern = sorted(args & PARENT_ARGS)
            if "mandant_id" not in args or not eltern:
                continue
            body = ast.get_source_segment(source, node) or ""
            # validierend ist ein Aufruf, der Eltern-Kennung UND mandant_id zusammen bekommt
            validiert = "mandant_id !=" in body or "mandant_id ==" in body
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                namen = {getattr(a, "id", "") for a in call.args} | {
                    getattr(k.value, "id", "") for k in call.keywords
                }
                if "mandant_id" in namen and namen & set(eltern):
                    validiert = True
                    break
            if not validiert:
                rel = str(path.relative_to(BACKEND))
                befunde.append(
                    f"PRUEFEN  {rel}:{node.lineno:<5d} {node.name}  "
                    f"({', '.join(eltern)}) — Eltern-Kennung nicht erkennbar validiert"
                )
    return befunde


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict", action="store_true", help="Exit-Code 1 bei Ueberschreitung"
    )
    parser.add_argument(
        "--max-offen",
        type=int,
        default=0,
        help="erlaubte Zahl triagierter OFFEN-Befunde (Stand 2026-09-09: 43)",
    )
    parser.add_argument("--only", help="nur Befunde dieser Klasse zeigen")
    args = parser.parse_args()

    models = load_models()
    findings: list[Finding] = []
    for path in sorted(APP.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        findings.extend(scan(path, models))

    order = {"OFFEN": 0, "PRUEFEN": 1, "OK": 2, "GLOBAL": 3}
    findings.sort(key=lambda f: (order[f.verdict], f.file, f.line))

    shown = [f for f in findings if not args.only or f.verdict == args.only]
    for finding in shown:
        if finding.verdict in {"OFFEN", "PRUEFEN"} or args.only:
            print(finding)

    counts = {v: sum(1 for f in findings if f.verdict == v) for v in order}
    print()
    print(
        f"{len(findings)} Queries geprueft — "
        + ", ".join(f"{v}: {counts[v]}" for v in order)
    )

    endpunkte = check_endpoints()
    methoden = check_service_methods()
    if not args.only:
        print()
        print(f"Endpunkte mit ungepruefter zweiter Kennung: {len(endpunkte)}")
        for zeile in endpunkte:
            print("  " + zeile)
        print()
        print(f"Service-Methoden ohne erkennbare Elternpruefung: {len(methoden)}")
        for zeile in methoden:
            print("  " + zeile)

    if not args.strict:
        return 0

    fehler = []
    if endpunkte:
        fehler.append(f"{len(endpunkte)} Endpunkt(e) reichen die mandant_id nicht durch")
    if counts["OFFEN"] > args.max_offen:
        fehler.append(
            f"{counts['OFFEN']} OFFEN-Befunde, erlaubt sind {args.max_offen} — "
            "eine ungepruefte Query ist dazugekommen"
        )
    for zeile in fehler:
        print(f"FEHLER: {zeile}")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
