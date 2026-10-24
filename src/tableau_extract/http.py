"""Höflicher HTTP-Client: eigener User-Agent, Drossel, Backoff, Versuchsprotokoll."""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from typing import Any, NoReturn
from urllib.parse import urljoin, urlsplit

import requests

from . import __version__
from .models import Attempt

DEFAULT_USER_AGENT = f"tableau-extract/{__version__} (+https://github.com/trosinde/tableau-extract)"
RETRY_STATUS = {429, 500, 502, 503, 504}
BACKOFF = (2.0, 4.0, 8.0)
_LOGIN_RE = re.compile(r"signin|login|/auth", re.IGNORECASE)


class HttpError(Exception):
    """Endgültig gescheiterte Anfrage; `attempt` beschreibt den Grund."""

    def __init__(self, attempt: Attempt) -> None:
        super().__init__(attempt.message)
        self.attempt = attempt


class PoliteClient:
    """Eine `requests.Session` mit Drossel je Host, Retry/Backoff und Protokoll.

    - höchstens eine Anfrage pro `min_interval` Sekunden an denselben Host
    - Retry bei 429/5xx/Timeout mit Backoff 2/4/8 s (`Retry-After` hat Vorrang)
    - kein Retry bei 4xx (außer 429)
    - Weiterleitungen auf Anmeldeseiten gelten als „Anmeldung erforderlich“
    """

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        min_interval: float | None = None,
        timeout: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            user_agent or os.environ.get("TABLEAU_EXTRACT_USER_AGENT") or DEFAULT_USER_AGENT
        )
        env_interval = os.environ.get("TABLEAU_EXTRACT_MIN_INTERVAL")
        self.min_interval = max(
            1.0,
            min_interval
            if min_interval is not None
            else float(env_interval)
            if env_interval
            else 1.0,
        )
        self.timeout = timeout
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}
        self.log: list[Attempt] = []

    def _throttle(self, url: str) -> None:
        host = urlsplit(url).netloc
        last = self._last.get(host)
        if last is not None:
            wait = self.min_interval - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last[host] = self._clock()

    def request(self, method: str, url: str, *, label: str, **kwargs: Any) -> requests.Response:
        """Führt eine Anfrage aus; wirft `HttpError` bei endgültigem Fehlschlag.

        Weiterleitungen werden selbst verfolgt (höchstens 5), damit Anmeldeseiten
        erkannt werden und jede Anfrage gedrosselt bleibt.
        """
        kwargs.setdefault("timeout", self.timeout)
        kwargs["allow_redirects"] = False
        retries = redirects = 0
        while True:
            self._throttle(url)
            try:
                resp = self.session.request(method, url, **kwargs)
            except (requests.Timeout, requests.ConnectionError) as exc:
                if retries < len(BACKOFF):
                    self._sleep(BACKOFF[retries])
                    retries += 1
                    continue
                self._fail(label, url, None, f"{type(exc).__name__}: {exc}")

            if resp.is_redirect:
                location = urljoin(url, resp.headers.get("Location", ""))
                if _LOGIN_RE.search(location):
                    self._fail(label, url, resp.status_code, f"Anmeldung erforderlich ({location})")
                if redirects >= 5:
                    self._fail(label, url, resp.status_code, "zu viele Weiterleitungen")
                redirects += 1
                if resp.status_code in (301, 302, 303):
                    method = "GET"
                    kwargs.pop("data", None)
                    kwargs.pop("json", None)
                url = location
                continue
            if resp.status_code in RETRY_STATUS and retries < len(BACKOFF):
                self._sleep(_retry_after(resp) or BACKOFF[retries])
                retries += 1
                continue
            if resp.status_code >= 400:
                self._fail(label, url, resp.status_code, _describe(resp))
            self.log.append(Attempt(label, True, url, resp.status_code, "ok"))
            return resp

    def get(self, url: str, *, label: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, label=label, **kwargs)

    def post(self, url: str, *, label: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", url, label=label, **kwargs)

    def _fail(self, label: str, url: str, status: int | None, message: str) -> NoReturn:
        attempt = Attempt(label, False, url, status, message)
        self.log.append(attempt)
        raise HttpError(attempt)


def _retry_after(resp: requests.Response) -> float | None:
    value = resp.headers.get("Retry-After", "")
    return float(value) if value.isdigit() else None


def _describe(resp: requests.Response) -> str:
    """Kurze, aussagekräftige Fehlermeldung aus Status, Server und Body."""
    server = resp.headers.get("Server", "")
    parts = [f"HTTP {resp.status_code}"]
    if server:
        parts.append(server)
    body = resp.text[:2000]
    m = re.search(r'"type"\s*:\s*"([^"]+)"', body)
    if m:
        parts.append(m.group(1))
    elif "<TITLE>" in body.upper():
        t = re.search(r"<title>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
        if t:
            parts.append(t.group(1).strip())
    return ", ".join(parts)
