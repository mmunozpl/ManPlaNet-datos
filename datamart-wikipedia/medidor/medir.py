#!/usr/bin/env python3
"""Banco de pruebas del DataMart. Corre dentro del servicio ``medidor`` del
compose, con la plataforma ya cargada por el DAG, y escribe los CSV en el
directorio de la medición (montado en /salida).

Bloques:
  1. cargas: COPY, INSERT por lotes, INSERT multifila y upsert sobre la
     misma tabla y las mismas filas (un año de la zona preparada);
  2. consultas: diez preguntas de BI sobre tres modelos (plano, estrella y
     copo de nieve), con y sin índices, mediana de cinco repeticiones;
  3. estrategias incrementales de dbt (append, delete+insert, merge) sobre
     la ventana de tres días que cada carga reprocesa, y el coste de una
     reconstrucción completa;
  4. tests de dbt: qué pasa, qué avisa y qué falla, con sus filas;
  5. Airflow: duración de cada run y tarea del relleno histórico, y dos runs
     con fallo simulado, uno que el reintento recupera y otro que agota los
     reintentos y dispara el aviso;
  6. tamaños: filas y octetos de cada tabla y de cada zona del S3;
  7. planes: EXPLAIN (ANALYZE, BUFFERS) de la consulta de los diez más
     vistos sobre la estrella y el copo, con y sin índices;
  8. snapshot: qué fechas guarda la dimensión con historia (la hora de
     observación de dbt frente a la fecha de negocio de los datos);
  9. ranking: el ranking mensual derivado de las listas diarias frente a la
     lista mensual oficial de la API (all-days);
 10. idempotencia: las tablas antes y después de repetir una carga mensual
     entera (los runs con fallo simulado reprocesan octubre de 2026).
"""
import collections
import csv
import datetime as dt
import io
import json
import os
import statistics
import subprocess
import time
import urllib.error
import urllib.request

import boto3
import psycopg
import pyarrow.csv as pcsv
import pyarrow.parquet as pq
from botocore.config import Config

SALIDA = "/salida"
DSN = os.environ["DATAMART_DSN"]
ADMIN = os.environ["ADMIN_DSN"]
AF = os.environ["AIRFLOW_URL"]
PROYECTO_DBT = "/opt/proyecto-dbt"
DESTINO_DBT = "/tmp/dbt-destino"
ANIO_CARGA = int(os.environ.get("ANIO_CARGA", "2025"))  # el año del banco de cargas
PRUEBAS: list[dict] = []
ANTES: dict[str, int] = {}  # filas de las tablas al empezar, para la idempotencia
CACHE = "/cache"


# ---------------------------------------------------------------- utilidades
def ahora() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def anota(bloque: str, prueba: str, resultado: str, ms: float, detalle: str = "") -> None:
    fila = dict(instante=ahora(), bloque=bloque, prueba=prueba, resultado=resultado,
                ms=round(ms), detalle=" ".join(str(detalle).split())[:300])
    PRUEBAS.append(fila)
    print(f"[{bloque}] {prueba}: {resultado} ({fila['ms']} ms) {fila['detalle'][:120]}", flush=True)


def escribir_csv(nombre: str, filas: list[dict], campos: list[str]) -> None:
    with open(os.path.join(SALIDA, nombre), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader(); w.writerows(filas)


def cronometro():
    t0 = time.perf_counter()
    return lambda: (time.perf_counter() - t0) * 1000


def s3():
    return boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"],
                        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
                        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
                        region_name="us-east-1", config=Config(s3={"addressing_style": "path"}))


def dbt(*args: str, estrategia: str = "delete+insert") -> tuple[int, float, str]:
    """Ejecuta dbt contra el proyecto montado y devuelve (código, segundos,
    salida)."""
    env = dict(os.environ, DBT_PROFILES_DIR=PROYECTO_DBT)
    orden = ["dbt", *args, "--profiles-dir", PROYECTO_DBT, "--project-dir", PROYECTO_DBT,
             "--target-path", f"{DESTINO_DBT}/target", "--log-path", f"{DESTINO_DBT}/logs",
             "--vars", json.dumps({"estrategia": estrategia})]
    t0 = time.perf_counter()
    r = subprocess.run(orden, capture_output=True, text=True, env=env, timeout=3600)
    return r.returncode, time.perf_counter() - t0, r.stdout + r.stderr


def resumen_dbt(salida: str) -> str:
    """la línea «Done. PASS=…» de dbt, o el final de su salida."""
    lineas = [l for l in salida.splitlines() if "Done. PASS=" in l or "Completed with" in l]
    return lineas[-1].strip() if lineas else salida[-200:]


def consulta(con, sql: str, params=None):
    with con.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else None


# --------------------------------------------------------------- 1. cargas
def filas_del_anio(anio: int):
    """Las filas de un año de la zona preparada, como tabla pyarrow."""
    import pyarrow as pa
    c = s3(); bucket = os.environ["S3_BUCKET"]
    tablas = []
    pref = f"preparado/es.wikipedia/"
    r = c.list_objects_v2(Bucket=bucket, Prefix=pref)
    claves = [o["Key"] for o in r.get("Contents", []) if f"anio={anio}" in o["Key"]]
    while r.get("IsTruncated"):
        r = c.list_objects_v2(Bucket=bucket, Prefix=pref, ContinuationToken=r["NextContinuationToken"])
        claves += [o["Key"] for o in r.get("Contents", []) if f"anio={anio}" in o["Key"]]
    for k in sorted(claves):
        tablas.append(pq.read_table(io.BytesIO(c.get_object(Bucket=bucket, Key=k)["Body"].read())))
    return pa.concat_tables(tablas)


def bloque_cargas() -> None:
    b = "cargas"
    tabla = filas_del_anio(ANIO_CARGA)
    n = tabla.num_rows
    filas = tabla.to_pylist()
    buf = io.BytesIO(); pcsv.write_csv(tabla, buf, pcsv.WriteOptions(include_header=False)); csv_bytes = buf.getvalue()
    resultados = []
    with psycopg.connect(DSN, autocommit=False) as con:
        def preparar_tabla(con_indice: bool):
            consulta(con, "DROP TABLE IF EXISTS banco.carga")
            consulta(con, "CREATE TABLE banco.carga (LIKE crudo.visualizaciones_top INCLUDING DEFAULTS)")
            if con_indice:
                consulta(con, "CREATE UNIQUE INDEX IF NOT EXISTS carga_clave ON banco.carga (fecha, acceso, articulo)")
            con.commit()
        # COPY
        preparar_tabla(False); ms = cronometro()
        with con.cursor() as cur:
            with cur.copy("COPY banco.carga (proyecto, acceso, fecha, articulo, visitas, posicion) FROM STDIN WITH (FORMAT csv)") as cp:
                cp.write(csv_bytes)
        con.commit(); t = ms()
        resultados.append(dict(metodo="COPY desde CSV", filas=n, ms=round(t), filas_por_s=round(n / t * 1000)))
        anota(b, "COPY desde CSV", f"{n} filas", t)
        # INSERT por lotes (executemany de 1.000)
        preparar_tabla(False); ms = cronometro()
        with con.cursor() as cur:
            sql = "INSERT INTO banco.carga (proyecto, acceso, fecha, articulo, visitas, posicion) VALUES (%s, %s, %s, %s, %s, %s)"
            lote = [(r["proyecto"], r["acceso"], r["fecha"], r["articulo"], r["visitas"], r["posicion"]) for r in filas]
            for i in range(0, n, 1000):
                cur.executemany(sql, lote[i:i + 1000])
        con.commit(); t = ms()
        resultados.append(dict(metodo="INSERT por lotes de 1.000 (executemany)", filas=n, ms=round(t), filas_por_s=round(n / t * 1000)))
        anota(b, "INSERT por lotes de 1.000", f"{n} filas", t)
        # INSERT multifila (1.000 filas por sentencia)
        preparar_tabla(False); ms = cronometro()
        with con.cursor() as cur:
            for i in range(0, n, 1000):
                trozo = lote[i:i + 1000]
                marcas = ",".join(["(%s,%s,%s,%s,%s,%s)"] * len(trozo))
                cur.execute("INSERT INTO banco.carga (proyecto, acceso, fecha, articulo, visitas, posicion) VALUES " + marcas,
                            [v for fila in trozo for v in fila])
        con.commit(); t = ms()
        resultados.append(dict(metodo="INSERT multifila de 1.000", filas=n, ms=round(t), filas_por_s=round(n / t * 1000)))
        anota(b, "INSERT multifila de 1.000", f"{n} filas", t)
        # upsert sobre la tabla ya llena (todas las filas chocan): ON CONFLICT DO UPDATE
        preparar_tabla(True)
        with con.cursor() as cur:
            with cur.copy("COPY banco.carga (proyecto, acceso, fecha, articulo, visitas, posicion) FROM STDIN WITH (FORMAT csv)") as cp:
                cp.write(csv_bytes)
        con.commit(); ms = cronometro()
        with con.cursor() as cur:
            for i in range(0, n, 1000):
                trozo = lote[i:i + 1000]
                marcas = ",".join(["(%s,%s,%s,%s,%s,%s)"] * len(trozo))
                cur.execute("INSERT INTO banco.carga (proyecto, acceso, fecha, articulo, visitas, posicion) VALUES " + marcas +
                            " ON CONFLICT (fecha, acceso, articulo) DO UPDATE SET visitas = EXCLUDED.visitas, posicion = EXCLUDED.posicion",
                            [v for fila in trozo for v in fila])
        con.commit(); t = ms()
        resultados.append(dict(metodo="upsert multifila (ON CONFLICT DO UPDATE), todas chocan", filas=n, ms=round(t), filas_por_s=round(n / t * 1000)))
        anota(b, "upsert ON CONFLICT, todas las filas chocan", f"{n} filas", t)
        # COPY con el índice único presente
        preparar_tabla(True); ms = cronometro()
        with con.cursor() as cur:
            with cur.copy("COPY banco.carga (proyecto, acceso, fecha, articulo, visitas, posicion) FROM STDIN WITH (FORMAT csv)") as cp:
                cp.write(csv_bytes)
        con.commit(); t = ms()
        resultados.append(dict(metodo="COPY con índice único ya creado", filas=n, ms=round(t), filas_por_s=round(n / t * 1000)))
        anota(b, "COPY con índice único", f"{n} filas", t)
        consulta(con, "DROP TABLE IF EXISTS banco.carga"); con.commit()
    escribir_csv("cargas.csv", resultados, ["metodo", "filas", "ms", "filas_por_s"])


# ------------------------------------------------------------ 2. consultas
MODELOS_SQL = {
    # el modelo plano: una tabla ancha con todo desnormalizado
    "plano": """
        CREATE TABLE banco.plano AS
        SELECT f.fecha, f.anio, f.mes, f.anio_mes, f.nombre_dia, f.es_fin_de_semana,
               a.acceso, a.canal, a.es_agregado,
               ar.titulo, ar.espacio_nombres, ar.es_articulo,
               h.visitas, h.posicion
        FROM marts.hechos_visualizaciones h
        JOIN marts.dim_fecha f ON f.fecha_id = h.fecha_id
        JOIN marts.dim_acceso a ON a.acceso_id = h.acceso_id
        JOIN marts.dim_articulo ar ON ar.articulo_id = h.articulo_id""",
    # el copo de nieve: las dimensiones normalizadas en tablas enlazadas
    "copo": """
        CREATE TABLE banco.copo_meses AS SELECT DISTINCT anio_mes, anio, mes, nombre_mes, trimestre FROM marts.dim_fecha;
        CREATE TABLE banco.copo_fechas AS SELECT fecha_id, fecha, anio_mes, dia, dia_semana_iso, nombre_dia, es_fin_de_semana, semana_iso FROM marts.dim_fecha;
        CREATE TABLE banco.copo_espacios AS SELECT row_number() OVER (ORDER BY espacio_nombres) AS espacio_id, espacio_nombres, bool_or(es_articulo) AS es_articulo FROM marts.dim_articulo GROUP BY espacio_nombres;
        CREATE TABLE banco.copo_articulos AS SELECT ar.articulo_id, ar.titulo, e.espacio_id, ar.primera_fecha_vista, ar.ultima_fecha_vista FROM marts.dim_articulo ar JOIN banco.copo_espacios e ON e.espacio_nombres = ar.espacio_nombres;
        CREATE TABLE banco.copo_canales AS SELECT row_number() OVER (ORDER BY canal) AS canal_id, canal FROM (SELECT DISTINCT canal FROM marts.dim_acceso) c;
        CREATE TABLE banco.copo_accesos AS SELECT a.acceso_id, a.acceso, c.canal_id, a.es_agregado FROM marts.dim_acceso a JOIN banco.copo_canales c ON c.canal = a.canal;
        CREATE TABLE banco.copo_hechos AS SELECT * FROM marts.hechos_visualizaciones""",
}
INDICES = {
    "plano": ["CREATE INDEX IF NOT EXISTS plano_fecha ON banco.plano (fecha)", "CREATE INDEX IF NOT EXISTS plano_titulo ON banco.plano (titulo)",
              "CREATE INDEX IF NOT EXISTS plano_acceso ON banco.plano (acceso, fecha)"],
    "copo": ["CREATE INDEX IF NOT EXISTS copo_hechos_fecha ON banco.copo_hechos (fecha_id)", "CREATE INDEX IF NOT EXISTS copo_hechos_art ON banco.copo_hechos (articulo_id)",
             "CREATE INDEX IF NOT EXISTS copo_hechos_acc ON banco.copo_hechos (acceso_id, fecha_id)", "CREATE UNIQUE INDEX IF NOT EXISTS copo_fechas_id ON banco.copo_fechas (fecha_id)",
             "CREATE UNIQUE INDEX IF NOT EXISTS copo_art_id ON banco.copo_articulos (articulo_id)"],
    "estrella": ["CREATE INDEX IF NOT EXISTS hv_fecha ON marts.hechos_visualizaciones (fecha_id)", "CREATE INDEX IF NOT EXISTS hv_art ON marts.hechos_visualizaciones (articulo_id)",
                 "CREATE INDEX IF NOT EXISTS hv_acc ON marts.hechos_visualizaciones (acceso_id, fecha_id)", "CREATE UNIQUE INDEX IF NOT EXISTS dim_fecha_id ON marts.dim_fecha (fecha_id)",
                 "CREATE UNIQUE INDEX IF NOT EXISTS dim_art_id ON marts.dim_articulo (articulo_id)"],
}
# las diez preguntas, en los tres modelos; {art} es un artículo que se fija al vuelo
CONSULTAS = {
    "1 visitas por mes (all-access)": dict(
        plano="SELECT anio_mes, sum(visitas) FROM banco.plano WHERE acceso = 'all-access' GROUP BY 1 ORDER BY 1",
        estrella="SELECT f.anio_mes, sum(h.visitas) FROM marts.hechos_visualizaciones h JOIN marts.dim_fecha f ON f.fecha_id = h.fecha_id JOIN marts.dim_acceso a ON a.acceso_id = h.acceso_id WHERE a.acceso = 'all-access' GROUP BY 1 ORDER BY 1",
        copo="SELECT m.anio_mes, sum(h.visitas) FROM banco.copo_hechos h JOIN banco.copo_fechas f ON f.fecha_id = h.fecha_id JOIN banco.copo_meses m ON m.anio_mes = f.anio_mes JOIN banco.copo_accesos a ON a.acceso_id = h.acceso_id WHERE a.acceso = 'all-access' GROUP BY 1 ORDER BY 1"),
    "2 los diez artículos más vistos de un mes": dict(
        plano="SELECT titulo, sum(visitas) v FROM banco.plano WHERE acceso = 'all-access' AND anio_mes = '2026-10' AND es_articulo GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
        estrella="SELECT ar.titulo, sum(h.visitas) v FROM marts.hechos_visualizaciones h JOIN marts.dim_fecha f ON f.fecha_id = h.fecha_id JOIN marts.dim_acceso a ON a.acceso_id = h.acceso_id JOIN marts.dim_articulo ar ON ar.articulo_id = h.articulo_id WHERE a.acceso = 'all-access' AND f.anio_mes = '2026-10' AND ar.es_articulo GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
        copo="SELECT ar.titulo, sum(h.visitas) v FROM banco.copo_hechos h JOIN banco.copo_fechas f ON f.fecha_id = h.fecha_id JOIN banco.copo_accesos a ON a.acceso_id = h.acceso_id JOIN banco.copo_articulos ar ON ar.articulo_id = h.articulo_id JOIN banco.copo_espacios e ON e.espacio_id = ar.espacio_id WHERE a.acceso = 'all-access' AND f.anio_mes = '2026-10' AND e.es_articulo GROUP BY 1 ORDER BY 2 DESC LIMIT 10"),
    "3 visitas por canal y día de la semana": dict(
        plano="SELECT canal, nombre_dia, sum(visitas) FROM banco.plano WHERE NOT es_agregado GROUP BY 1, 2 ORDER BY 1, 2",
        estrella="SELECT a.canal, f.nombre_dia, sum(h.visitas) FROM marts.hechos_visualizaciones h JOIN marts.dim_fecha f ON f.fecha_id = h.fecha_id JOIN marts.dim_acceso a ON a.acceso_id = h.acceso_id WHERE NOT a.es_agregado GROUP BY 1, 2 ORDER BY 1, 2",
        copo="SELECT c.canal, f.nombre_dia, sum(h.visitas) FROM banco.copo_hechos h JOIN banco.copo_fechas f ON f.fecha_id = h.fecha_id JOIN banco.copo_accesos a ON a.acceso_id = h.acceso_id JOIN banco.copo_canales c ON c.canal_id = a.canal_id WHERE NOT a.es_agregado GROUP BY 1, 2 ORDER BY 1, 2"),
    "4 cuota de páginas que no son artículos, por mes": dict(
        plano="SELECT anio_mes, sum(visitas) FILTER (WHERE NOT es_articulo)::float / sum(visitas) FROM banco.plano WHERE acceso = 'all-access' GROUP BY 1 ORDER BY 1",
        estrella="SELECT f.anio_mes, sum(h.visitas) FILTER (WHERE NOT ar.es_articulo)::float / sum(h.visitas) FROM marts.hechos_visualizaciones h JOIN marts.dim_fecha f ON f.fecha_id = h.fecha_id JOIN marts.dim_acceso a ON a.acceso_id = h.acceso_id JOIN marts.dim_articulo ar ON ar.articulo_id = h.articulo_id WHERE a.acceso = 'all-access' GROUP BY 1 ORDER BY 1",
        copo="SELECT m.anio_mes, sum(h.visitas) FILTER (WHERE NOT e.es_articulo)::float / sum(h.visitas) FROM banco.copo_hechos h JOIN banco.copo_fechas f ON f.fecha_id = h.fecha_id JOIN banco.copo_meses m ON m.anio_mes = f.anio_mes JOIN banco.copo_accesos a ON a.acceso_id = h.acceso_id JOIN banco.copo_articulos ar ON ar.articulo_id = h.articulo_id JOIN banco.copo_espacios e ON e.espacio_id = ar.espacio_id WHERE a.acceso = 'all-access' GROUP BY 1 ORDER BY 1"),
    "5 días en el top y visitas de un artículo": dict(
        plano="SELECT count(*), sum(visitas), min(fecha), max(fecha) FROM banco.plano WHERE acceso = 'all-access' AND titulo = '{art}'",
        estrella="SELECT count(*), sum(h.visitas), min(f.fecha), max(f.fecha) FROM marts.hechos_visualizaciones h JOIN marts.dim_fecha f ON f.fecha_id = h.fecha_id JOIN marts.dim_acceso a ON a.acceso_id = h.acceso_id JOIN marts.dim_articulo ar ON ar.articulo_id = h.articulo_id WHERE a.acceso = 'all-access' AND ar.titulo = '{art}'",
        copo="SELECT count(*), sum(h.visitas), min(f.fecha), max(f.fecha) FROM banco.copo_hechos h JOIN banco.copo_fechas f ON f.fecha_id = h.fecha_id JOIN banco.copo_accesos a ON a.acceso_id = h.acceso_id JOIN banco.copo_articulos ar ON ar.articulo_id = h.articulo_id WHERE a.acceso = 'all-access' AND ar.titulo = '{art}'"),
    "6 variación de un mes al anterior": dict(
        plano="WITH m AS (SELECT anio_mes, sum(visitas) v FROM banco.plano WHERE acceso = 'all-access' GROUP BY 1) SELECT anio_mes, v, v - lag(v) OVER (ORDER BY anio_mes) FROM m ORDER BY 1",
        estrella="WITH m AS (SELECT f.anio_mes, sum(h.visitas) v FROM marts.hechos_visualizaciones h JOIN marts.dim_fecha f ON f.fecha_id = h.fecha_id JOIN marts.dim_acceso a ON a.acceso_id = h.acceso_id WHERE a.acceso = 'all-access' GROUP BY 1) SELECT anio_mes, v, v - lag(v) OVER (ORDER BY anio_mes) FROM m ORDER BY 1",
        copo="WITH m AS (SELECT mm.anio_mes, sum(h.visitas) v FROM banco.copo_hechos h JOIN banco.copo_fechas f ON f.fecha_id = h.fecha_id JOIN banco.copo_meses mm ON mm.anio_mes = f.anio_mes JOIN banco.copo_accesos a ON a.acceso_id = h.acceso_id WHERE a.acceso = 'all-access' GROUP BY 1) SELECT anio_mes, v, v - lag(v) OVER (ORDER BY anio_mes) FROM m ORDER BY 1"),
    "7 fin de semana frente a laborable, por espacio de nombres": dict(
        plano="SELECT espacio_nombres, avg(visitas) FILTER (WHERE es_fin_de_semana) / avg(visitas) FILTER (WHERE NOT es_fin_de_semana) FROM banco.plano WHERE acceso = 'all-access' GROUP BY 1 ORDER BY 1",
        estrella="SELECT ar.espacio_nombres, avg(h.visitas) FILTER (WHERE f.es_fin_de_semana) / avg(h.visitas) FILTER (WHERE NOT f.es_fin_de_semana) FROM marts.hechos_visualizaciones h JOIN marts.dim_fecha f ON f.fecha_id = h.fecha_id JOIN marts.dim_acceso a ON a.acceso_id = h.acceso_id JOIN marts.dim_articulo ar ON ar.articulo_id = h.articulo_id WHERE a.acceso = 'all-access' GROUP BY 1 ORDER BY 1",
        copo="SELECT e.espacio_nombres, avg(h.visitas) FILTER (WHERE f.es_fin_de_semana) / avg(h.visitas) FILTER (WHERE NOT f.es_fin_de_semana) FROM banco.copo_hechos h JOIN banco.copo_fechas f ON f.fecha_id = h.fecha_id JOIN banco.copo_accesos a ON a.acceso_id = h.acceso_id JOIN banco.copo_articulos ar ON ar.articulo_id = h.articulo_id JOIN banco.copo_espacios e ON e.espacio_id = ar.espacio_id WHERE a.acceso = 'all-access' GROUP BY 1 ORDER BY 1"),
    "8 posición diaria de un artículo en un mes": dict(
        plano="SELECT fecha, posicion, visitas FROM banco.plano WHERE acceso = 'all-access' AND titulo = '{art}' AND anio_mes = '2026-10' ORDER BY 1",
        estrella="SELECT f.fecha, h.posicion, h.visitas FROM marts.hechos_visualizaciones h JOIN marts.dim_fecha f ON f.fecha_id = h.fecha_id JOIN marts.dim_acceso a ON a.acceso_id = h.acceso_id JOIN marts.dim_articulo ar ON ar.articulo_id = h.articulo_id WHERE a.acceso = 'all-access' AND ar.titulo = '{art}' AND f.anio_mes = '2026-10' ORDER BY 1",
        copo="SELECT f.fecha, h.posicion, h.visitas FROM banco.copo_hechos h JOIN banco.copo_fechas f ON f.fecha_id = h.fecha_id JOIN banco.copo_accesos a ON a.acceso_id = h.acceso_id JOIN banco.copo_articulos ar ON ar.articulo_id = h.articulo_id WHERE a.acceso = 'all-access' AND ar.titulo = '{art}' AND f.anio_mes = '2026-10' ORDER BY 1"),
    "9 artículos distintos en el top por mes": dict(
        plano="SELECT anio_mes, count(DISTINCT titulo) FROM banco.plano WHERE acceso = 'all-access' GROUP BY 1 ORDER BY 1",
        estrella="SELECT f.anio_mes, count(DISTINCT h.articulo_id) FROM marts.hechos_visualizaciones h JOIN marts.dim_fecha f ON f.fecha_id = h.fecha_id JOIN marts.dim_acceso a ON a.acceso_id = h.acceso_id WHERE a.acceso = 'all-access' GROUP BY 1 ORDER BY 1",
        copo="SELECT m.anio_mes, count(DISTINCT h.articulo_id) FROM banco.copo_hechos h JOIN banco.copo_fechas f ON f.fecha_id = h.fecha_id JOIN banco.copo_meses m ON m.anio_mes = f.anio_mes JOIN banco.copo_accesos a ON a.acceso_id = h.acceso_id WHERE a.acceso = 'all-access' GROUP BY 1 ORDER BY 1"),
    "10 cuota de la portada sobre el total diario": dict(
        plano="SELECT fecha, sum(visitas) FILTER (WHERE titulo = 'Wikipedia:Portada')::float / sum(visitas) FROM banco.plano WHERE acceso = 'all-access' GROUP BY 1 ORDER BY 1",
        estrella="SELECT f.fecha, sum(h.visitas) FILTER (WHERE ar.titulo = 'Wikipedia:Portada')::float / sum(h.visitas) FROM marts.hechos_visualizaciones h JOIN marts.dim_fecha f ON f.fecha_id = h.fecha_id JOIN marts.dim_acceso a ON a.acceso_id = h.acceso_id JOIN marts.dim_articulo ar ON ar.articulo_id = h.articulo_id WHERE a.acceso = 'all-access' GROUP BY 1 ORDER BY 1",
        copo="SELECT f.fecha, sum(h.visitas) FILTER (WHERE ar.titulo = 'Wikipedia:Portada')::float / sum(h.visitas) FROM banco.copo_hechos h JOIN banco.copo_fechas f ON f.fecha_id = h.fecha_id JOIN banco.copo_accesos a ON a.acceso_id = h.acceso_id JOIN banco.copo_articulos ar ON ar.articulo_id = h.articulo_id WHERE a.acceso = 'all-access' GROUP BY 1 ORDER BY 1"),
}


PLANES: list[dict] = []


def resumir_plan(plan, modelo: str, indices: int, fichero: str) -> dict:
    """Lo que un EXPLAIN ANALYZE dice en una fila: tiempos, nodo raíz, el nodo
    con la peor estimación de filas (la razón habitual de un mal plan) y los
    bloques compartidos tocados."""
    raiz = plan[0]["Plan"]
    peor = dict(nodo="", relacion="", est=0, real=0, razon=0.0)
    def tablas(n):
        t = [n["Relation Name"]] if n.get("Relation Name") else []
        for h in n.get("Plans", []):
            t += tablas(h)
        return t
    def recorrer(n):
        nonlocal peor
        for h in n.get("Plans", []):   # primero los hijos: el error nace abajo
            recorrer(h)
        tipo = n.get("Node Type", "")
        # solo los nodos de acceso y de unión: Limit, Sort y Aggregate
        # recortan filas por diseño y no son estimaciones erradas. Las filas
        # se comparan por bucle, que es como las estima el planificador
        if "Scan" in tipo or "Join" in tipo or tipo == "Nested Loop":
            est, real = n.get("Plan Rows", 0), n.get("Actual Rows", 0)
            razon = max(est, 1) / max(real, 1) if real <= est else max(real, 1) / max(est, 1)
            if razon > peor["razon"]:
                peor = dict(nodo=tipo, relacion=n.get("Relation Name") or " ⋈ ".join(tablas(n)) or n.get("Index Name") or "", est=est, real=real, razon=razon)
    recorrer(raiz)
    return dict(modelo=modelo, indices=indices, fichero=f"planes/{fichero}",
                ms_ejecucion=round(plan[0].get("Execution Time", 0), 1), ms_planificacion=round(plan[0].get("Planning Time", 0), 1),
                nodo_raiz=raiz.get("Node Type", ""), nodo_peor_estimado=peor["nodo"], relacion=peor["relacion"],
                filas_estimadas=peor["est"], filas_reales=peor["real"],
                bloques_compartidos=raiz.get("Shared Hit Blocks", 0) + raiz.get("Shared Read Blocks", 0),
                bloques_disco=raiz.get("Shared Read Blocks", 0))


def indices_existentes(con, esquema: str, tablas: tuple[str, ...]) -> list[str]:
    """los índices de esas tablas, menos las claves primarias; dbt los nombra
    con un hash, así que se buscan por tabla y no por nombre."""
    return [r[0] for r in consulta(con, "SELECT indexname FROM pg_indexes WHERE schemaname = %s AND tablename = ANY(%s) "
                                        "AND indexname NOT LIKE '%%_pkey'", (esquema, list(tablas)))]


def bloque_consultas() -> None:
    b = "consultas"
    resultados = []
    with psycopg.connect(DSN, autocommit=True) as con:
        # un artículo real para las consultas 5 y 8: el tercero más visto de 2026-10 que sea artículo
        art = consulta(con, """SELECT ar.titulo FROM marts.hechos_visualizaciones h JOIN marts.dim_fecha f ON f.fecha_id = h.fecha_id
                               JOIN marts.dim_acceso a ON a.acceso_id = h.acceso_id JOIN marts.dim_articulo ar ON ar.articulo_id = h.articulo_id
                               WHERE a.acceso = 'all-access' AND f.anio_mes = '2026-10' AND ar.es_articulo GROUP BY 1 ORDER BY sum(h.visitas) DESC OFFSET 2 LIMIT 1""")[0][0]
        anota(b, "artículo de referencia para las consultas 5 y 8", art, 0)
        # los modelos de comparación se construyen desde la estrella
        for m in ("plano", "copo"):
            for tabla in consulta(con, "SELECT tablename FROM pg_tables WHERE schemaname = 'banco'") or []:
                consulta(con, f"DROP TABLE IF EXISTS banco.{tabla[0]} CASCADE")
            break
        ms = cronometro(); consulta(con, MODELOS_SQL["plano"]); anota(b, "construir el modelo plano", "hecho", ms())
        ms = cronometro(); consulta(con, MODELOS_SQL["copo"]); anota(b, "construir el copo de nieve", "hecho", ms())
        # los índices de la estrella los creó dbt: se quitan para la pasada sin índices y se reponen
        idx_estrella = indices_existentes(con, "marts", ("hechos_visualizaciones", "dim_fecha", "dim_articulo", "dim_acceso"))
        for i in idx_estrella:
            consulta(con, f'DROP INDEX IF EXISTS marts."{i}"')
        anota(b, "índices de la estrella retirados para la pasada sin índices", f"{len(idx_estrella)} índices", 0, " ".join(idx_estrella))
        consulta(con, "ANALYZE")
        tamanos = {m: consulta(con, "SELECT pg_total_relation_size(%s)", (t,))[0][0] for m, t in
                   (("plano", "banco.plano"), ("copo", "banco.copo_hechos"), ("estrella", "marts.hechos_visualizaciones"))}
        for con_indices in (False, True):
            if con_indices:
                for m, sqls in INDICES.items():
                    for s in sqls:
                        consulta(con, s)
                consulta(con, "ANALYZE")
            for nombre, variantes in CONSULTAS.items():
                for modelo in ("plano", "estrella", "copo"):
                    sql = variantes[modelo].replace("{art}", art.replace("'", "''"))
                    consulta(con, sql)  # calentamiento
                    tiempos = []
                    for _ in range(5):
                        ms = cronometro(); filas = consulta(con, sql); tiempos.append(ms())
                    mediana = statistics.median(tiempos)
                    resultados.append(dict(consulta=nombre, modelo=modelo, indices=int(con_indices), ms=round(mediana, 1),
                                           filas=len(filas or []), octetos_modelo=tamanos[modelo]))
                    anota(b, f"{nombre} · {modelo} · {'con' if con_indices else 'sin'} índices", f"{len(filas or [])} filas", mediana)
            # el plan de la consulta 2 (los diez más vistos de un mes) en la estrella y el copo
            for modelo in ("estrella", "copo"):
                sql = CONSULTAS["2 los diez artículos más vistos de un mes"][modelo].replace("{art}", art.replace("'", "''"))
                plan = consulta(con, "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql)[0][0]
                plan = plan if isinstance(plan, (list, dict)) else json.loads(plan)
                os.makedirs(os.path.join(SALIDA, "planes"), exist_ok=True)
                nombre_plan = f"consulta2_{modelo}_{'con' if con_indices else 'sin'}_indices.json"
                with open(os.path.join(SALIDA, "planes", nombre_plan), "w") as f:
                    json.dump(plan, f, ensure_ascii=False, indent=1)
                PLANES.append(resumir_plan(plan, modelo, int(con_indices), nombre_plan))
        escribir_csv("planes.csv", PLANES, ["modelo", "indices", "fichero", "ms_ejecucion", "ms_planificacion", "nodo_raiz",
                                            "nodo_peor_estimado", "relacion", "filas_estimadas", "filas_reales", "bloques_compartidos", "bloques_disco"])
        for pl in PLANES:
            anota("planes", f"consulta 2 · {pl['modelo']} · {'con' if pl['indices'] else 'sin'} índices",
                  f"{pl['ms_ejecucion']} ms, peor estimación en {pl['nodo_peor_estimado']} ({pl['relacion']}): {pl['filas_estimadas']} estimadas frente a {pl['filas_reales']} reales", pl["ms_ejecucion"])
        # los modelos de comparación se retiran: el banco deja la base como la encontró
        for tabla in consulta(con, "SELECT tablename FROM pg_tables WHERE schemaname = 'banco'") or []:
            consulta(con, f"DROP TABLE IF EXISTS banco.{tabla[0]} CASCADE")
    escribir_csv("consultas.csv", resultados, ["consulta", "modelo", "indices", "ms", "filas", "octetos_modelo"])


# -------------------------------------------------- 3. estrategias de dbt
def bloque_estrategias() -> None:
    b = "estrategias dbt"
    resultados = []
    with psycopg.connect(DSN, autocommit=True) as con:
        n_antes = consulta(con, "SELECT count(*) FROM marts.hechos_visualizaciones")[0][0]
    for estrategia in ("delete+insert", "merge", "append"):
        cod, seg, salida = dbt("run", "--select", "hechos_visualizaciones", estrategia=estrategia)
        with psycopg.connect(DSN, autocommit=True) as con:
            n = consulta(con, "SELECT count(*) FROM marts.hechos_visualizaciones")[0][0]
            dup = consulta(con, "SELECT count(*) FROM (SELECT fecha_id, articulo_id, acceso_id FROM marts.hechos_visualizaciones GROUP BY 1, 2, 3 HAVING count(*) > 1) d")[0][0]
        resultados.append(dict(estrategia=estrategia, codigo=cod, segundos=round(seg, 1), filas_despues=n, claves_duplicadas=dup))
        anota(b, f"run incremental con {estrategia} (ventana de 3 días)", f"código {cod}, {n} filas, {dup} claves duplicadas", seg * 1000, resumen_dbt(salida))
    # se deja la tabla limpia con delete+insert y se mide la reconstrucción completa
    cod, seg, salida = dbt("run", "--full-refresh", estrategia="delete+insert")
    resultados.append(dict(estrategia="reconstrucción completa (--full-refresh, todos los modelos)", codigo=cod, segundos=round(seg, 1), filas_despues=n_antes, claves_duplicadas=0))
    anota(b, "reconstrucción completa de todos los modelos", f"código {cod}", seg * 1000, resumen_dbt(salida))
    cod, seg, salida = dbt("run", estrategia="delete+insert")
    resultados.append(dict(estrategia="run incremental de todos los modelos (sin datos nuevos)", codigo=cod, segundos=round(seg, 1), filas_despues=n_antes, claves_duplicadas=0))
    anota(b, "run incremental de todos los modelos, sin datos nuevos", f"código {cod}", seg * 1000)
    escribir_csv("estrategias.csv", resultados, ["estrategia", "codigo", "segundos", "filas_despues", "claves_duplicadas"])


# ------------------------------------------------------------ 4. tests dbt
def bloque_tests() -> None:
    b = "tests dbt"
    cod, seg, salida = dbt("test")
    anota(b, "dbt test", f"código {cod}", seg * 1000)
    filas = []
    try:
        rr = json.load(open(f"{DESTINO_DBT}/target/run_results.json"))
        for r in rr["results"]:
            filas.append(dict(test=r["unique_id"].split(".")[-1] if r["unique_id"].count(".") < 3 else r["unique_id"].split(".")[2],
                              estado=r["status"], filas_fallidas=r.get("failures") or 0,
                              segundos=round(r.get("execution_time", 0), 2)))
    except Exception as e:
        anota(b, "leer run_results.json", "no", 0, str(e))
    escribir_csv("tests_dbt.csv", filas, ["test", "estado", "filas_fallidas", "segundos"])
    est = {}
    for f in filas:
        est[f["estado"]] = est.get(f["estado"], 0) + 1
    anota(b, "resultado de los tests", json.dumps(est), 0)


# -------------------------------------------------------------- 5. Airflow
def af_token() -> str:
    datos = json.dumps({"username": os.environ["AIRFLOW_USUARIO"], "password": os.environ["AIRFLOW_CONTRASENA"]}).encode()
    req = urllib.request.Request(f"{AF}/auth/token", data=datos, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]


def af(ruta: str, datos=None, metodo=None, token=None):
    req = urllib.request.Request(f"{AF}/api/v2/{ruta}", data=None if datos is None else json.dumps(datos).encode(),
                                 method=metodo or ("POST" if datos is not None else "GET"))
    req.add_header("Authorization", f"Bearer {token}"); req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def bloque_airflow() -> None:
    b = "Airflow"
    tok = af_token()
    cod, runs = af("dags/visualizaciones_mensual/dagRuns?limit=200&order_by=logical_date", token=tok)
    filas_runs, filas_tareas = [], []
    for r in (runs or {}).get("dag_runs", []):
        ini, fin = r.get("start_date"), r.get("end_date")
        dur = (dt.datetime.fromisoformat(fin) - dt.datetime.fromisoformat(ini)).total_seconds() if ini and fin else None
        filas_runs.append(dict(run_id=r["dag_run_id"], mes=(r.get("data_interval_start") or "")[:7], estado=r["state"], tipo=r.get("run_type"),
                               inicio=ini, fin=fin, segundos=round(dur, 1) if dur else ""))
        c2, tis = af(f"dags/visualizaciones_mensual/dagRuns/{r['dag_run_id']}/taskInstances?limit=100", token=tok)
        for t in (tis or {}).get("task_instances", []):
            filas_tareas.append(dict(run_id=r["dag_run_id"], mes=(r.get("data_interval_start") or "")[:7], tarea=t["task_id"], estado=t["state"],
                                     intentos=t.get("try_number"), segundos=round(t.get("duration") or 0, 1)))
    escribir_csv("runs_airflow.csv", filas_runs, ["run_id", "mes", "estado", "tipo", "inicio", "fin", "segundos"])
    escribir_csv("tareas_airflow.csv", filas_tareas, ["run_id", "mes", "tarea", "estado", "intentos", "segundos"])
    ok = sum(1 for r in filas_runs if r["estado"] == "success")
    anota(b, "runs del relleno histórico", f"{len(filas_runs)} runs, {ok} con éxito", 0)
    # dos runs con fallo simulado en la primera tarea: con un fallo, el
    # reintento recupera el run; con cuatro, la tarea agota sus tres
    # reintentos, el run falla y salta el aviso en su registro. Vuelven a
    # procesar octubre de 2026 (el intervalo se da explícito); la fecha
    # lógica tiene que ser única por DAG, así que no puede ser la del run
    # programado de ese mes
    avisos = collections.Counter()
    for n_fallos, esperado, dia in ((1, "success", 15), (4, "failed", 16)):
        ms = cronometro()
        run_id = f"fallos_simulados_{n_fallos}"
        cod, resp = af("dags/visualizaciones_mensual/dagRuns",
                       {"dag_run_id": run_id, "logical_date": f"2026-10-{dia}T00:00:00Z",
                        "data_interval_start": "2026-10-01T00:00:00Z", "data_interval_end": "2026-11-01T00:00:00Z",
                        "conf": {"fallos_simulados": n_fallos}}, token=tok)
        if cod not in (200, 201):
            anota(b, f"run con {n_fallos} fallo(s) simulado(s)", f"HTTP {cod}", ms(), json.dumps(resp)[:200]); continue
        estado = resp.get("state")
        for _ in range(360):
            time.sleep(5)
            c, r = af(f"dags/visualizaciones_mensual/dagRuns/{run_id}", token=tok)
            estado = (r or {}).get("state")
            if estado in ("success", "failed"):
                break
        mes = ((r or {}).get("data_interval_start") or "")[:7]
        filas_runs.append(dict(run_id=run_id, mes=mes, estado=estado, tipo="manual", inicio=(r or {}).get("start_date"),
                               fin=(r or {}).get("end_date"), segundos=round(ms() / 1000, 1)))
        c, tis = af(f"dags/visualizaciones_mensual/dagRuns/{run_id}/taskInstances?limit=100", token=tok)
        desc = [t for t in (tis or {}).get("task_instances", []) if t["task_id"] == "descargar"]
        intentos = desc[0].get("try_number") if desc else None
        for t in (tis or {}).get("task_instances", []):
            filas_tareas.append(dict(run_id=run_id, mes=mes, tarea=t["task_id"], estado=t["state"], intentos=t.get("try_number"),
                                     segundos=round(t.get("duration") or 0, 1)))
        # el registro de cada intento de «descargar», por la API: ahí quedan
        # el fallo simulado, el aviso de reintento y el aviso definitivo
        for intento in range(1, (intentos or 0) + 1):
            c, log = af(f"dags/visualizaciones_mensual/dagRuns/{run_id}/taskInstances/descargar/logs/{intento}", token=tok)
            texto = json.dumps(log, ensure_ascii=False)
            avisos["fallo simulado"] += texto.count("fallo simulado en el intento")
            avisos["aviso de fallo definitivo"] += texto.count("AVISO: la tarea")
        anota(b, f"run con {n_fallos} fallo(s) simulado(s) en «descargar»", f"estado {estado}, {intentos} intento(s) de la tarea",
              ms(), "como se esperaba" if estado == esperado else f"se esperaba {esperado}")
    escribir_csv("runs_airflow.csv", filas_runs, ["run_id", "mes", "estado", "tipo", "inicio", "fin", "segundos"])
    escribir_csv("tareas_airflow.csv", filas_tareas, ["run_id", "mes", "tarea", "estado", "intentos", "segundos"])
    escribir_csv("avisos_airflow.csv", [dict(evento=k, n=v) for k, v in sorted(avisos.items())], ["evento", "n"])
    anota(b, "avisos en los registros de las tareas", ", ".join(f"{v} {k}" for k, v in sorted(avisos.items())), 0)


# -------------------------------------------------------------- 6. tamaños
def bloque_tamanos() -> None:
    b = "tamaños"
    filas = []
    with psycopg.connect(ADMIN, autocommit=True) as con:
        for esquema, tabla in consulta(con, "SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN ('crudo','preparado','marts') ORDER BY 1, 2"):
            n = consulta(con, f'SELECT count(*) FROM "{esquema}"."{tabla}"')[0][0]
            octetos = consulta(con, "SELECT pg_total_relation_size(%s)", (f"{esquema}.{tabla}",))[0][0]
            filas.append(dict(zona="postgresql", objeto=f"{esquema}.{tabla}", filas=n, octetos=octetos))
            ANTES[f"{esquema}.{tabla}"] = n
        ANTES["crudo.visualizaciones_top (2026-10)"] = consulta(con, "SELECT count(*) FROM crudo.visualizaciones_top WHERE fecha >= '2026-10-01'")[0][0]
        for objeto, sql in HUELLAS.items():
            ANTES["huella " + objeto] = consulta(con, sql)[0][0]
    c = s3(); bucket = os.environ["S3_BUCKET"]
    for pref in ("crudo/", "preparado/"):
        total, k, token = 0, 0, None
        while True:
            kw = dict(Bucket=bucket, Prefix=pref)
            if token:
                kw["ContinuationToken"] = token
            r = c.list_objects_v2(**kw)
            for o in r.get("Contents", []):
                total += o["Size"]; k += 1
            if not r.get("IsTruncated"):
                break
            token = r["NextContinuationToken"]
        filas.append(dict(zona="s3", objeto=pref, filas=k, octetos=total))
    escribir_csv("tamanos.csv", filas, ["zona", "objeto", "filas", "octetos"])
    for f in filas:
        anota(b, f["objeto"], f"{f['filas']} filas u objetos, {f['octetos']} octetos", 0)


# ------------------------------------------------------------ 8. snapshot
def bloque_snapshot() -> None:
    b = "snapshot"
    with psycopg.connect(DSN, autocommit=True) as con:
        r = consulta(con, """SELECT count(*), count(DISTINCT articulo_id), min(dbt_valid_from), max(dbt_valid_from),
                                    count(DISTINCT fecha_datos), min(fecha_datos), max(fecha_datos),
                                    count(*) FILTER (WHERE dbt_valid_to IS NULL)
                             FROM marts.snap_articulo_tramo""")[0]
        filas = [dict(metrica="versiones", valor=r[0]), dict(metrica="articulos", valor=r[1]),
                 dict(metrica="dbt_valid_from_min", valor=r[2].isoformat(timespec="seconds")), dict(metrica="dbt_valid_from_max", valor=r[3].isoformat(timespec="seconds")),
                 dict(metrica="minutos_entre_observaciones", valor=round((r[3] - r[2]).total_seconds() / 60, 1)),
                 dict(metrica="fechas_de_negocio_distintas", valor=r[4]), dict(metrica="fecha_datos_min", valor=str(r[5])), dict(metrica="fecha_datos_max", valor=str(r[6])),
                 dict(metrica="versiones_vigentes", valor=r[7])]
        por_n = consulta(con, "SELECT n, count(*) FROM (SELECT articulo_id, count(*) n FROM marts.snap_articulo_tramo GROUP BY 1) t GROUP BY 1 ORDER BY 1")
        escribir_csv("snapshot_versiones.csv", [dict(versiones=n, articulos=k) for n, k in por_n], ["versiones", "articulos"])
        ej = consulta(con, """SELECT ar.titulo, ar.es_articulo, s.tramo, s.fecha_datos, s.dbt_valid_from, s.dbt_valid_to
                              FROM marts.snap_articulo_tramo s JOIN marts.dim_articulo ar USING (articulo_id)
                              WHERE s.articulo_id = (SELECT s2.articulo_id FROM marts.snap_articulo_tramo s2 JOIN marts.dim_articulo a2 USING (articulo_id)
                                                     WHERE a2.es_articulo GROUP BY 1 ORDER BY count(*) DESC, s2.articulo_id LIMIT 1)
                              ORDER BY s.dbt_valid_from""")
        escribir_csv("snapshot_ejemplo.csv", [dict(titulo=t, tramo=tr, fecha_datos=str(fd), dbt_valid_from=vf.isoformat(timespec="seconds"),
                                                   dbt_valid_to=vt.isoformat(timespec="seconds") if vt else "") for t, _, tr, fd, vf, vt in ej],
                     ["titulo", "tramo", "fecha_datos", "dbt_valid_from", "dbt_valid_to"])
    escribir_csv("snapshot.csv", filas, ["metrica", "valor"])
    anota(b, "versiones de la dimensión con historia", f"{r[0]} versiones de {r[1]} artículos; dbt_valid_from en {filas[4]['valor']} minutos; {r[4]} fechas de negocio de {r[5]} a {r[6]}", 0)
    anota(b, "artículo con más versiones", f"{len(ej)} versiones", 0, ej[0][0] if ej else "")


# ------------------------------------------------------------- 9. ranking
def bloque_ranking() -> None:
    b = "ranking"
    import gzip
    filas = []
    with psycopg.connect(DSN, autocommit=True) as con:
        meses = [m[0] for m in consulta(con, "SELECT DISTINCT anio_mes FROM marts.hechos_ranking_mensual ORDER BY 1")]
        for anio_mes in meses:
            ruta = os.path.join(CACHE, "mensual", "all-access", anio_mes[:4], anio_mes[5:7] + ".json.gz")
            if not os.path.exists(ruta):
                anota(b, f"{anio_mes}: lista mensual oficial", "no está en la caché (laboratorio.sh datos)", 0); continue
            with gzip.open(ruta) as f:
                oficial = json.load(f)["items"][0]["articles"]
            of = {a["article"]: (a["views"], a["rank"]) for a in oficial}
            der = consulta(con, """SELECT ar.titulo, r.visitas_mes, r.posicion_mes FROM marts.hechos_ranking_mensual r
                                   JOIN marts.dim_articulo ar USING (articulo_id) JOIN marts.dim_acceso a USING (acceso_id)
                                   WHERE r.anio_mes = %s AND a.acceso = 'all-access' ORDER BY r.posicion_mes, ar.titulo""", (anio_mes,))
            de = {t: (v, p) for t, v, p in der}
            def top(d, n):
                return {t for t, (v, p) in d.items() if p <= n}
            coinc = {n: len(top(of, n) & top(de, n)) for n in (10, 100, 1000)}
            ausentes = sum(1 for t in of if t not in de)
            cocientes = sorted(de[t][0] / of[t][0] for t in top(of, 100) if t in de and of[t][0] > 0)
            mediana = statistics.median(cocientes) if cocientes else None
            # el cociente agregado: suma de visitas derivadas entre suma de oficiales, sobre el top 100 oficial entero
            # (un artículo sin fila en el derivado suma 0 arriba y sus visitas oficiales abajo)
            suma_of = sum(of[t][0] for t in top(of, 100)); suma_de = sum(de[t][0] for t in top(of, 100) if t in de)
            filas.append(dict(anio_mes=anio_mes, oficial=len(of), derivado=len(de), coincidencias_10=coinc[10], coincidencias_100=coinc[100],
                              coincidencias_1000=coinc[1000], ausentes_en_derivado=ausentes,
                              mediana_cociente_visitas_top100=round(mediana, 3) if mediana is not None else "",
                              cociente_agregado_visitas_top100=round(suma_de / suma_of, 3) if suma_of else ""))
    escribir_csv("ranking_oficial.csv", filas, ["anio_mes", "oficial", "derivado", "coincidencias_10", "coincidencias_100", "coincidencias_1000",
                                                "ausentes_en_derivado", "mediana_cociente_visitas_top100", "cociente_agregado_visitas_top100"])
    if filas:
        med = lambda k: statistics.median(f[k] for f in filas)
        anota(b, "ranking derivado frente a la lista mensual oficial", f"{len(filas)} meses; coincidencias (mediana) top 10 {med('coincidencias_10')}, top 100 {med('coincidencias_100')}, top 1000 {med('coincidencias_1000')}; "
              f"ausentes en el derivado (mediana) {med('ausentes_en_derivado')}; cociente de visitas en el top 100 (mediana de medianas) {statistics.median(f['mediana_cociente_visitas_top100'] for f in filas if f['mediana_cociente_visitas_top100'] != '')}", 0)


# -------------------------------------------------------- 10. idempotencia
# huellas de contenido (md5 de las filas ordenadas, sin las columnas técnicas
# de auditoría como cargado_en): si la huella es la misma, los valores son
# los mismos, no solo el número de filas
HUELLAS = {
    "crudo.visualizaciones_top (2026-10)": "SELECT md5(string_agg(concat_ws('|', proyecto, acceso, fecha, articulo, visitas, posicion), E'\\n' ORDER BY acceso, fecha, articulo)) FROM crudo.visualizaciones_top WHERE fecha >= '2026-10-01'",
    "marts.hechos_visualizaciones (2026-10)": "SELECT md5(string_agg(concat_ws('|', fecha_id, articulo_id, acceso_id, visitas, posicion), E'\\n' ORDER BY fecha_id, acceso_id, articulo_id)) FROM marts.hechos_visualizaciones WHERE fecha_id >= 20261001",
    "marts.dim_articulo": "SELECT md5(string_agg(concat_ws('|', articulo_id, titulo, espacio_nombres, es_articulo, primera_fecha_vista, ultima_fecha_vista), E'\\n' ORDER BY articulo_id)) FROM marts.dim_articulo",
    "marts.hechos_ranking_mensual (2026-10)": "SELECT md5(string_agg(concat_ws('|', anio_mes, articulo_id, acceso_id, visitas_mes, dias_en_top, posicion_media, mejor_posicion, posicion_mes), E'\\n' ORDER BY acceso_id, posicion_mes, articulo_id)) FROM marts.hechos_ranking_mensual WHERE anio_mes = '2026-10'",
    "marts.snap_articulo_tramo": "SELECT md5(string_agg(concat_ws('|', articulo_id, tramo, fecha_datos, dbt_valid_from, dbt_valid_to), E'\\n' ORDER BY articulo_id, dbt_valid_from)) FROM marts.snap_articulo_tramo",
}


def bloque_idempotencia() -> None:
    b = "idempotencia"
    filas = []
    with psycopg.connect(ADMIN, autocommit=True) as con:
        for objeto, sql in (("marts.hechos_visualizaciones", "SELECT count(*) FROM marts.hechos_visualizaciones"),
                            ("crudo.visualizaciones_top", "SELECT count(*) FROM crudo.visualizaciones_top"),
                            ("crudo.visualizaciones_top (2026-10)", "SELECT count(*) FROM crudo.visualizaciones_top WHERE fecha >= '2026-10-01'"),
                            ("marts.dim_articulo", "SELECT count(*) FROM marts.dim_articulo"),
                            ("marts.hechos_ranking_mensual", "SELECT count(*) FROM marts.hechos_ranking_mensual"),
                            ("marts.snap_articulo_tramo", "SELECT count(*) FROM marts.snap_articulo_tramo")):
            despues = consulta(con, sql)[0][0]
            filas.append(dict(objeto=objeto, antes=ANTES.get(objeto, ""), despues=despues))
        dup = consulta(con, "SELECT count(*) FROM (SELECT fecha_id, articulo_id, acceso_id FROM marts.hechos_visualizaciones GROUP BY 1, 2, 3 HAVING count(*) > 1) d")[0][0]
        filas.append(dict(objeto="claves duplicadas en los hechos", antes=0, despues=dup))
        for objeto, sql in HUELLAS.items():
            despues = consulta(con, sql)[0][0]
            filas.append(dict(objeto="huella " + objeto, antes=ANTES.get("huella " + objeto, ""), despues=despues))
    for f in filas:
        f["igual"] = "sí" if str(f["antes"]) == str(f["despues"]) else ("" if f["antes"] == "" else "no")
    escribir_csv("idempotencia.csv", filas, ["objeto", "antes", "despues", "igual"])
    iguales = all(f["antes"] == f["despues"] for f in filas if f["antes"] != "")
    anota(b, "las tablas tras repetir la carga de octubre de 2026 entera (run con fallo simulado recuperado)",
          "iguales que antes" if iguales else "DISTINTAS", 0, "; ".join(f"{f['objeto']}: {f['antes']} → {f['despues']}" for f in filas))


def principal() -> None:
    os.makedirs(DESTINO_DBT, exist_ok=True)
    inicio = time.time()
    try:
        bloque_tamanos()
        bloque_cargas()
        bloque_consultas()
        bloque_estrategias()
        bloque_tests()
        bloque_snapshot()
        bloque_ranking()
        bloque_airflow()
        bloque_idempotencia()
    finally:
        escribir_csv("pruebas.csv", PRUEBAS, ["instante", "bloque", "prueba", "resultado", "ms", "detalle"])
        print(f"\n{len(PRUEBAS)} anotaciones, {time.time() - inicio:.0f} s", flush=True)


if __name__ == "__main__":
    principal()
