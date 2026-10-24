"""Erzeugt notebooks/schnellstart.ipynb (Quelle der Wahrheit für das Beispiel-Notebook).

Aufruf: uv run python scripts/make_notebook.py
"""

from pathlib import Path

import nbformat as nbf

md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

cells = [
    md("""# tableau-extract – Schnellstart

Dieses Notebook holt die Daten hinter der BBSR-Karte **Wohnungsneubaubedarf 2023–2030** je Landkreis.
Die Werte stammen exakt aus dem Tableau-Datenmodell, nicht aus Farben oder Tooltips.

- Läuft lokal (JupyterLab, VS Code) von einem Privatanschluss oder im Homelab.
- **Nicht in Google Colab** oder anderen Cloud-Notebooks: Der BBSR-Server sperrt Rechenzentren.
- Ohne Netz oder in CI: Umgebungsvariable `TABLEAU_EXTRACT_REPLAY=notebooks/beispiel_raw` setzen;
  dann wird eine gespeicherte Serverantwort ausgewertet."""),
    code(
        '%pip install "git+https://github.com/trosinde/tableau-extract.git@v0.1.0"',
        metadata={"tags": ["skip-ci"]},
    ),
    code("""import pandas as pd

from tableau_extract import extract, list_view

URL = (
    "https://tableau.bbsr.bund.de/t/bbr/views/"
    "Wohnungsneubaubedarfe_insgesamt_2023_bis_2030pa_krs_FINAL/DWohnungsneubaubedare_insgesamt"
)"""),
    md(
        "## 1. Ansicht ansehen\n\nWelche Blätter und Felder hat die Ansicht, und welche Rolle erkennt das Tool?"
    ),
    code("list_view(URL)"),
    md("""## 2. Daten holen

`extract` schreibt nach `out/<slug>/<Zeitstempel>_<Prüfsumme>/` und zeigt eine Zusammenfassung.
Die Gegenprobe vergleicht die Summe der Kreise mit dem Bundeswert (~320 000 Wohnungen pro Jahr)."""),
    code("""r = extract(URL, out="out", check_sum=320_000)
r"""),
    md("""## 3. Zweiter Lauf

Hat sich nichts geändert, lädt das Tool die Daten gar nicht erst (Vorabprüfung des
Veröffentlichungsstands) bzw. schreibt nichts Neues."""),
    code("""r2 = extract(URL, out="out")
assert r2.status == "unverändert"
r2"""),
    md("""## 4. Auswerten mit pandas

Messwerte liegen als `Decimal` vor (exakt, ohne Float-Rundung). Für Rechnungen mit pandas
umwandeln, z. B. mit `pd.to_numeric`."""),
    code("""df = r.df.copy()
je_ew = "p_wohnungsneubaubedarf_2330_we_pa_je_10000ew"
absolut = "p_wohnungsneubaubedarf_2330_we_pa"
df[[je_ew, absolut]] = df[[je_ew, absolut]].apply(pd.to_numeric)
df.nlargest(10, je_ew)[["ags5", "kreis_name", je_ew, absolut]]"""),
    code("""(df.groupby("slk2023")[absolut]
   .agg(["count", "sum"])
   .sort_values("sum", ascending=False))"""),
    md("## 5. Herkunft und Prüfungen"),
    code("""meta = r.meta
print("Weg:", meta["weg"], "| Blatt:", meta["blatt"], "| Gebietsschema:", meta["gebietsschema"])
print("Veröffentlicht:", (meta["veroeffentlichungsstand"] or {}).get("workbookLastPublishedAt"))
print("Vollständig:", meta["pruefungen"]["vollstaendigkeit"]["vollstaendig"])
pd.DataFrame(meta["felder"])[["original", "spalte", "rolle", "im_datenmodell_gerundet"]]"""),
]

nb = nbf.v4.new_notebook(
    cells=cells,
    metadata={
        "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
        "language_info": {"name": "python"},
    },
)
out = Path(__file__).resolve().parents[1] / "notebooks" / "schnellstart.ipynb"
nbf.write(nb, out)
print(out)
