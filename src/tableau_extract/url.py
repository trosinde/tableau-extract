"""Tableau-View-URLs prüfen, normalisieren und in Bestandteile zerlegen."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

from .errors import InputError

_VIEW_RE = re.compile(r"^(?:/t/(?P<site>[^/]+))?/views/(?P<workbook>[^/]+)/(?P<sheet>[^/?#]+?)/?$")
#: Vizportal-Form: https://host/#/site/<site>/views/<wb>/<sheet>
_FRAGMENT_RE = re.compile(
    r"^/(?:site/(?P<site>[^/]+)/)?views/(?P<workbook>[^/]+)/(?P<sheet>[^/?]+)"
)


@dataclass(frozen=True)
class ViewUrl:
    """Bestandteile einer Tableau-View-URL."""

    base: str  # https://host
    site: str | None
    workbook: str
    sheet: str  # Name der Ansicht in der URL (Blatt bzw. Dashboard)
    query: str = ""  # nicht-Anzeige-Parameter (Filter in der URL), normalisiert

    @property
    def path(self) -> str:
        site = f"/t/{quote(self.site)}" if self.site else ""
        return f"{site}/views/{quote(self.workbook)}/{quote(self.sheet)}"

    @property
    def normalized(self) -> str:
        return self.base + self.path + (f"?{self.query}" if self.query else "")

    @property
    def embed_url(self) -> str:
        """URL der eingebetteten Ansicht, wie sie der Browser lädt."""
        params = ":embed=y" + (f"&{self.query}" if self.query else "")
        return f"{self.base}{self.path}?{params}"

    @property
    def csv_url(self) -> str:
        return self.base + self.path + ".csv" + (f"?{self.query}" if self.query else "")

    @property
    def vizql_prefix(self) -> str:
        site = f"/t/{quote(self.site)}" if self.site else ""
        return f"{self.base}/vizql{site}/w/{quote(self.workbook)}/v/{quote(self.sheet)}"

    @property
    def slug(self) -> str:
        parts = [self.site or "default", self.workbook, self.sheet]
        return "-".join(_slugify(p) for p in parts)


def _slugify(text: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", text.replace("ß", "ss"))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_") or "x"


def parse_view_url(url: str) -> ViewUrl:
    """Zerlegt und normalisiert eine Tableau-View-URL.

    Anzeige- und Einbettungsparameter (alle mit `:` beginnend) werden entfernt.
    Wirft `InputError`, wenn die URL nicht auf eine Tableau-Ansicht zeigt.
    """
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise InputError(f"Keine gültige http(s)-URL: {url!r}")

    path = unquote(parts.path)
    match = _VIEW_RE.match(path)
    if match is None and parts.fragment:
        match = _FRAGMENT_RE.match(unquote(parts.fragment))
    if match is None:
        raise InputError(_not_tableau_message(url, parts.netloc))

    workbook, sheet = match.group("workbook"), match.group("sheet")
    if sheet.endswith(".csv"):
        sheet = sheet[: -len(".csv")]
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k[:1] != ":")
    )
    return ViewUrl(
        base=f"{parts.scheme}://{parts.netloc}",
        site=match.group("site"),
        workbook=workbook,
        sheet=sheet,
        query=query,
    )


def _not_tableau_message(url: str, host: str) -> str:
    hint = (
        "Erwartet wird die URL einer Tableau-Ansicht, z. B. "
        "https://<server>/t/<site>/views/<Arbeitsmappe>/<Blatt>."
    )
    if url.lower().endswith((".html", ".htm", "/")) or "tableau" not in host.lower():
        hint += (
            " Zeigt die URL auf eine Seite, die die Karte nur einbettet (z. B. mit "
            "Zustimmungs-Checkbox), bitte die Tableau-URL aus dem `iframe` der Seite "
            "verwenden (src-Attribut mit '/views/')."
        )
    return f"Keine Tableau-View-URL: {url}. {hint}"
