#!/usr/bin/env python3
"""Instantánea del catálogo KEV de CISA: altas por día.

Descarga el feed público del «Known Exploited Vulnerabilities Catalog» y
resume su cadencia: una fila por día en que hubo altas, con el día de la
semana y cuántas entradas se dieron de alta. No redistribuye el catálogo,
solo el recuento agregado que sostiene las figuras del artículo.

Se guarda en csv y se escribe la ficha de procedencia al lado.
"""
import csv
import datetime
import json
import urllib.request
from pathlib import Path

FEED = ("https://www.cisa.gov/sites/default/files/feeds/"
        "known_exploited_vulnerabilities.json")
DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado",
        "domingo"]


def descargar() -> dict:
    """se trae el feed entero; el catálogo ronda los 1,7 MB."""
    with urllib.request.urlopen(FEED, timeout=90) as r:
        return json.load(r)


def resumir(cat: dict) -> list[dict]:
    """agrupa las entradas por fecha de alta."""
    por_dia: dict[str, int] = {}
    for x in cat["vulnerabilities"]:
        por_dia[x["dateAdded"]] = por_dia.get(x["dateAdded"], 0) + 1
    filas = []
    for fecha in sorted(por_dia):
        d = datetime.date.fromisoformat(fecha)
        filas.append({"fecha": fecha, "dia_semana": DIAS[d.weekday()],
                      "altas": por_dia[fecha]})
    return filas


def main() -> None:
    cat = descargar()
    filas = resumir(cat)
    DESTINO.mkdir(parents=True, exist_ok=True)
    with (DESTINO / "altas.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["fecha", "dia_semana", "altas"])
        w.writeheader()
        w.writerows(filas)

    finde = sum(r["altas"] for r in filas
                if r["dia_semana"] in ("sábado", "domingo"))
    ficha = f"""# Instantánea del catálogo KEV

Recuento agregado, no el catálogo: `altas.csv` no contiene identificadores
de vulnerabilidad, productos ni descripciones, solo cuántas entradas se
dieron de alta cada día. El catálogo íntegro lo publica CISA y se consulta
en la fuente.

- Feed: {FEED}
- Versión del catálogo: `{cat['catalogVersion']}`
- Publicado por CISA: {cat['dateReleased']}
- Extraído: {datetime.date.today().isoformat()}
- Entradas del catálogo: {cat['count']}
- Días con altas: {len(filas)}
- Primer día: {filas[0]['fecha']} · último: {filas[-1]['fecha']}
- Entradas dadas de alta en sábado o domingo: {finde}

## Campos

| Columna | Origen |
|---|---|
| `fecha` | `dateAdded` de las entradas, agrupado |
| `dia_semana` | derivado de `fecha`, en huso local del catálogo |
| `altas` | número de entradas con esa `dateAdded` |

El día de la semana es cálculo propio sobre la fecha que publica CISA, que
no incluye hora: una alta de última hora del viernes y otra de primera hora
del lunes se distinguen por su fecha, no por su marca de tiempo.
"""
    (DESTINO / "INSTANTANEA.md").write_text(ficha, encoding="utf-8")
    print(f"[kev] {cat['catalogVersion']} · {cat['count']} entradas · "
          f"{len(filas)} días de alta · {finde} en fin de semana")


if __name__ == "__main__":
    main()
