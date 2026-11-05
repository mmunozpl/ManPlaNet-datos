#!/usr/bin/env python3
"""Resume desde el anfitrión (solo biblioteca estándar) lo que el medidor no
ve: el registro de Airflow (avisos de fallo y reintentos), las fases del
arranque, las líneas de configuración, las imágenes y la memoria; y escribe
la INSTANTANEA.md con las cifras de todos los CSV.

Uso: registros.py <dir de registros> <fases.csv> <dir de salida>
"""
import collections
import csv
import datetime as dt
import os
import re
import statistics
import sys

REGISTROS, FASES, SALIDA = sys.argv[1:4]
FICHEROS_CONFIG = [
    "compose.yaml", "laboratorio.sh", "postgres/init.sh", "airflow/Dockerfile",
    "airflow/dags/visualizaciones.py", "ingesta/descargar.py", "ingesta/s3.py",
    "ingesta/preparar.py", "dbt/dbt_project.yml", "dbt/profiles.yml",
    "dbt/macros/generate_schema_name.sql", "dbt/models/sources.yml",
    "dbt/models/staging/stg_visualizaciones.sql", "dbt/models/marts/dim_fecha.sql",
    "dbt/models/marts/dim_acceso.sql", "dbt/models/marts/dim_articulo.sql",
    "dbt/models/marts/hechos_visualizaciones.sql", "dbt/models/marts/hechos_ranking_mensual.sql",
    "dbt/models/marts/schema.yml", "dbt/models/intermedio/int_articulo_tramo.sql",
    "dbt/snapshots/snap_articulo_tramo.sql", "dbt/tests/grano_unico.sql",
    "dbt/tests/posicion_en_rango.sql", "dbt/tests/dias_contiguos.sql",
    "dbt/seeds/accesos.csv", "dbt/seeds/espacios_nombres.csv",
]


def escribir(nombre, filas, campos):
    with open(os.path.join(SALIDA, nombre), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader(); w.writerows(filas)


def leer_csv(nombre):
    ruta = os.path.join(SALIDA, nombre)
    if not os.path.exists(ruta):
        return []
    with open(ruta, newline="") as f:
        return list(csv.DictReader(f))


def avisos_airflow():
    """los avisos los cuenta el medidor en los registros de las tareas, por
    la API; aquí solo se leen para la instantánea."""
    return leer_csv("avisos_airflow.csv")


def esfuerzo():
    filas = []
    if os.path.exists(FASES):
        for linea in open(FASES):
            if linea.strip():
                fase, seg = linea.strip().rsplit(",", 1)
                filas.append(dict(fase=fase, segundos_acumulados=int(seg)))
    escribir("esfuerzo.csv", filas, ["fase", "segundos_acumulados"])
    return filas


def configuracion():
    filas = []
    for nombre in FICHEROS_CONFIG:
        ruta = os.path.join(SALIDA, nombre)
        if not os.path.exists(ruta):
            continue
        with open(ruta) as f:
            lineas = [l for l in f if l.strip() and not l.lstrip().startswith(("#", "--", "{#"))]
        filas.append(dict(fichero=nombre, lineas=len(lineas)))
    escribir("configuracion.csv", filas, ["fichero", "lineas"])
    return filas


def imagenes():
    filas, vistas = [], set()
    ruta = os.path.join(REGISTROS, "imagenes.txt")
    if os.path.exists(ruta):
        for linea in open(ruta):
            if "," in linea:
                imagen, tam = linea.strip().rsplit(",", 1)
                if imagen not in vistas:
                    vistas.add(imagen); filas.append(dict(imagen=imagen, tamano=tam))
    escribir("imagenes.csv", filas, ["imagen", "tamano"])
    return filas


def recursos():
    filas = []
    ruta = os.path.join(REGISTROS, "recursos.txt")
    if os.path.exists(ruta):
        for linea in open(ruta):
            if "," in linea:
                nombre, mem = linea.strip().split(",", 1)
                filas.append(dict(contenedor=nombre.replace("datamart-wikipedia-", "").replace("-1", ""), memoria=mem.split("/")[0].strip()))
    escribir("recursos.csv", filas, ["contenedor", "memoria"])
    return filas


def instantanea(avisos, fases, config, imgs, recs):
    cargas = leer_csv("cargas.csv"); consultas = leer_csv("consultas.csv"); estr = leer_csv("estrategias.csv")
    tests = leer_csv("tests_dbt.csv"); runs = leer_csv("runs_airflow.csv"); tareas = leer_csv("tareas_airflow.csv")
    tam = leer_csv("tamanos.csv"); pruebas = leer_csv("pruebas.csv")
    L = ["# Instantánea del laboratorio del DataMart", "",
         f"Medido el {dt.date.today().isoformat()}. PostgreSQL 17.11, Airflow 3.3.2, dbt-core 1.12.6 con "
         "dbt-postgres 1.11.0, RustFS 1.0.4 como S3; todo en Docker Compose en una sola máquina. Dato real: "
         "los mil artículos más vistos de cada día en es.wikipedia por tipo de acceso (API de Wikimedia), "
         "de enero de 2024 a octubre de 2026.", ""]
    if tam:
        L += ["## Tamaños", ""] + [f"- {t['objeto']}: {t['filas']} filas u objetos, {int(t['octetos']) / 1e6:.1f} MB" for t in tam]
    if cargas:
        L += ["", "## Cargas", ""] + [f"- {c['metodo']}: {c['filas']} filas en {int(c['ms']) / 1000:.1f} s ({c['filas_por_s']} filas/s)" for c in cargas]
    if consultas:
        L += ["", "## Consultas (mediana de 5, ms)", ""]
        for idx in ("0", "1"):
            for modelo in ("plano", "estrella", "copo"):
                vals = [float(c["ms"]) for c in consultas if c["modelo"] == modelo and c["indices"] == idx]
                if vals:
                    L.append(f"- {modelo}, {'con' if idx == '1' else 'sin'} índices: mediana {statistics.median(vals):.1f} ms, suma {sum(vals):.0f} ms en {len(vals)} consultas")
    if estr:
        L += ["", "## Estrategias de dbt", ""] + [f"- {e['estrategia']}: {e['segundos']} s, {e['filas_despues']} filas, {e['claves_duplicadas']} claves duplicadas" for e in estr]
    if tests:
        c = collections.Counter(t["estado"] for t in tests)
        L += ["", "## Tests de dbt", "", f"- {len(tests)} tests: {dict(c)}"]
        L += [f"- {t['test']}: {t['estado']}, {t['filas_fallidas']} filas" for t in tests if t["estado"] != "pass"]
    if runs:
        prog = [r for r in runs if r["tipo"] == "scheduled"]
        ok = [float(r["segundos"]) for r in prog if r["estado"] == "success" and r["segundos"]]
        L += ["", "## Airflow", "", f"- {len(prog)} runs programados, {len(ok)} con éxito; mediana {statistics.median(ok):.1f} s por run, suma {sum(ok):.0f} s" if ok else f"- {len(prog)} runs programados"]
        por_tarea = collections.defaultdict(list)
        for t in tareas:
            if t["estado"] == "success" and t["segundos"] and t["run_id"].startswith("scheduled"):
                por_tarea[t["tarea"]].append(float(t["segundos"]))
        L += [f"- {k}: mediana {statistics.median(v):.1f} s ({len(v)} ejecuciones)" for k, v in sorted(por_tarea.items())]
        for r in runs:
            if r["tipo"] != "scheduled":
                d = [t for t in tareas if t["run_id"] == r["run_id"] and t["tarea"] == "descargar"]
                L.append(f"- {r['run_id']}: run en {r['estado']} a los {float(r['segundos']):.0f} s, «descargar» con {d[0]['intentos'] if d else '?'} intento(s)")
    if avisos:
        L += ["- registro: " + ", ".join(f"{a['n']} {a['evento']}" for a in avisos)]
    idem = leer_csv("idempotencia.csv")
    if idem:
        L += ["", "## Idempotencia (octubre de 2026 cargado dos veces)", ""] + [f"- {i['objeto']}: {i['antes'][:12]} → {i['despues'][:12]}" + (f" ({'igual' if i.get('igual') == 'sí' else 'DISTINTO'})" if i.get("igual") else "") for i in idem]
    planes = leer_csv("planes.csv")
    if planes:
        L += ["", "## Planes de la consulta 2 (los diez más vistos de un mes)", ""]
        L += [f"- {p['modelo']}, {'con' if p['indices'] == '1' else 'sin'} índices: {p['ms_ejecucion']} ms, raíz {p['nodo_raiz']}, peor estimación en {p['nodo_peor_estimado']} ({p['relacion']}): {p['filas_estimadas']} filas estimadas frente a {p['filas_reales']} reales, {p['bloques_compartidos']} bloques" for p in planes]
    snap = leer_csv("snapshot.csv")
    if snap:
        d = {x["metrica"]: x["valor"] for x in snap}
        L += ["", "## Dimensión con historia (snapshot de dbt)", "",
              f"- {d['versiones']} versiones de {d['articulos']} artículos, {d['versiones_vigentes']} vigentes; dbt_valid_from entre {d['dbt_valid_from_min']} y {d['dbt_valid_from_max']} ({d['minutos_entre_observaciones']} minutos: hora de observación); fecha_datos con {d['fechas_de_negocio_distintas']} valores, de {d['fecha_datos_min']} a {d['fecha_datos_max']} (fecha de negocio)"]
        ej = leer_csv("snapshot_ejemplo.csv")
        if ej:
            L.append(f"- artículo con más versiones: {len(ej)} (" + " → ".join(f"{e['tramo']} desde {e['fecha_datos']}" for e in ej) + ")")
    rk = leer_csv("ranking_oficial.csv")
    if rk:
        med = lambda k: statistics.median(float(f[k]) for f in rk if f[k] != "")
        L += ["", "## Ranking mensual derivado frente a la lista mensual oficial (all-access)", "",
              f"- {len(rk)} meses; coincidencias, mediana: top 10 {med('coincidencias_10'):.0f}, top 100 {med('coincidencias_100'):.0f}, top 1000 {med('coincidencias_1000'):.0f}; artículos del top 1000 oficial ausentes del derivado, mediana {med('ausentes_en_derivado'):.0f}; cociente visitas derivadas/oficiales en el top 100: mediana por artículo {med('mediana_cociente_visitas_top100'):.3f}, suma sobre suma {med('cociente_agregado_visitas_top100'):.3f}"]
    if fases:
        L += ["", "## Esfuerzo", "", f"- `init` en {fases[-1]['segundos_acumulados']} s: " + "; ".join(f"{f['fase']} a los {f['segundos_acumulados']} s" for f in fases)]
    if config:
        L.append(f"- {sum(f['lineas'] for f in config)} líneas de configuración, modelos y guiones en {len(config)} ficheros, sin comentarios ni líneas en blanco")
    if imgs:
        L.append("- imágenes: " + "; ".join(f"{f['imagen']} {f['tamano']}" for f in imgs))
    if recs:
        L.append("- memoria en reposo: " + "; ".join(f"{f['contenedor']} {f['memoria']}" for f in recs))
    with open(os.path.join(SALIDA, "INSTANTANEA.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    instantanea(avisos_airflow(), esfuerzo(), configuracion(), imagenes(), recursos())
