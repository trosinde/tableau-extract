"""Führt ein Notebook aus; Zellen mit dem Tag `skip-ci` werden übersprungen.

Aufruf: python scripts/run_notebook.py <notebook.ipynb> <arbeitsordner> [<ausgabe.ipynb>]
Ein Fehler in einer Zelle beendet das Skript mit Exit-Code 1.
"""

import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError


def main() -> int:
    src, workdir = Path(sys.argv[1]), Path(sys.argv[2])
    dst = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    nb = nbformat.read(src, as_version=4)
    nb.cells = [c for c in nb.cells if "skip-ci" not in c.get("metadata", {}).get("tags", [])]
    workdir.mkdir(parents=True, exist_ok=True)
    client = NotebookClient(
        nb, timeout=300, kernel_name="python3", resources={"metadata": {"path": str(workdir)}}
    )
    try:
        client.execute()
    except CellExecutionError as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        if dst is not None:
            nbformat.write(nb, dst)
    print(f"{src}: {len(nb.cells)} Zellen ausgeführt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
