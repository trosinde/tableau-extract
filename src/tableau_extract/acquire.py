"""Orchestrierung der Extraktionswege: Vorabprüfung, Reihenfolge A→B→C→D, Protokoll."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .errors import BlockedError, InputError
from .http import PoliteClient
from .models import Attempt, MethodFailed, RawCapture
from .url import ViewUrl

METHODS = ("csv", "vizql", "download", "network")


@dataclass
class Acquisition:
    """Ergebnis des Abrufs: entweder Daten (`capture`) oder „unverändert“ laut Vorabprüfung."""

    capture: RawCapture | None
    attempts: list[Attempt] = field(default_factory=list)
    stamp: dict[str, Any] | None = None
    unchanged_by_stamp: bool = False


def acquire(
    view: ViewUrl,
    *,
    client: PoliteClient | None = None,
    method: str | None = None,
    all_filters: bool = False,
    replay: str | None = None,
    skip_if_stamp: Callable[[dict[str, Any]], bool] | None = None,
    timeout: float = 60.0,
) -> Acquisition:
    """Holt die Rohdaten der Ansicht.

    `skip_if_stamp(stamp)` entscheidet nach der kleinen startSession-Anfrage, ob der
    Vollabruf entfallen kann (Vorabprüfung). Ohne Funktion wird immer voll geladen.
    """
    if replay:
        from .methods import replay as replay_method

        cap = replay_method.fetch(replay, view.sheet)
        return Acquisition(cap, [Attempt("replay", True, replay, None, "ok")], cap.stamp)

    if method is not None and method not in METHODS:
        raise InputError(f"Unbekannter Weg {method!r}; erlaubt: {', '.join(METHODS)}")
    order = [method] if method else list(METHODS)
    client = client or PoliteClient(timeout=timeout)

    from .methods import browser, csv, vizql

    session = vizql.VizqlSession(view, client)
    attempts: list[Attempt] = []
    stamp = None

    if skip_if_stamp is not None and "vizql" in order:
        try:
            session.open()
            stamp = session.stamp
            if stamp is not None and skip_if_stamp(stamp):
                attempts.append(
                    Attempt(
                        "vorabpruefung",
                        True,
                        view.normalized,
                        200,
                        "Veröffentlichungsstand unverändert",
                    )
                )
                return Acquisition(None, attempts, stamp, unchanged_by_stamp=True)
        except MethodFailed:
            pass  # wird beim Weg B protokolliert

    bsession = browser.BrowserSession(view, str(client.session.headers["User-Agent"]), timeout)
    runners: dict[str, Callable[[], RawCapture]] = {
        "csv": lambda: csv.fetch(view, client),
        "vizql": lambda: vizql.fetch(session, all_filters=all_filters),
        "download": lambda: browser.fetch_download(bsession),
        "network": lambda: browser.fetch_network(bsession, all_filters=all_filters),
    }
    for name in order:
        try:
            cap = runners[name]()
        except MethodFailed as exc:
            a = exc.attempt
            attempts.append(Attempt(name, False, a.url, a.status, a.message))
            continue
        attempts.append(Attempt(name, True, view.normalized, 200, "ok"))
        return Acquisition(cap, attempts, cap.stamp or stamp)

    report = "; ".join(
        f"{a.method}: {a.message}" + (f" (HTTP {a.status})" if a.status else "") for a in attempts
    )
    raise BlockedError(
        f"Kein Weg lieferte Daten. {report}",
        {"fehlversuche": [a.as_dict() for a in attempts]},
    )
