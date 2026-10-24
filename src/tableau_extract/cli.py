"""Kommandozeile `tableau-extract`."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="tableau-extract",
        description="Tableau-Kartenansicht -> Tabelle je Landkreis.",
    )


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0
