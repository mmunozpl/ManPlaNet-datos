"""Estado de enriquecimiento de los CVE en el NVD, por año de publicación.

Recorre la API 2.0 del NVD y guarda una fila por CVE publicado entre 2023 y
la fecha de corte: identificador, fecha de publicación, estado de
enriquecimiento (`vulnStatus`) y si consta en el catálogo de vulnerabilidades
explotadas conocidas de CISA. Después agrega por año y por mes.

Escribe junto a sí mismo: `cve-estados.csv.gz`, `por-anio.csv`, `por-mes.csv`,
`resumen.json` e `INSTANTANEA.md`. Sin clave, la API admite cinco peticiones
cada treinta segundos; el recorrido completo tarda unos veinte minutos.
"""
import collections
import csv
import datetime as dt
import gzip
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"
KEV = ("https://www.cisa.gov/sites/default/files/feeds/"
       "known_exploited_vulnerabilities.json")
ANIO_INICIAL = 2023
PAUSA = 7
# estados con ficha completa del NVD: puntuación y productos afectados
COMPLETA = ("Analyzed", "Modified")


def pide(url: str, **kw) -> dict:
    """Hace una petición con reintentos.

    Args:
        url: punto de entrada.
        **kw: parámetros de consulta.

    Returns:
        el JSON de la respuesta.
    """
    u = url + ("?" + urllib.parse.urlencode(kw) if kw else "")
    r = urllib.request.Request(u, headers={"User-Agent": "ManPla.net"})
    for i in range(6):
        try:
            with urllib.request.urlopen(r, timeout=180) as f:
                return json.load(f)
        except Exception as e:  # noqa: BLE001
            if i == 5:
                raise
            print(f"    reintento {i + 1}: {type(e).__name__}", flush=True)
            time.sleep(15 * (i + 1))
    raise RuntimeError("sin respuesta")


def ventanas(ini: str, fin: str):
    """Parte un periodo en tramos de 110 días; la API admite 120 como mucho."""
    a, b = dt.date.fromisoformat(ini), dt.date.fromisoformat(fin)
    while a <= b:
        c = min(a + dt.timedelta(days=110), b)
        yield (a.isoformat() + "T00:00:00.000",
               c.isoformat() + "T23:59:59.999")
        a = c + dt.timedelta(days=1)


def catalogo_kev() -> dict:
    """Devuelve {cve: fecha de alta} del catálogo de explotadas."""
    d = pide(KEV)
    return {v["cveID"]: v["dateAdded"] for v in d["vulnerabilities"]}


def recorre(ini: str, fin: str, kev: dict):
    """Genera una fila por CVE publicado en el periodo, sin los rechazados."""
    for p0, p1 in ventanas(ini, fin):
        i = 0
        while True:
            d = pide(NVD, pubStartDate=p0, pubEndDate=p1, resultsPerPage=2000,
                     startIndex=i, noRejected="")
            for v in d["vulnerabilities"]:
                c = v["cve"]
                yield [c["id"], c["published"][:10], c["vulnStatus"],
                       int(c["id"] in kev), kev.get(c["id"], "")]
            i += d["resultsPerPage"]
            print(f"    {p0[:10]}: {i}/{d['totalResults']}", flush=True)
            if i >= d["totalResults"]:
                break
            time.sleep(PAUSA)
        time.sleep(PAUSA)


def agrega(filas: list[dict]) -> tuple[list[dict], list[dict]]:
    """Agrega por año y, para el último año, por mes.

    Args:
        filas: diccionarios con cve, publicado, estado y en_kev.

    Returns:
        (por_anio, por_mes), listas de diccionarios listas para csv.
    """
    por_anio = []
    anios = sorted({f["publicado"][:4] for f in filas})
    for a in anios:
        fa = [f for f in filas if f["publicado"][:4] == a]
        c = collections.Counter(f["estado"] for f in fa)
        completa = sum(c[e] for e in COMPLETA)
        por_anio.append({
            "anio": a, "publicados": len(fa), "ficha_completa": completa,
            "analizados": c["Analyzed"], "modificados": c["Modified"],
            "aplazados": c["Deferred"], "recibidos": c["Received"],
            "en_espera": c["Awaiting Analysis"],
            "en_analisis": c["Undergoing Analysis"],
            "explotados": sum(int(f["en_kev"]) for f in fa),
            "pct_ficha_completa": round(100 * completa / len(fa), 2),
            "pct_aplazados": round(100 * c["Deferred"] / len(fa), 2),
        })
    ultimo = anios[-1]
    por_mes = []
    fm = [f for f in filas if f["publicado"][:4] == ultimo]
    for m in sorted({f["publicado"][:7] for f in fm}):
        g = [f for f in fm if f["publicado"][:7] == m]
        apl = sum(1 for f in g if f["estado"] == "Deferred")
        comp = sum(1 for f in g if f["estado"] in COMPLETA)
        por_mes.append({"mes": m, "publicados": len(g), "aplazados": apl,
                        "ficha_completa": comp,
                        "pct_aplazados": round(100 * apl / len(g), 2)})
    return por_anio, por_mes


def escribe_csv(ruta: Path, filas: list[dict]) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def instantanea(hoy: str, corte: str, n_kev: int, por_anio: list[dict],
                por_mes: list[dict]) -> str:
    u = por_anio[-1]
    lineas = [
        "# Instantánea — estado de enriquecimiento de los CVE en el NVD", "",
        f"- Extracción: {hoy}, contra la API 2.0 del NVD "
        f"(`{NVD}`), sin clave.",
        f"- Periodo: CVE publicados desde el 01-01-{ANIO_INICIAL} hasta el "
        f"{corte}, sin los rechazados (`noRejected`).",
        f"- Catálogo de explotadas de CISA en el momento de la extracción: "
        f"{n_kev} entradas.",
        "- Con ficha completa se cuentan los estados `Analyzed` y `Modified`,"
        " que son los que llevan puntuación y lista de productos afectados"
        " puestas por el NVD.", "",
        "| año | publicados | ficha completa | aplazados | explotados |",
        "|---|---|---|---|---|",
    ]
    for r in por_anio:
        lineas.append(f"| {r['anio']} | {r['publicados']} | "
                      f"{r['pct_ficha_completa']} % | {r['pct_aplazados']} %"
                      f" | {r['explotados']} |")
    lineas += ["", f"Aplazados de {u['anio']} por mes de publicación:", ""]
    lineas += [f"- {r['mes']}: {r['aplazados']} de {r['publicados']} "
               f"({r['pct_aplazados']} %)" for r in por_mes]
    lineas += ["", "## Columnas de `cve-estados.csv.gz`", "",
               "| columna | origen |", "|---|---|",
               "| `cve` | `cve.id` de la API |",
               "| `publicado` | `cve.published`, fecha |",
               "| `estado` | `cve.vulnStatus` |",
               "| `en_kev` | 1 si el identificador está en el catálogo |",
               "| `kev_alta` | `dateAdded` del catálogo, si está |", "",
               "No interviene ningún dato de ninguna persona."]
    return "\n".join(lineas) + "\n"


def main() -> None:
    hoy = dt.date.today()
    corte = (hoy - dt.timedelta(days=1)).isoformat()
    kev = catalogo_kev()
    print(f"catálogo de explotadas: {len(kev)} entradas", flush=True)
    filas = []
    with gzip.open(AQUI / "cve-estados.csv.gz", "wt", newline="",
                   encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cve", "publicado", "estado", "en_kev", "kev_alta"])
        for a in range(ANIO_INICIAL, hoy.year + 1):
            print(f"=== {a}", flush=True)
            fin = f"{a}-12-31" if a < hoy.year else corte
            for fila in recorre(f"{a}-01-01", fin, kev):
                w.writerow(fila)
                filas.append(dict(zip(["cve", "publicado", "estado",
                                       "en_kev", "kev_alta"], fila)))
    por_anio, por_mes = agrega(filas)
    escribe_csv(AQUI / "por-anio.csv", por_anio)
    escribe_csv(AQUI / "por-mes.csv", por_mes)
    (AQUI / "resumen.json").write_text(json.dumps({
        "extraccion": hoy.isoformat(), "corte": corte, "kev_entradas": len(kev),
        "por_anio": por_anio, "por_mes": por_mes}, ensure_ascii=False,
        indent=1), encoding="utf-8")
    (AQUI / "INSTANTANEA.md").write_text(
        instantanea(hoy.strftime("%d-%m-%Y"), corte, len(kev), por_anio,
                    por_mes), encoding="utf-8")
    print("hecho:", len(filas), "filas")


if __name__ == "__main__":
    main()
