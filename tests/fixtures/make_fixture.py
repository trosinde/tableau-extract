"""Erzeugt kleine Test-Fixtures aus einer echten bootstrapSession-Antwort.

Gekürzt wird nur, was für die Daten unerheblich ist:
- Geometrien (`spatial`-Werte) werden durch einen Platzhalter ersetzt,
- die Render-Szene (`.../visual/scene`) der Kartenzone wird entfernt.
Alle anderen Teile, insbesondere Datenwörterbuch und `paneColumnsData`, bleiben
unverändert. Die Längenpräfixe werden neu berechnet.

Aufruf:
    python tests/fixtures/make_fixture.py <bootstrapSession.txt> <ziel.txt>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PLACEHOLDER = "GEOGRAPHY('POINT(0 0)')"


def split_segments(text: str) -> list[Any]:
    parts, i = [], 0
    while i < len(text):
        m = re.match(r"(\d+);", text[i:])
        if m is None:
            raise ValueError(f"kein Längenpräfix an Position {i}")
        start = i + len(m.group(0))
        end = start + int(m.group(1))
        parts.append(json.loads(text[start:end]))
        i = end
    return parts


def join_segments(parts: list[Any]) -> str:
    out = []
    for p in parts:
        body = json.dumps(p, ensure_ascii=False, separators=(",", ":"))
        out.append(f"{len(body)};{body}")
    return "".join(out)


def shrink(parts: list[Any]) -> list[Any]:
    zones = (
        parts[0]
        .get("worldUpdate", {})
        .get("applicationPresModel", {})
        .get("workbookPresModel", {})
        .get("dashboardPresModel", {})
        .get("zones", {})
    )
    for zone in zones.values():
        visual = (zone or {}).get("presModelHolder", {}).get("visual")
        if isinstance(visual, dict):
            visual.pop("scene", None)
    if len(parts) > 1:
        segs = parts[1]["secondaryInfo"]["presModelMap"]["dataDictionary"]["presModelHolder"][
            "genDataDictionaryPresModel"
        ]["dataSegments"]
        for seg in segs.values():
            for col in seg["dataColumns"]:
                if col["dataType"] == "spatial":
                    col["dataValues"] = [PLACEHOLDER] * len(col["dataValues"])
    return parts


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    parts = shrink(split_segments(src.read_text(encoding="utf-8")))
    dst.write_text(join_segments(parts), encoding="utf-8")
    print(f"{dst}: {dst.stat().st_size} Bytes")


if __name__ == "__main__":
    main()
