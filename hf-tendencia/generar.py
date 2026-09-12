#!/usr/bin/env python3
"""Instantánea del escaparate de Hugging Face: los 100 en tendencia.

Lee la API pública del Hub y guarda, de cada repositorio, los tres números
que el propio Hub muestra —tendencia, descargas y likes—, su fecha de
creación y si contiene alguno de los ficheros de consulta con los que el Hub
cuenta descargas. No descarga pesos ni código: solo metadatos.

Se guarda en csv y se escribe la ficha de procedencia al lado.
"""
import csv
import datetime
import json
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://huggingface.co/api/models"
DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo
# ficheros de consulta por defecto, según la documentación del Hub
CONSULTA = {"config.json", "config.yaml", "hyperparams.yaml", "params.json",
            "meta.yaml"}


def pedir(url: str) -> list | dict:
    """una petición al Hub, sin credenciales."""
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def ficha(repo: str) -> dict:
    """el detalle de un repositorio, con su listado de ficheros."""
    return pedir(f"{API}/{urllib.parse.quote(repo, safe='/')}")


def main(n: int = 100) -> None:
    lista = pedir(f"{API}?sort=trendingScore&direction=-1&limit={n}")
    hoy = datetime.date.today()
    filas = []
    for i, m in enumerate(lista, 1):
        try:
            d = ficha(m["modelId"])
        except Exception:
            d = {}
        ficheros = [f["rfilename"] for f in d.get("siblings", [])]
        creado = (m.get("createdAt") or "")[:10]
        filas.append({
            "puesto": i,
            "id": m["modelId"],
            "descargas": m.get("downloads") or 0,
            "likes": m.get("likes") or 0,
            "creado": creado,
            "edad_dias": ((hoy - datetime.date.fromisoformat(creado)).days
                          if creado else ""),
            "biblioteca": d.get("library_name") or m.get("library_name") or "",
            "ficheros": len(ficheros),
            "con_fichero_consulta": int(bool(CONSULTA & set(ficheros))),
            "safetensors_raiz": int(any(
                f.endswith(".safetensors") and "/" not in f for f in ficheros)),
        })

    DESTINO.mkdir(parents=True, exist_ok=True)
    campos = list(filas[0])
    with (DESTINO / "tendencia.csv").open("w", newline="",
                                          encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)

    cero = sum(1 for r in filas if r["descargas"] == 0)
    sin_q = sum(1 for r in filas if not r["con_fichero_consulta"])
    (DESTINO / "INSTANTANEA.md").write_text(f"""# Instantánea del escaparate de Hugging Face

Metadatos de los {len(filas)} repositorios con más «trending score» del Hub.
No contiene pesos ni código: solo los números que el propio Hub publica y el
recuento de ficheros de cada repositorio.

- API: {API}?sort=trendingScore&direction=-1&limit={len(filas)}
- Extraído: {hoy.isoformat()}
- Con cero descargas: {cero}
- Sin ningún fichero de consulta por defecto: {sin_q}

## Campos

| Columna | Origen |
|---|---|
| `puesto` | orden de la respuesta del Hub por `trendingScore` |
| `descargas`, `likes` | los que publica el Hub en la ficha del modelo |
| `creado`, `edad_dias` | `createdAt`, y su distancia a la fecha del sondeo |
| `biblioteca` | `library_name` declarada en el repositorio |
| `ficheros` | número de entradas en `siblings` |
| `con_fichero_consulta` | 1 si contiene alguno de los cinco ficheros de consulta por defecto |
| `safetensors_raiz` | 1 si tiene algún `.safetensors` en la raíz, no anidado |

Las dos últimas columnas son cálculo propio sobre el listado de ficheros, y
sirven para contrastar el recuento de descargas contra el mecanismo que el
Hub documenta. La lista de ficheros de consulta por defecto se toma de la
documentación del Hub y puede cambiar sin aviso.
""", encoding="utf-8")
    print(f"[hf] {len(filas)} repos · {cero} con cero descargas · "
          f"{sin_q} sin fichero de consulta")


if __name__ == "__main__":
    main()
