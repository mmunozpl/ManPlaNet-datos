#!/usr/bin/env python3
"""Instantánea del marcador verificado de ARC-AGI: puntuación, coste y arnés.

Descarga los cuatro JSON públicos con que arcprize.org pinta su marcador
—conjuntos, modelos, proveedores y evaluaciones— y deja al lado tres
tablas: el marcador de las tres versiones con su arnés, la frontera por
fecha de publicación del modelo, y el hueco entre el conjunto público y el
semiprivado de ARC-AGI-2, que la propia política de pruebas de ARC Prize
señala como indicio de exposición del semiprivado. Si el cliente de Kaggle
está configurado, añade la cabecera de las dos tablas públicas de ARC Prize
2026, que miden soluciones abiertas sin acceso a la red.

Son cifras publicadas, no tareas: ninguna tarea del ARC-AGI se descarga.
Se guarda en csv y json y se escribe la ficha de procedencia al lado.
"""
import csv
import datetime
import json
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

BASE = "https://arcprize.org/media/data/"
FICHEROS = ["datasets", "models", "providers", "evaluations"]
DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo
HOY = datetime.date.today()
# lanzamiento público de cada versión, según los anuncios de ARC Prize
LANZAMIENTO = {"v1": "2019-11-05", "v2": "2025-03-24", "v3": "2026-03-25"}
KAGGLE = {"ARC-AGI-3": "arc-prize-2026-arc-agi-3",
          "ARC-AGI-2": "arc-prize-2026-arc-agi-2"}


def descargar(nombre: str) -> list:
    """se trae un JSON del marcador; ninguno pasa de 200 kB."""
    req = urllib.request.Request(BASE + nombre + ".json",
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def arnes(modelo: dict) -> str:
    """el arnés va en el nombre: solo ARC-AGI-3 distingue dos."""
    nombre = modelo.get("displayName") or ""
    return "provider-adapter" if "Provider Adapter" in nombre else "standard"


def marcador(evals: list, modelos: dict) -> list[dict]:
    """una fila por evaluación mostrada, con coste por tarea o total."""
    filas = []
    for e in evals:
        if not e.get("display"):
            continue
        m = modelos.get(e["modelId"], {})
        fecha = (m.get("modelReleaseDate") or "")[:10]
        filas.append({
            "conjunto": e["datasetId"],
            "modelo_id": e["modelId"],
            "modelo": m.get("displayName") or e["modelId"],
            "proveedor": m.get("providerId") or "",
            "publicacion": fecha,
            "arnes": arnes(m) if e["datasetId"].startswith("v3") else "",
            "puntuacion": e.get("score"),
            # v1 y v2 publican coste por tarea; v3, coste total de la pasada
            "coste_por_tarea": e.get("costPerTask", ""),
            "coste_total": e.get("cost", ""),
        })
    filas.sort(key=lambda f: (f["conjunto"], -(f["puntuacion"] or 0)))
    return filas


def frontera(filas: list[dict]) -> list[dict]:
    """la mejor puntuación acumulada, fecha a fecha, por versión y arnés."""
    salida = []
    claves = sorted({(f["conjunto"], f["arnes"]) for f in filas
                     if f["conjunto"].endswith("Semi_Private")})
    for conjunto, arn in claves:
                # las entradas de competición llevan la fecha de su edición, no la
        # de publicación, y no entran en una frontera por fecha
        sel = [f for f in filas if f["conjunto"] == conjunto
               and f["arnes"] == arn and f["publicacion"]
               and not f["proveedor"].startswith("ARC Prize")]
        sel.sort(key=lambda f: (f["publicacion"], -(f["puntuacion"] or 0)))
        mejor = -1.0
        for f in sel:
            if (f["puntuacion"] or 0) > mejor:
                mejor = f["puntuacion"]
                salida.append({"conjunto": conjunto, "arnes": arn,
                               "publicacion": f["publicacion"],
                               "modelo": f["modelo"],
                               "puntuacion": mejor})
    return salida


def hueco_v2(filas: list[dict]) -> list[dict]:
    """público menos semiprivado de ARC-AGI-2, modelo a modelo."""
    pub = {f["modelo_id"]: f for f in filas
           if f["conjunto"] == "v2_Public_Eval"}
    salida = []
    for f in filas:
        if f["conjunto"] != "v2_Semi_Private" or f["modelo_id"] not in pub:
            continue
        p = pub[f["modelo_id"]]
        if f["puntuacion"] is None or p["puntuacion"] is None:
            continue
        salida.append({"modelo": f["modelo"],
                       "publicacion": f["publicacion"],
                       "publico": p["puntuacion"],
                       "semiprivado": f["puntuacion"],
                       "hueco_pp": round(100 * (p["puntuacion"]
                                                - f["puntuacion"]), 2)})
    salida.sort(key=lambda x: x["publicacion"])
    return salida


def kaggle() -> list[dict]:
    """cabecera de las dos tablas públicas, si hay cliente configurado."""
    if not shutil.which("kaggle"):
        return []
    filas = []
    for reto, slug in KAGGLE.items():
        # la salida csv (-v) del cliente 2.2.1 falla al autenticar, así que
        # se lee la tabla en texto: id, equipo, fecha y hora, puntuación
        r = subprocess.run(["kaggle", "competitions", "leaderboard", slug,
                            "-s"], capture_output=True, text=True)
        patron = re.compile(r"^\s*\d+\s+(.+?)\s{2,}(\d{4}-\d\d-\d\d)"
                            r"\S*\s+\S+\s+([\d.]+)\s*$")
        pos = 0
        for l in r.stdout.splitlines():
            m = patron.match(l)
            if m and pos < 10:
                pos += 1
                filas.append({"reto": reto, "puesto": pos,
                              "equipo": m.group(1).strip(),
                              "envio": m.group(2),
                              "puntuacion": float(m.group(3))})
    return filas


def escribir(nombre: str, filas: list[dict]) -> None:
    if not filas:
        return
    with open(DESTINO / nombre, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def main() -> None:
    datos = {n: descargar(n) for n in FICHEROS}
    modelos = {m["id"]: m for m in datos["models"]}
    filas = marcador(datos["evaluations"], modelos)
    front = frontera(filas)
    hueco = hueco_v2(filas)
    kag = kaggle()
    escribir("marcador.csv", filas)
    escribir("frontera.csv", front)
    escribir("hueco-v2.csv", hueco)
    escribir("kaggle-2026.csv", kag)

    # se resume la cifra de cada versión para el artículo
    v3 = [f for f in filas if f["conjunto"] == "v3_Semi_Private"]
    mejor = {a: max((f for f in v3 if f["arnes"] == a),
                    key=lambda f: f["puntuacion"]) for a in
             ("standard", "provider-adapter")}
    resumen = {
        "extraido": HOY.isoformat(),
        "lanzamiento": LANZAMIENTO,
        "evaluaciones": len(filas),
        "v3_mejor": {a: {k: mejor[a][k] for k in
                         ("modelo", "puntuacion", "coste_total")}
                     for a in mejor},
        "v3_lanzamiento_mejor": max(
            (f for f in v3 if f["publicacion"] <= LANZAMIENTO["v3"]),
            key=lambda f: f["puntuacion"])["puntuacion"],
        "kaggle_cabeza": {r: max((k["puntuacion"] for k in kag
                                  if k["reto"] == r), default=None)
                          for r in KAGGLE},
    }
    with open(DESTINO / "resumen.json", "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1)

    (DESTINO / "INSTANTANEA.md").write_text(f"""# Instantánea del marcador de ARC-AGI

Cifras publicadas por ARC Prize en los JSON que alimentan su marcador
verificado. No contiene ninguna tarea del ARC-AGI.

- Fuente: {BASE}{{datasets,models,providers,evaluations}}.json
- Extraído: {HOY.isoformat()}
- Evaluaciones mostradas: {len(filas)}
- Kaggle: cabecera de las tablas públicas de ARC Prize 2026
  ({", ".join(KAGGLE.values())}), si el cliente está configurado

## Ficheros

| Fichero | Contenido |
|---|---|
| `marcador.csv` | una fila por evaluación mostrada: conjunto, modelo, fecha de publicación del modelo, arnés (solo ARC-AGI-3), puntuación, coste por tarea (v1, v2) o total de la pasada (v3) |
| `frontera.csv` | la mejor puntuación acumulada por fecha de publicación, por versión y arnés, en los conjuntos semiprivados; sin las entradas de competición, fechadas por su edición |
| `hueco-v2.csv` | puntuación en el conjunto público menos la del semiprivado de ARC-AGI-2, modelo a modelo |
| `kaggle-2026.csv` | diez primeros puestos de cada tabla pública de Kaggle |
| `resumen.json` | las cifras que cita el artículo |

La puntuación de ARC-AGI-3 no es un porcentaje de juegos resueltos: pondera
cada nivel por la eficiencia en acciones frente a la línea base humana —el
cociente al cuadrado, con tope en 1,15 por nivel—, pondera los niveles por su
número y promedia por juego. El conjunto semiprivado tiene 55 entornos. La
tabla pública de Kaggle no es la clasificación final del premio.
""", encoding="utf-8")

    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    import random
    print("\n15 filas aleatorias del marcador:")
    for f in random.Random(20260925).sample(filas, 15):
        print(f"  {f['conjunto']:16} {f['puntuacion']:.4f}  {f['modelo']}")


if __name__ == "__main__":
    main()
