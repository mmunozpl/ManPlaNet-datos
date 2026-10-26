"""Banco b: las 22 consultas TPC-H en Polars y DuckDB, sobre Parquet.

Los datos salen de la extensión tpch de DuckDB (dbgen) y se escriben a
Parquet con las columnas DECIMAL pasadas a DOUBLE, que es el tipo que obtiene
polars-benchmark al inferir los ficheros .tbl. Las consultas de Polars son
las de pola-rs/polars-benchmark en un commit fijado; las de DuckDB, las de su
propia extensión (`tpch_queries()`), extraídas una vez y usadas sin tocar en
todas las versiones. Este módulo no copia el texto de ninguna consulta: el
repositorio se clona en el directorio de datos y las de DuckDB se leen de la
extensión al generar.
"""

import json
import math
from pathlib import Path

PB_REPO = "https://github.com/pola-rs/polars-benchmark.git"
PB_COMMIT = "401908a307f133a2dffbe3f5e0e0fb2b50ea310b"
TABLAS = ["customer", "lineitem", "nation", "orders", "part", "partsupp",
          "region", "supplier"]

# tolerancia declarada para dar dos resultados por coincidentes
TOL_REL = 1e-9
TOL_ABS = 1e-9
# polars-benchmark redondea a dos decimales en estas consultas y la extensión
# de duckdb no; ahí se admite medio céntimo de diferencia absoluta
REDONDEADAS = {8, 9, 10, 11, 14, 15, 17, 19, 22}
TOL_REDONDEO = 0.005 + 1e-9

GENERA = '''
import duckdb, time
from pathlib import Path
DEST = Path(r"{dest}")
SF = {sf}
HIJOS = {hijos}
PASO = {paso}
SOLO = {solo}
DEST.mkdir(parents=True, exist_ok=True)
c = duckdb.connect()
c.execute("SET memory_limit='{memoria}'")
c.execute("SET temp_directory='{temporal}'")
c.execute("INSTALL tpch")
c.execute("LOAD tpch")
t0 = time.time()
if HIJOS > 1:
    c.execute(f"CALL dbgen(sf={{SF}}, children={{HIJOS}}, step={{PASO}})")
else:
    c.execute(f"CALL dbgen(sf={{SF}})")
print("DBGEN", round(time.time() - t0, 1), flush=True)
for t in (SOLO or {tablas}):
    cols = c.execute(f"DESCRIBE {{t}}").fetchall()
    sel = ", ".join(
        f"CAST({{n}} AS DOUBLE) AS {{n}}" if ty.startswith("DECIMAL")
        else n for n, ty, *_ in cols)
    if HIJOS > 1:
        (DEST / t).mkdir(exist_ok=True)
        f = DEST / t / f"parte-{{PASO:03d}}.parquet"
    else:
        f = DEST / f"{{t}}.parquet"
    c.execute(f"COPY (SELECT {{sel}} FROM {{t}}) TO '{{f}}' "
              "(FORMAT parquet, COMPRESSION snappy)")
print("HECHO", round(time.time() - t0, 1))
'''

EXTRAE = '''
import duckdb, json
c = duckdb.connect()
c.execute("INSTALL tpch")
c.execute("LOAD tpch")
q = c.execute("SELECT query_nr, query FROM tpch_queries() "
              "ORDER BY 1").fetchall()
v = c.execute("SELECT extension_version FROM duckdb_extensions() "
              "WHERE extension_name = 'tpch'").fetchone()[0]
json.dump({{"version_tpch": v, "consultas": {{str(n): s for n, s in q}}}},
          open(r"{salida}", "w"))
print("HECHO", len(q))
'''

# arranque del motor fuera del cronómetro, como hace polars-benchmark;
# la lectura de metadatos y la consulta entera quedan dentro
POLARS = '''
import importlib.util, json, sys, time, types
import polars as pl
RAIZ = r"{raiz}"
DATOS = r"{datos}"
Q = {q}
MOTOR = "{motor}"
SALIDA = r"{salida}"
paq = types.ModuleType("queries"); paq.__path__ = []
sub = types.ModuleType("queries.polars"); sub.__path__ = []
uti = types.ModuleType("queries.polars.utils")
sub.utils = uti
ajustes = types.ModuleType("settings")


class Settings:
    scale_factor = {sf}


ajustes.Settings = Settings
sys.modules.update({{"queries": paq, "queries.polars": sub,
                    "queries.polars.utils": uti, "settings": ajustes}})
esp = importlib.util.spec_from_file_location(
    "consulta", f"{{RAIZ}}/queries/polars/q{{Q}}.py")
mod = importlib.util.module_from_spec(esp)
esp.loader.exec_module(mod)


def recoge(lf):
    return lf.collect() if MOTOR == "auto" else lf.collect(engine=MOTOR)


recoge(pl.LazyFrame({{"a": [1]}}))
t0 = time.perf_counter()
lfs = {{t: pl.scan_parquet(f"{{DATOS}}/{{t}}.parquet") for t in {tablas}}}
df = recoge(mod.q(**lfs))
dt = time.perf_counter() - t0
print("T_CONSULTA", dt)
print("FILAS", df.height)
if SALIDA:
    json.dump({{"columnas": df.columns,
               "filas": [list(r) for r in df.rows()]}},
              open(SALIDA, "w"), default=str)
'''

DUCKDB = '''
import json, time
import duckdb
DATOS = r"{datos}"
SALIDA = r"{salida}"
sql = open(r"{fsql}").read()
c = duckdb.connect()
c.execute("SELECT 1").fetchall()
t0 = time.perf_counter()
for t in {tablas}:
    c.execute(f"CREATE VIEW {{t}} AS SELECT * FROM "
              f"read_parquet('{{DATOS}}/{{t}}.parquet')")
r = c.execute(sql)
filas = r.fetchall()
dt = time.perf_counter() - t0
print("T_CONSULTA", dt)
print("FILAS", len(filas))
if SALIDA:
    json.dump({{"columnas": [d[0] for d in r.description],
               "filas": [list(f) for f in filas]}},
              open(SALIDA, "w"), default=str)
'''


def _num(x):
    """Convierte a float lo que sea numérico; None si no lo es."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        try:
            return float(x)
        except ValueError:
            return None
    return None


def compara(a: dict, b: dict, tol_abs: float = TOL_ABS) -> dict:
    """Compara dos resultados por posición de columna y de fila.

    Los nombres de columna difieren entre motores, así que se comparan por
    posición. Primero en el orden devuelto; si no coinciden, ordenadas las
    filas de ambos lados, para distinguir un orden distinto de un valor
    distinto.

    Args:
        a: resultado de referencia (columnas, filas).
        b: resultado comparado.
        tol_abs: tolerancia absoluta; TOL_REDONDEO en las consultas que un
            lado redondea a dos decimales.

    Returns:
        Diccionario con coincidencia, filas y diferencia relativa máxima.
    """
    fa, fb = a["filas"], b["filas"]
    d = {"filas_ref": len(fa), "filas": len(fb), "dif_rel_max": 0.0,
         "tol_rel": TOL_REL, "tol_abs": tol_abs,
         "coincide": False, "solo_orden": False, "detalle": ""}
    if len(fa) != len(fb):
        d["detalle"] = "número de filas distinto"
        return d
    if fa and len(fa[0]) != len(fb[0]):
        d["detalle"] = "número de columnas distinto"
        return d

    def iguala(xa, xb):
        peor = 0.0
        for ra, rb in zip(xa, xb):
            for va, vb in zip(ra, rb):
                na, nb = _num(va), _num(vb)
                if na is not None and nb is not None:
                    if not math.isclose(na, nb, rel_tol=TOL_REL,
                                        abs_tol=tol_abs):
                        return False, peor
                    if na != nb:
                        den = max(abs(na), abs(nb))
                        peor = max(peor, abs(na - nb) / den)
                elif str(va) != str(vb):
                    return False, peor
        return True, peor

    ok, peor = iguala(fa, fb)
    if ok:
        d.update(coincide=True, dif_rel_max=peor)
        return d

    def clave(r):
        return [str(x) for x in r]

    ok, peor = iguala(sorted(fa, key=clave), sorted(fb, key=clave))
    if ok:
        d.update(coincide=True, solo_orden=True, dif_rel_max=peor,
                 detalle="mismas filas en otro orden")
        return d
    d["detalle"] = "valores distintos"
    return d


def lee(ruta: Path) -> dict | None:
    """Lee un resultado volcado por un hijo; None si no existe."""
    try:
        return json.loads(Path(ruta).read_text())
    except (OSError, ValueError):
        return None
