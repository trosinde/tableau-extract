"""Zugangsprüfung (Schritt 0) für eine Tableau-Ansicht.

Führt fünf Tests aus, je Test höchstens eine Anfrage (T5: ein Seitenaufruf im
Browser). Es werden keine Sperren, Anmeldungen oder Zustimmungsdialoge umgangen;
Weiterleitungen werden nicht verfolgt, sondern nur protokolliert.

Aufruf:
    python probe/access_probe.py "<tableau-view-url>" [--env lokal] [--out probe/results]

Ergebnis: <out>/<env>/result.json plus Rohdaten (CSV-Kopf, bootstrapSession-Auszug).
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

PROJECT_UA = "tableau-extract-probe/0.1 (+https://github.com/trosinde/tableau-extract)"
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
REFERER = "https://www.bbsr.bund.de/"
TIMEOUT = 30
PAUSE = 1.0  # höchstens 1 Anfrage pro Sekunde
NETZ_DEFAULT = {"lokal": "Privatanschluss", "cloud": "Rechenzentrum (GitHub Actions)"}


def normalize(url: str) -> str:
    """Entfernt Anzeige-/Einbettungsparameter (`:embed`, `:toolbar`, ...)."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.startswith(":")]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def csv_url(view_url: str) -> str:
    parts = urlsplit(view_url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path + ".csv", parts.query, ""))


def summarize(resp: requests.Response) -> dict:
    body = resp.content
    return {
        "status": resp.status_code,
        "reason": resp.reason,
        "location": resp.headers.get("Location"),
        "content_type": resp.headers.get("Content-Type"),
        "server": resp.headers.get("Server"),
        "bytes": len(body),
        "login_redirect": bool(
            resp.headers.get("Location")
            and re.search(r"signin|login|auth", resp.headers["Location"], re.I)
        ),
        "body_snippet": body[:300].decode("utf-8", errors="replace"),
    }


def http_test(name: str, url: str, headers: dict | None) -> dict:
    t0 = time.monotonic()
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=False)
        result = {"test": name, "url": url, "ok": resp.status_code == 200, **summarize(resp)}
        result["_response"] = resp
    except requests.RequestException as exc:
        result = {"test": name, "url": url, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result["seconds"] = round(time.monotonic() - t0, 2)
    time.sleep(PAUSE)
    return result


def browser_test(url: str, out_dir: Path) -> dict:
    """T5: Ansicht in headless Chromium öffnen, bootstrapSession und Download-Menü prüfen."""
    result: dict = {"test": "T5", "url": url, "ok": False}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        result["error"] = f"playwright fehlt: {exc}"
        return result

    bootstrap: dict = {}
    vizql_calls: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(user_agent=BROWSER_UA, extra_http_headers={"Referer": REFERER})

        def on_response(resp):  # noqa: ANN001
            if "/vizql/" in resp.url:
                vizql_calls.append({"url": resp.url, "status": resp.status})
                if "bootstrapSession" in resp.url and not bootstrap:
                    try:
                        bootstrap["status"] = resp.status
                        bootstrap["text"] = resp.text()
                    except Exception as exc:  # noqa: BLE001
                        bootstrap["error"] = str(exc)

        page.on("response", on_response)
        t0 = time.monotonic()
        try:
            nav = page.goto(url + ("&" if "?" in url else "?") + ":embed=y", timeout=90_000)
            result["page_status"] = nav.status if nav else None
            result["final_url"] = page.url
            # Kartenkacheln laden laufend nach; "networkidle" wird nie erreicht.
            page.wait_for_load_state("load", timeout=90_000)
            deadline = time.monotonic() + 60
            while not bootstrap and time.monotonic() < deadline:
                page.wait_for_timeout(500)
            page.wait_for_timeout(3000)
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"{type(exc).__name__}: {exc}"
        result["seconds"] = round(time.monotonic() - t0, 2)
        result["title"] = page.title()
        result["login_page"] = bool(re.search(r"signin|login", page.url, re.I))
        page.screenshot(path=str(out_dir / "t5_screenshot.png"), full_page=False)

        # Download-Menü öffnen (nur ansehen, nichts herunterladen).
        result["download_menu"] = inspect_download_menu(page, out_dir)
        browser.close()

    result["vizql_calls"] = vizql_calls[:20]
    text = bootstrap.get("text", "")
    result["bootstrap_status"] = bootstrap.get("status")
    result["bootstrap_bytes"] = len(text)
    result["bootstrap_has_dataDictionary"] = "dataDictionary" in text
    result["bootstrap_has_presModel"] = "presModelHolder" in text
    result["bootstrap_summary"] = summarize_bootstrap(text)
    perms = sorted(set(re.findall(r'"([A-Za-z]*(?:[Pp]ermission|[Dd]ownload|[Ee]xport)[A-Za-z]*)"\s*:\s*(true|false)', text)))
    result["bootstrap_flags"] = [f"{k}={v}" for k, v in perms][:60]
    if text:
        (out_dir / "t5_bootstrapSession.txt").write_text(text, encoding="utf-8")
    result["ok"] = result["bootstrap_has_dataDictionary"]
    return result


def summarize_bootstrap(text: str) -> dict:
    """Blätter, Felder und Umfang des Datenwörterbuchs (ohne Werte) aus der Antwort lesen."""
    try:
        parts, i = [], 0
        while i < len(text):
            m = re.match(r"(\d+);", text[i:])
            if not m:
                break
            start = i + len(m.group(0))
            parts.append(json.loads(text[start : start + int(m.group(1))]))
            i = start + int(m.group(1))
        pmm = parts[1]["secondaryInfo"]["presModelMap"]
        segs = pmm["dataDictionary"]["presModelHolder"]["genDataDictionaryPresModel"]["dataSegments"]
        types = {c["dataType"]: len(c["dataValues"]) for s in segs.values() for c in s["dataColumns"]}
        sheets = pmm["vizData"]["presModelHolder"]["genPresModelMapPresModel"]["presModelMap"]
        fields = {
            name: [c["fieldCaption"] for c in
                   v["presModelHolder"]["genVizDataPresModel"]["paneColumnsData"]["vizDataColumns"]
                   if c.get("fieldCaption")]
            for name, v in sheets.items()
        }
        return {"value_counts_by_type": types, "sheets": fields}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def inspect_download_menu(page, out_dir: Path) -> dict:  # noqa: ANN001
    info: dict = {"button_found": False, "options": {}}
    try:
        frame = page
        btn = frame.locator('[data-tb-test-id="viz-viewer-toolbar-button-download"], '
                            '[data-tb-test-id="download-ToolbarButton"]').first
        if btn.count() == 0:
            return info
        info["button_found"] = True
        btn.click(timeout=10_000)
        page.wait_for_timeout(2000)
        labels = {"Image": "Bild", "Data": "Daten", "Crosstab": "Kreuztabelle", "PDF": "PDF",
                  "PowerPoint": "PowerPoint", "Tableau Workbook": "Arbeitsmappe"}
        for en, de in labels.items():
            opt = page.get_by_text(re.compile(rf"^\s*({en}|{de})\s*$")).first
            if opt.count() == 0 or not opt.is_visible():
                info["options"][de] = "nicht angeboten"
                continue
            disabled = opt.evaluate(
                "e => !!e.closest('[aria-disabled=\"true\"],[disabled],.disabled')"
            )
            info["options"][de] = "deaktiviert" if disabled else "aktiv"
        page.screenshot(path=str(out_dir / "t5_download_menu.png"))
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--env", default="lokal", help="Kennung der Umgebung (lokal, cloud)")
    ap.add_argument("--out", default="probe/results")
    ap.add_argument("--skip-browser", action="store_true")
    ap.add_argument("--netz", help="Art des Netzes, z. B. Privatanschluss oder Rechenzentrum")
    args = ap.parse_args()

    view = normalize(args.url)
    parts = urlsplit(view)
    base = f"{parts.scheme}://{parts.netloc}"
    out_dir = Path(args.out) / args.env
    out_dir.mkdir(parents=True, exist_ok=True)

    browser_headers = {"User-Agent": BROWSER_UA, "Referer": REFERER}
    results = []

    results.append(http_test("T1", base + "/robots.txt", {"User-Agent": PROJECT_UA}))
    # T2/T3 gegen die URL wie angegeben (inkl. :embed), denn ohne :embed leitet Tableau
    # grundsätzlich auf die Vizportal-Oberfläche (#/site/...) weiter.
    results.append(http_test("T2", args.url, None))  # Standard-UA von requests
    results.append(http_test("T3", args.url, browser_headers))
    t4 = http_test("T4", csv_url(view), browser_headers)
    if t4.get("ok") and "_response" in t4:
        head = t4["_response"].content.decode("utf-8", errors="replace").splitlines()[:3]
        (out_dir / "t4_head.csv").write_text("\n".join(head) + "\n", encoding="utf-8")
        t4["csv_head"] = head
    results.append(t4)
    if not args.skip_browser:
        results.append(browser_test(view, out_dir))

    for r in results:
        r.pop("_response", None)

    # Bewusst keine IP-Adresse und kein Rechnername: nur die Art des Netzes.
    report = {
        "env": args.env,
        "input_url": args.url,
        "view_url": view,
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "netz": args.netz or NETZ_DEFAULT.get(args.env, "unbekannt"),
        "python": platform.python_version(),
        "results": results,
    }
    (out_dir / "result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    for r in results:
        status = r.get("status", r.get("bootstrap_status", r.get("error", "-")))
        print(f"{r['test']}: ok={r['ok']} status={status} {r.get('location') or ''}")
    print(f"-> {out_dir / 'result.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
