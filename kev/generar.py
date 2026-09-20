#!/usr/bin/env python3
"""Instantánea del catálogo KEV de CISA: altas por día, ventanas y triaje.

Descarga el feed público del «Known Exploited Vulnerabilities Catalog» y
deja tres cosas al lado: la cadencia (una fila por día con altas), la
ventana entre el alta y la fecha límite mes a mes, y las entradas que
llevan la marca de triaje forense —`forensicTriage`, la columna que el
catálogo trae desde la directiva BOD 26-04—. No redistribuye el catálogo:
`altas.csv` y `ventanas-mensuales.csv` son recuentos, y
`triaje-forense.csv` lleva solo el identificador público, el proveedor, el
producto y las fechas de las entradas marcadas.

Se guarda en csv y json y se escribe la ficha de procedencia al lado.
"""
import csv
import datetime
import json
import urllib.request
from collections import Counter
from pathlib import Path

FEED = ("https://www.cisa.gov/sites/default/files/feeds/"
        "known_exploited_vulnerabilities.json")
DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado",
        "domingo"]
BOD_26_04 = datetime.date(2026, 6, 10)       # entrada en vigor de la directiva


def descargar() -> dict:
    """se trae el feed entero; el catálogo ronda los 1,7 MB."""
    req = urllib.request.Request(FEED, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def fecha(s: str) -> datetime.date:
    return datetime.date.fromisoformat(s)


def ventana(x: dict) -> int:
    """días naturales entre el alta y la fecha límite."""
    return (fecha(x["dueDate"]) - fecha(x["dateAdded"])).days


def resumir_altas(cat: dict) -> list[dict]:
    """agrupa las entradas por fecha de alta."""
    por_dia: dict[str, int] = {}
    for x in cat["vulnerabilities"]:
        por_dia[x["dateAdded"]] = por_dia.get(x["dateAdded"], 0) + 1
    filas = []
    for f in sorted(por_dia):
        d = fecha(f)
        filas.append({"fecha": f, "dia_semana": DIAS[d.weekday()],
                      "altas": por_dia[f]})
    return filas


def resumir_ventanas(cat: dict) -> list[dict]:
    """una fila por mes: altas y cuántas tuvieron cada ventana."""
    meses: dict[str, Counter] = {}
    for x in cat["vulnerabilities"]:
        c = meses.setdefault(x["dateAdded"][:7], Counter())
        c["altas"] += 1
        v = ventana(x)
        c["ventana_3" if v == 3 else "ventana_14" if v == 14
          else "ventana_21" if v == 21 else "ventana_otra"] += 1
        if x.get("forensicTriage") == "Yes":
            c["triaje_forense"] += 1
    return [{"mes": m, **{k: meses[m].get(k, 0) for k in (
        "altas", "ventana_3", "ventana_14", "ventana_21", "ventana_otra",
        "triaje_forense")}} for m in sorted(meses)]


def marcadas(cat: dict) -> list[dict]:
    """las entradas con forensicTriage = Yes, una por fila."""
    filas = []
    for x in cat["vulnerabilities"]:
        if x.get("forensicTriage") != "Yes":
            continue
        filas.append({
            "cve": x["cveID"], "proveedor": x["vendorProject"],
            "producto": x["product"], "fecha_alta": x["dateAdded"],
            "vencimiento": x["dueDate"], "ventana_dias": ventana(x),
            "ransomware": x.get("knownRansomwareCampaignUse", ""),
            "cwe": ";".join(x.get("cwes", [])),
            "componente_compartido": "open-source component" in x.get(
                "notes", "")})
    return sorted(filas, key=lambda r: (r["fecha_alta"], r["cve"]))


def escribir_csv(nombre: str, filas: list[dict]) -> None:
    with (DESTINO / nombre).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def main() -> None:
    cat = descargar()
    vul = cat["vulnerabilities"]
    altas = resumir_altas(cat)
    ventanas = resumir_ventanas(cat)
    marca = marcadas(cat)
    DESTINO.mkdir(parents=True, exist_ok=True)
    escribir_csv("altas.csv", altas)
    escribir_csv("ventanas-mensuales.csv", ventanas)
    escribir_csv("triaje-forense.csv", marca)

    finde = sum(r["altas"] for r in altas
                if r["dia_semana"] in ("sábado", "domingo"))
    desde_bod = [x for x in vul if fecha(x["dateAdded"]) >= BOD_26_04]
    cruce = Counter((ventana(x), x.get("forensicTriage", ""))
                    for x in desde_bod)
    resumen = {
        "version_catalogo": cat["catalogVersion"],
        "publicado_por_cisa": cat["dateReleased"],
        "extraido": datetime.date.today().isoformat(),
        "entradas": cat["count"],
        "dias_con_altas": len(altas),
        "altas_en_fin_de_semana": finde,
        "triaje_forense": {
            "si": len(marca),
            "no": sum(1 for x in vul if x.get("forensicTriage") == "No"),
            "sin_campo": sum(1 for x in vul if "forensicTriage" not in x),
            "primera_marca": marca[0]["fecha_alta"] if marca else None,
            "ultima_marca": marca[-1]["fecha_alta"] if marca else None,
            "dias_con_marca": len({r["fecha_alta"] for r in marca}),
            "ventanas_de_las_marcadas": dict(Counter(
                r["ventana_dias"] for r in marca)),
            "por_mes": dict(sorted(Counter(
                r["fecha_alta"][:7] for r in marca).items())),
            "por_proveedor": dict(Counter(
                r["proveedor"] for r in marca).most_common()),
            "ransomware_conocido": sum(
                1 for r in marca if r["ransomware"] == "Known"),
            "componente_compartido": sum(
                1 for r in marca if r["componente_compartido"]),
            "por_anio_del_cve": dict(sorted(Counter(
                r["cve"][4:8] for r in marca).items())),
            "por_dia_semana": dict(Counter(
                DIAS[fecha(r["fecha_alta"]).weekday()] for r in marca)),
        },
        "desde_bod_26_04": {
            "desde": BOD_26_04.isoformat(),
            "altas": len(desde_bod),
            "ventana_3_con_triaje": cruce[(3, "Yes")],
            "ventana_3_sin_triaje": cruce[(3, "No")],
            "ventana_14": sum(n for (v, _), n in cruce.items() if v == 14),
            "otras": sum(n for (v, _), n in cruce.items()
                         if v not in (3, 14)),
        },
        "ventana_mediana_por_mes_2026": {
            m["mes"]: sorted(ventana(x) for x in vul
                             if x["dateAdded"].startswith(m["mes"]))[
                m["altas"] // 2]
            for m in ventanas if m["mes"].startswith("2026")},
    }
    (DESTINO / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    t = resumen["triaje_forense"]
    b = resumen["desde_bod_26_04"]
    ficha = f"""# Instantánea del catálogo KEV

Recuentos y una lista corta, no el catálogo: `altas.csv` y
`ventanas-mensuales.csv` no contienen identificadores de vulnerabilidad,
productos ni descripciones; `triaje-forense.csv` lleva solo el identificador
público, el proveedor, el producto y las fechas de las entradas que el
catálogo marca con `forensicTriage = Yes`. El catálogo íntegro lo publica
CISA y se consulta en la fuente.

- Feed: {FEED}
- Versión del catálogo: `{cat['catalogVersion']}`
- Publicado por CISA: {cat['dateReleased']}
- Extraído: {resumen['extraido']}
- Entradas del catálogo: {cat['count']}
- Días con altas: {len(altas)}
- Primer día: {altas[0]['fecha']} · último: {altas[-1]['fecha']}
- Entradas dadas de alta en sábado o domingo: {finde}
- Entradas con marca de triaje forense: {t['si']} (la primera, el
  {t['primera_marca']}; la última, el {t['ultima_marca']})
- Altas desde la BOD 26-04 ({b['desde']}): {b['altas']} —
  {b['ventana_3_con_triaje']} con ventana de tres días y marca,
  {b['ventana_3_sin_triaje']} con tres días sin marca, {b['ventana_14']}
  con catorce días—

## Campos

### `altas.csv`

| Columna | Origen |
|---|---|
| `fecha` | `dateAdded` de las entradas, agrupado |
| `dia_semana` | derivado de `fecha`, en huso local del catálogo |
| `altas` | número de entradas con esa `dateAdded` |

### `ventanas-mensuales.csv`

| Columna | Origen |
|---|---|
| `mes` | `dateAdded`, año y mes |
| `altas` | entradas dadas de alta ese mes |
| `ventana_3`, `ventana_14`, `ventana_21`, `ventana_otra` | entradas
  según los días naturales entre `dateAdded` y `dueDate` |
| `triaje_forense` | entradas del mes con `forensicTriage = Yes` |

### `triaje-forense.csv`

| Columna | Origen |
|---|---|
| `cve`, `proveedor`, `producto` | `cveID`, `vendorProject`, `product` |
| `fecha_alta`, `vencimiento` | `dateAdded`, `dueDate` |
| `ventana_dias` | días naturales entre ambas |
| `ransomware` | `knownRansomwareCampaignUse` |
| `cwe` | `cwes`, separados por punto y coma |
| `componente_compartido` | si `notes` dice que afecta a un componente
  de código abierto o protocolo usado por distintos productos |

El día de la semana es cálculo propio sobre la fecha que publica CISA, que
no incluye hora: una alta de última hora del viernes y otra de primera hora
del lunes se distinguen por su fecha, no por su marca de tiempo. El
significado de la marca de triaje no lo define el feed: lo fija la tabla de
plazos de la BOD 26-04 («& forensic triage» en el escalón de tres días) y su
guía de implantación.
"""
    (DESTINO / "INSTANTANEA.md").write_text(ficha, encoding="utf-8")
    print(f"[kev] {cat['catalogVersion']} · {cat['count']} entradas · "
          f"{len(altas)} días de alta · {finde} en fin de semana · "
          f"{t['si']} con triaje forense")


if __name__ == "__main__":
    main()
