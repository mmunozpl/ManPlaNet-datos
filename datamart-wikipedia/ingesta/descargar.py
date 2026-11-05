#!/usr/bin/env python3
"""Zona cruda: descarga de la API de analítica de Wikimedia la lista de los
mil artículos más vistos de cada día en un proyecto, por tipo de acceso, y
la guarda tal cual la sirve (JSON comprimido, un fichero por día y acceso)
con un manifiesto de lo descargado, y la lista mensual oficial (``all-days``)
de all-access de cada mes. Los días sin datos (404 de la API) se
anotan y no se inventan.

Uso: descargar.py --desde 2024-01-01 --hasta 2026-10-31 --salida DIR
     [--proyecto es.wikipedia] [--accesos all-access,desktop,mobile-web,mobile-app]
     [--hilos 8]
"""
import argparse
import csv
import datetime as dt
import gzip
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = "ManPlaNet-datos/1.0 (https://manpla.net; mmunozpl@uoc.edu)"
API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top"


def pedir(url: str, intentos: int = 5) -> tuple[int, bytes]:
    """GET con reintentos exponenciales; 404 y 200 se devuelven, lo demás se
    reintenta."""
    espera = 1.0
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, e.read()
            if e.code == 429 or e.code >= 500:
                time.sleep(espera); espera *= 2; continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(espera); espera *= 2
    return 0, b""


def descargar_dia(proyecto: str, acceso: str, dia: dt.date, salida: str) -> dict:
    carpeta = os.path.join(salida, "crudo", acceso, f"{dia:%Y}", f"{dia:%m}")
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, f"{dia:%d}.json.gz")
    marca = destino + ".404"
    fila = dict(fecha=dia.isoformat(), acceso=acceso, estado="", articulos=0, octetos=0)
    if os.path.exists(destino):
        with gzip.open(destino) as f:
            n = len(json.load(f)["items"][0]["articles"])
        fila.update(estado="en caché", articulos=n, octetos=os.path.getsize(destino)); return fila
    if os.path.exists(marca):
        fila.update(estado="sin datos (404)"); return fila
    cod, cuerpo = pedir(f"{API}/{proyecto}/{acceso}/{dia:%Y/%m/%d}")
    if cod == 200:
        with gzip.open(destino, "wb") as f:
            f.write(cuerpo)
        fila.update(estado="descargado", articulos=len(json.loads(cuerpo)["items"][0]["articles"]),
                    octetos=os.path.getsize(destino))
    elif cod == 404:
        open(marca, "w").close(); fila["estado"] = "sin datos (404)"
    else:
        fila["estado"] = f"error {cod}"
    return fila


def descargar_mes(proyecto: str, acceso: str, anio: int, mes: int, salida: str) -> dict:
    """La lista mensual oficial (día ``all-days``), la referencia externa con la
    que el medidor compara el ranking mensual derivado de las listas diarias."""
    carpeta = os.path.join(salida, "mensual", acceso, f"{anio:04d}")
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, f"{mes:02d}.json.gz")
    fila = dict(fecha=f"{anio:04d}-{mes:02d}", acceso=acceso, estado="", articulos=0, octetos=0)
    if os.path.exists(destino):
        with gzip.open(destino) as f:
            n = len(json.load(f)["items"][0]["articles"])
        fila.update(estado="en caché", articulos=n, octetos=os.path.getsize(destino)); return fila
    cod, cuerpo = pedir(f"{API}/{proyecto}/{acceso}/{anio:04d}/{mes:02d}/all-days")
    if cod == 200:
        with gzip.open(destino, "wb") as f:
            f.write(cuerpo)
        fila.update(estado="descargado", articulos=len(json.loads(cuerpo)["items"][0]["articles"]),
                    octetos=os.path.getsize(destino))
    else:
        fila["estado"] = f"error {cod}"
    return fila


def principal() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--desde", required=True); p.add_argument("--hasta", required=True)
    p.add_argument("--salida", required=True); p.add_argument("--proyecto", default="es.wikipedia")
    p.add_argument("--accesos", default="all-access,desktop,mobile-web,mobile-app")
    p.add_argument("--hilos", type=int, default=8)
    a = p.parse_args()
    desde, hasta = dt.date.fromisoformat(a.desde), dt.date.fromisoformat(a.hasta)
    dias = [desde + dt.timedelta(d) for d in range((hasta - desde).days + 1)]
    accesos = a.accesos.split(",")
    tareas = [(acc, d) for d in dias for acc in accesos]
    filas, t0 = [], time.time()
    with ThreadPoolExecutor(max_workers=a.hilos) as ex:
        futuros = [ex.submit(descargar_dia, a.proyecto, acc, d, a.salida) for acc, d in tareas]
        for k, f in enumerate(as_completed(futuros), 1):
            filas.append(f.result())
            if k % 200 == 0:
                print(f"{k}/{len(tareas)} · {time.time() - t0:.0f} s", flush=True)
    # las listas mensuales oficiales de all-access, una por mes del rango
    meses = sorted({(d.year, d.month) for d in dias})
    for anio, mes in meses:
        filas.append(descargar_mes(a.proyecto, "all-access", anio, mes, a.salida))
    filas.sort(key=lambda r: (r["acceso"], r["fecha"]))
    os.makedirs(a.salida, exist_ok=True)
    with open(os.path.join(a.salida, "manifiesto_crudo.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fecha", "acceso", "estado", "articulos", "octetos"])
        w.writeheader(); w.writerows(filas)
    est = {}
    for r in filas:
        est[r["estado"]] = est.get(r["estado"], 0) + 1
    print("hecho:", est, f"· {sum(r['octetos'] for r in filas) / 1e6:.1f} MB · {time.time() - t0:.0f} s")


if __name__ == "__main__":
    principal()
