"""La ola de modelos de decisión tipada en Hugging Face, semana a semana.

Se piden a la API pública de Hugging Face los repositorios de modelos con
cualquiera de las cinco etiquetas con que se publican los modelos de
decisión tipada (decision-model, system-one, jev, typed-decision, decider),
se unen sin repetir y se cuentan por semana de creación (lunes a domingo,
según el campo createdAt). No hace falta GPU ni cuenta.

Uso:
    python ola.py

Salidas, junto a este fichero:
    ola_repos.csv: un repositorio por fila, con su fecha de creación, las
        etiquetas por las que entra, descargas y «me gusta» del día;
    ola_semanal.csv: repositorios creados por semana.
"""

import csv
import datetime as dt
import json
import random
import re
import time
import urllib.request
from collections import Counter
from pathlib import Path

from tqdm import tqdm

RAIZ = Path(__file__).resolve().parent
ETIQUETAS = ("decision-model", "system-one", "jev", "typed-decision",
             "decider")
API = "https://huggingface.co/api/models?filter={}&limit=1000"
UA = "ManPlaNet-medicion/1.0 (+https://manpla.net)"


def pedir(url: str) -> tuple[list[dict], str]:
    """una página de la API y el enlace a la siguiente, si lo hay.

    Args:
        url: dirección de la página.

    Returns:
        Los modelos de la página y la URL de la siguiente (cadena vacía si
        es la última).
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        datos = json.load(r)
        enlace = r.headers.get("Link", "")
    m = re.search(r'<([^>]+)>;\s*rel="next"', enlace)
    return datos, m.group(1) if m else ""


def lunes(fecha: str) -> str:
    """lunes de la semana de una fecha ISO."""
    d = dt.date.fromisoformat(fecha[:10])
    return (d - dt.timedelta(days=d.weekday())).isoformat()


def mostrar(filas: list[dict], nombre: str) -> None:
    """15 filas al azar del fichero recién guardado."""
    print(f"\n{nombre}: {len(filas)} filas; 15 al azar")
    for f in random.Random(0).sample(filas, min(15, len(filas))):
        print("  ", f)


def main() -> None:
    repos: dict[str, dict] = {}
    for etiqueta in tqdm(ETIQUETAS, desc="etiquetas"):
        url = API.format(etiqueta)
        while url:
            pagina, url = pedir(url)
            for m in pagina:
                r = repos.setdefault(m["id"], {
                    "repo": m["id"], "creado": m.get("createdAt", ""),
                    "etiquetas": set(), "descargas": m.get("downloads", 0),
                    "me_gusta": m.get("likes", 0)})
                r["etiquetas"].add(etiqueta)
            time.sleep(0.5)
    filas = sorted(({**r, "etiquetas": "|".join(sorted(r["etiquetas"]))}
                    for r in repos.values()), key=lambda r: r["creado"])
    # se guarda en csv
    with open(RAIZ / "ola_repos.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    mostrar(filas, "ola_repos.csv")
    semanas = Counter(lunes(r["creado"]) for r in filas if r["creado"])
    sem = [{"semana": s, "repos": n} for s, n in sorted(semanas.items())]
    with open(RAIZ / "ola_semanal.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["semana", "repos"])
        w.writeheader()
        w.writerows(sem)
    mostrar(sem, "ola_semanal.csv")
    print(f"\n{len(filas)} repositorios únicos; consultado el "
          f"{dt.date.today().isoformat()}")


if __name__ == "__main__":
    main()
