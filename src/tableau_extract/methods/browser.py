"""Wege C und D im Browser (Playwright): Download-Menü prüfen, bootstrapSession mitschneiden.

Beide Wege teilen sich einen Seitenaufruf:
- C prüft, ob das Download-Menü „Daten“ oder „Kreuztabelle“ anbietet. Ein Download
  über diesen Weg ist noch nicht umgesetzt (design.md, Non-Goals); er wird nur protokolliert.
- D nimmt die beim Laden mitgeschnittene `startSession`- und `bootstrapSession`-Antwort
  und wertet sie mit demselben Parser wie Weg B aus.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from ..errors import FormatError
from ..models import Attempt, MethodFailed, RawCapture
from ..url import ViewUrl
from .vizql import capture_from_bootstrap

NAME_C = "download"
NAME_D = "network"
_LOGIN = re.compile(r"signin|login", re.IGNORECASE)
_MENU_LABELS = {"Daten": ("Data", "Daten"), "Kreuztabelle": ("Crosstab", "Kreuztabelle")}


class BrowserSession:
    """Lädt die Ansicht einmal in headless Chromium und hält die Ergebnisse fest."""

    def __init__(self, view: ViewUrl, user_agent: str, timeout: float = 90.0) -> None:
        self.view = view
        self.user_agent = user_agent
        self.timeout = timeout
        self.loaded = False
        self.failure: Attempt | None = None
        self.start: dict[str, Any] | None = None
        self.start_raw = b""
        self.bootstrap: bytes | None = None
        self.menu: dict[str, str] = {}

    def load(self) -> None:
        if self.loaded:
            return
        self.loaded = True
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.failure = Attempt(
                NAME_D,
                False,
                None,
                None,
                "Playwright nicht installiert (pip install 'tableau-extract[browser]' "
                "und 'playwright install chromium')",
            )
            return
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(user_agent=self.user_agent)
                page.on("response", self._on_response)
                resp = page.goto(self.view.embed_url, timeout=self.timeout * 1000)
                status = resp.status if resp else None
                if status is not None and status >= 400:
                    self.failure = Attempt(
                        NAME_D,
                        False,
                        self.view.embed_url,
                        status,
                        f"HTTP {status} beim Laden der Ansicht",
                    )
                elif _LOGIN.search(page.url):
                    self.failure = Attempt(
                        NAME_D, False, page.url, status, "Anmeldung erforderlich"
                    )
                else:
                    deadline = time.monotonic() + self.timeout
                    while self.bootstrap is None and time.monotonic() < deadline:
                        page.wait_for_timeout(500)
                    self.menu = _inspect_download_menu(page)
                browser.close()
        except Exception as exc:
            self.failure = Attempt(
                NAME_D, False, self.view.embed_url, None, f"Browser: {type(exc).__name__}: {exc}"
            )

    def _on_response(self, resp: Any) -> None:
        url = resp.url
        try:
            if "/startSession/" in url and self.start is None and resp.status == 200:
                self.start_raw = resp.body()
                self.start = json.loads(self.start_raw)
            elif "/bootstrapSession/" in url and self.bootstrap is None and resp.status == 200:
                self.bootstrap = resp.body()
        except Exception:
            pass


def _inspect_download_menu(page: Any) -> dict[str, str]:
    """Öffnet das Download-Menü der Werkzeugleiste und liest die Einträge (lädt nichts)."""
    result: dict[str, str] = {}
    btn = page.locator(
        '[data-tb-test-id="viz-viewer-toolbar-button-download"], '
        '[data-tb-test-id="download-ToolbarButton"]'
    ).first
    if btn.count() == 0:
        return {"_menü": "kein Download-Knopf"}
    try:
        btn.click(timeout=10_000)
        page.wait_for_timeout(1500)
        for label, names in _MENU_LABELS.items():
            pattern = re.compile(rf"^\s*({'|'.join(names)})\s*$")
            opt = page.get_by_text(pattern).first
            if opt.count() == 0 or not opt.is_visible():
                result[label] = "nicht angeboten"
                continue
            disabled = opt.evaluate("e => !!e.closest('[aria-disabled=\"true\"],[disabled]')")
            result[label] = "deaktiviert" if disabled else "angeboten"
        page.keyboard.press("Escape")
    except Exception as exc:
        result["_menü"] = f"nicht lesbar: {type(exc).__name__}"
    return result


def fetch_download(session: BrowserSession) -> RawCapture:
    """Weg C: nur prüfen und protokollieren."""
    session.load()
    if session.failure is not None:
        raise MethodFailed(
            Attempt(
                NAME_C, False, session.failure.url, session.failure.status, session.failure.message
            )
        )
    offered = [k for k, v in session.menu.items() if v == "angeboten"]
    menu = ", ".join(f"{k}: {v}" for k, v in session.menu.items()) or "nicht geprüft"
    if not offered:
        raise MethodFailed(
            Attempt(NAME_C, False, session.view.embed_url, None, f"Download-Menü: {menu}")
        )
    raise MethodFailed(
        Attempt(
            NAME_C,
            False,
            session.view.embed_url,
            None,
            f"Download-Menü: {menu}; Download über diesen Weg ist noch nicht umgesetzt",
        )
    )


def fetch_network(session: BrowserSession, *, all_filters: bool = False) -> RawCapture:
    """Weg D: mitgeschnittene bootstrapSession auswerten."""
    session.load()
    if session.failure is not None:
        raise MethodFailed(session.failure)
    if session.bootstrap is None:
        raise MethodFailed(
            Attempt(
                NAME_D,
                False,
                session.view.embed_url,
                None,
                "keine bootstrapSession-Antwort mitgeschnitten",
            )
        )
    if all_filters:
        raise MethodFailed(
            Attempt(
                NAME_D,
                False,
                None,
                None,
                "--all-filters wird über den Browser-Weg nicht unterstützt",
            )
        )
    try:
        return capture_from_bootstrap(
            NAME_D, session.bootstrap, start=session.start, start_raw=session.start_raw
        )
    except FormatError as exc:
        raise MethodFailed(Attempt(NAME_D, False, None, None, str(exc))) from exc
