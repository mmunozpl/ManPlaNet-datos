"""Banco c: agregaciones sobre un Parquet mayor que el tope de memoria.

La tabla lineitem de TPC-H a SF100 (600 millones de filas) se recorre bajo
un tope de cgroup de 8 GiB, sin swap. Tres consultas:

- c1, la consulta 1 de TPC-H: cuatro grupos, estado diminuto; mide si el
  motor recorre más datos que memoria sin necesidad de volcar.
- c2, suma de l_quantity por l_orderkey (150 millones de grupos, estado de
  tamaño fijo), la subconsulta de la 18: obliga a volcar a disco.
- c3, máximo de l_comment por l_orderkey (150 millones de grupos, estado de
  tamaño variable): pone a prueba el volcado de estados de agregado que
  DuckDB anuncia para la 2.0 (#24499).

Cada consulta reduce su salida a una o pocas filas para que el resultado
no pese. Se registra si termina, el tiempo, los picos de memoria y los bytes
escritos a disco temporal.
"""

POLARS = '''
import importlib.util, sys, time, types
import polars as pl
RAIZ = r"{raiz}"
GLOB = r"{glob}"
CONSULTA = "{consulta}"
MOTOR = "{motor}"


def recoge(lf):
    return lf.collect() if MOTOR == "auto" else lf.collect(engine=MOTOR)


recoge(pl.LazyFrame({{"a": [1]}}))
t0 = time.perf_counter()
li = pl.scan_parquet(GLOB)
if CONSULTA == "c1":
    paq = types.ModuleType("queries"); paq.__path__ = []
    sub = types.ModuleType("queries.polars"); sub.__path__ = []
    sub.utils = types.ModuleType("queries.polars.utils")
    sys.modules.update({{"queries": paq, "queries.polars": sub,
                        "queries.polars.utils": sub.utils}})
    esp = importlib.util.spec_from_file_location(
        "consulta", f"{{RAIZ}}/queries/polars/q1.py")
    mod = importlib.util.module_from_spec(esp)
    esp.loader.exec_module(mod)
    lf = mod.q(lineitem=li)
elif CONSULTA == "c2":
    lf = (li.group_by("l_orderkey")
            .agg(pl.col("l_quantity").sum().alias("s"))
            .filter(pl.col("s") > 300)
            .select(pl.len().alias("n"), pl.col("s").sum().alias("t")))
else:
    lf = (li.group_by("l_orderkey")
            .agg(pl.col("l_comment").max().alias("m"))
            .select(pl.len().alias("n"),
                    pl.col("m").str.len_bytes().sum().alias("t")))
df = recoge(lf)
dt = time.perf_counter() - t0
print("T_CONSULTA", dt)
print("RESULTADO", [list(r) for r in df.rows()][:4])
'''

DUCKDB = '''
import time
import duckdb
GLOB = r"{glob}"
CONSULTA = "{consulta}"
c = duckdb.connect()
print("LIMITE_DUCKDB", c.execute(
    "SELECT current_setting('memory_limit')").fetchone()[0])
print("TEMPORAL_DUCKDB", c.execute(
    "SELECT current_setting('temp_directory')").fetchone()[0])
SQL = {{
    "c1": open(r"{fq1}").read(),
    "c2": "SELECT count(*), sum(s) FROM (SELECT l_orderkey, "
          "sum(l_quantity) AS s FROM lineitem GROUP BY l_orderkey "
          "HAVING sum(l_quantity) > 300)",
    "c3": "SELECT count(*), sum(strlen(m)) FROM (SELECT l_orderkey, "
          "max(l_comment) AS m FROM lineitem GROUP BY l_orderkey)",
}}
c.execute("SELECT 1").fetchall()
t0 = time.perf_counter()
c.execute(f"CREATE VIEW lineitem AS SELECT * FROM read_parquet('{{GLOB}}')")
filas = c.execute(SQL[CONSULTA]).fetchall()
dt = time.perf_counter() - t0
print("T_CONSULTA", dt)
print("RESULTADO", [list(f) for f in filas][:4])
'''

# configuraciones de polars: (etiqueta, motor, variables de entorno)
# el presupuesto de 1.x se fija en el 80 % del tope, como haría la 2.0
CONF_POLARS = {
    "1": [("predeterminado", "auto", {}),
          ("streaming", "streaming", {})],
    "1.44.2": [("streaming + volcado a mano", "streaming",
                {"POLARS_OOC_MEMORY_BUDGET_MB": "{presupuesto_mb}"})],
    "2": [("predeterminado", "auto", {}),
          ("in-memory", "in-memory", {}),
          ("streaming sin volcado", "streaming",
           {"POLARS_OOC_MEMORY_BUDGET_FRACTION": "1000"})],
}
