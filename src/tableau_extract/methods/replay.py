"""Offline-Wiederholung: Rohantworten eines früheren Laufs (`raw/`) neu auswerten."""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import InputError
from ..models import RawCapture, RawFile
from ..vizql_parse import VizState
from .csv import parse_view_csv

NAME = "replay"
EXPECTED = "bootstrapSession.txt (Weg B/D) oder view.csv (Weg A)"


def fetch(folder: str | Path, sheet: str) -> RawCapture:
    root = Path(folder)
    if not root.is_dir():
        raise InputError(f"Replay-Ordner {root} nicht gefunden (erwartet: {EXPECTED})")
    files = [RawFile(p.name, p.read_bytes()) for p in sorted(root.iterdir()) if p.is_file()]
    by_name = {f.name: f for f in files}
    start = None
    if "startSession.json" in by_name:
        start = json.loads(by_name["startSession.json"].content)

    if "bootstrapSession.txt" in by_name:
        state = VizState.from_bootstrap(by_name["bootstrapSession.txt"].content.decode("utf-8"))
        if state.locale is None and start:
            state.locale = start.get("locale")
        capture = RawCapture(NAME, files, state.to_view())
        if "filter_index.json" in by_name:
            index = json.loads(by_name["filter_index.json"].content)
            done: set[str] = set()
            commands = sorted(n for n in by_name if n.startswith("command_"))
            for entry in index:
                for name in commands:
                    if name in done:
                        continue
                    state.apply_command_response(json.loads(by_name[name].content))
                    done.add(name)
                    if name == entry["datei"]:
                        break
                capture.filter_views.append((entry["filter"], state.to_view()))
    elif "view.csv" in by_name:
        capture = RawCapture(NAME, files, parse_view_csv(by_name["view.csv"].content, sheet))
    else:
        raise InputError(
            f"Replay-Ordner {root} enthält keine verwertbare Antwort (erwartet: {EXPECTED})"
        )
    if start:
        from .vizql import INFO_KEYS, stamp_from_start

        capture.stamp = stamp_from_start(start)
        capture.info = {k: start[k] for k in INFO_KEYS if k in start}
    capture.info["replay_ordner"] = str(root)
    return capture
