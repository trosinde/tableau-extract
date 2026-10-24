"""Kommandozeile `tableau-extract`."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from . import __version__
from .acquire import METHODS
from .api import DEFAULT_FULL_CHECK_DAYS, extract, list_view
from .errors import ExtractError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tableau-extract",
        description=(
            "Liest die Daten hinter einer Tableau-Kartenansicht exakt aus und legt sie "
            "je Landkreis als CSV/Parquet mit meta.json ab."
        ),
        epilog=(
            "Exit-Codes: 0 neu oder unverändert, 1 Eingabe-/unerwarteter Fehler, "
            "2 Quelle gesperrt, 3 Kreise nicht eindeutig zuordenbar. "
            "Umgebungsvariablen: TABLEAU_EXTRACT_OUT, TABLEAU_EXTRACT_REPLAY, "
            "TABLEAU_EXTRACT_USER_AGENT, TABLEAU_EXTRACT_MIN_INTERVAL."
        ),
    )
    p.add_argument("url", help="URL der Tableau-Ansicht (…/views/<Arbeitsmappe>/<Blatt>)")
    p.add_argument(
        "--list", action="store_true", help="Blätter, Felder, Filter anzeigen; nichts schreiben"
    )
    p.add_argument("--sheet", help="Blatt erzwingen (sonst automatisch)")
    p.add_argument("--all-filters", action="store_true", help="je Filterwert einen Abzug ziehen")
    p.add_argument("--method", choices=METHODS, help="nur diesen Weg versuchen")
    p.add_argument("--out", help="Basisverzeichnis der Ausgabe (Standard: out/)")
    p.add_argument("--replay", help="gespeicherte Rohantworten (raw/) neu auswerten, ohne Abruf")
    p.add_argument(
        "--force",
        action="store_true",
        help="voll laden, auch wenn der Veröffentlichungsstand unverändert ist",
    )
    p.add_argument(
        "--full-check-days",
        type=float,
        default=DEFAULT_FULL_CHECK_DAYS,
        help="spätestens nach so vielen Tagen voll laden (Standard: %(default)g)",
    )
    p.add_argument("--check-sum", type=float, help="Sollwert für die Summe eines Messfelds")
    p.add_argument(
        "--check-field", help="Spalte für --check-sum (Standard: erstes absolutes Messfeld)"
    )
    p.add_argument("--gebietsstand", type=int, help="Jahr der Kreis-Referenzliste erzwingen")
    p.add_argument("--referenz", help="eigene Kreis-Referenzliste (CSV ags5;name;typ)")
    p.add_argument("--timeout", type=float, default=60.0, help="Zeitlimit je Anfrage in Sekunden")
    p.add_argument("--quiet", action="store_true", help="nur Fehler ausgeben")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _print(quiet: bool, *lines: Any) -> None:
    if not quiet:
        for line in lines:
            print(line)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.list:
            listing = list_view(
                args.url, method=args.method, replay=args.replay, timeout=args.timeout
            )
            print(repr(listing))
            return 0
        result = extract(
            args.url,
            out=args.out,
            sheet=args.sheet,
            all_filters=args.all_filters,
            method=args.method,
            replay=args.replay,
            force=args.force,
            full_check_days=args.full_check_days,
            check_sum=args.check_sum,
            check_field=args.check_field,
            gebietsstand=args.gebietsstand,
            referenz=args.referenz,
            timeout=args.timeout,
        )
    except ExtractError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        for f in exc.report.get("fehlversuche", []):
            status = f" HTTP {f['status']}" if f.get("status") else ""
            print(f"  Weg {f['method']}:{status} {f['message']}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        return 130

    for a in result.meta.get("versuche", []) if result.status == "neu" else []:
        state = "ok" if a["ok"] else "gescheitert"
        status = f", HTTP {a['status']}" if a.get("status") and not a["ok"] else ""
        _print(
            args.quiet,
            f"Weg {a['method']}: {state}{status}" + ("" if a["ok"] else f" – {a['message']}"),
        )
    for m in result.messages:
        _print(args.quiet, m)
    if result.status == "neu":
        voll = result.meta.get("pruefungen", {}).get("vollstaendigkeit", {})
        if isinstance(voll, dict) and voll:
            _print(
                args.quiet,
                f"Vollständigkeit: {voll['gefunden']}/{voll['erwartet']} Kreise "
                f"(Gebietsstand {voll['gebietsstand']})",
            )
        _print(args.quiet, f"neu: {result.path} ({len(result.df)} Zeilen)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
