"""Banco a: repetición exacta del banco de la entrada del 11-08-2026.

Treinta millones de filas y diez columnas, escritas en CSV y Parquet con la
misma semilla (7) y el mismo generador; seis maneras de recorrerlas y seis
motores para la misma agregación. Los programas de cada prueba son los de
agosto, letra por letra; solo cambian las rutas, que se rellenan al lanzar.
Cada medida es un proceso nuevo, con la caché de página del fichero expulsada
antes, y se toma la mediana de tres tandas.
"""

GENERADOR = '''
import sys
from pathlib import Path
import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc
import pyarrow.parquet as pq

BASE = Path(r"{base}")
FILAS = {filas}
LOTE = {lote}

BASE.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(7)
prov = pa.array(["Sevilla", "Madrid", "Soria", "Teruel", "Barcelona"])
esquema = pa.schema([
    ("id", pa.int64()), ("marca_tiempo", pa.int64()),
    ("provincia", pa.string()), ("sensor", pa.int16()),
    ("temperatura", pa.float32()), ("humedad", pa.float32()),
    ("presion", pa.float32()), ("bateria", pa.float32()),
    ("estado", pa.string()), ("nota", pa.string()),
])
csv_p = BASE / "datos.csv"
pq_snappy = BASE / "datos_snappy.parquet"
pq_zstd = BASE / "datos_zstd.parquet"

w_snappy = pq.ParquetWriter(pq_snappy, esquema, compression="snappy")
w_zstd = pq.ParquetWriter(pq_zstd, esquema, compression="zstd")
with open(csv_p, "w", encoding="utf-8") as f:
    f.write(",".join(n for n in esquema.names) + "\\n")
    base_id = 0
    for i in range(FILAS // LOTE):
        n = LOTE
        t = pa.table({{
            "id": np.arange(base_id, base_id + n, dtype=np.int64),
            "marca_tiempo": (1_750_000_000
                             + np.arange(n, dtype=np.int64)),
            "provincia": prov.take(rng.integers(0, 5, n)),
            "sensor": rng.integers(0, 512, n).astype(np.int16),
            "temperatura": rng.normal(18, 6, n).astype(np.float32),
            "humedad": rng.normal(55, 15, n).astype(np.float32),
            "presion": rng.normal(1013, 8, n).astype(np.float32),
            "bateria": rng.uniform(3.0, 4.2, n).astype(np.float32),
            "estado": pa.array(["ok"] * n),
            "nota": pa.array([""] * n),
        }}, schema=esquema)
        w_snappy.write_table(t)
        w_zstd.write_table(t)
        df = t.to_pandas()
        df.to_csv(f, header=False, index=False)
        base_id += n
        print("LOTE", i + 1, flush=True)
w_snappy.close()
w_zstd.close()

# arrow ipc sin comprimir, cada row group partido en lotes de 65536 filas:
# así sale el fichero de agosto (465 lotes que no cruzan row groups)
pf = pq.ParquetFile(pq_snappy)
with pa.OSFile(str(BASE / "datos.arrow"), "wb") as s:
    with ipc.new_file(s, pf.schema_arrow) as w:
        for i in range(pf.num_row_groups):
            for b in pf.read_row_group(i).to_batches(max_chunksize=65536):
                w.write_batch(b)
print("HECHO 1")
'''

# las seis pruebas de agosto, sin tocar
PRUEBAS = {
    "csv_pandas": """
import pandas as pd
df = pd.read_csv(r"{csv}")
print(len(df))
""",
    "parquet_completo": """
import pyarrow.parquet as pq
t = pq.read_table(r"{pqf}")
print(t.num_rows)
""",
    "parquet_2_columnas": """
import pyarrow.parquet as pq
t = pq.read_table(r"{pqf}", columns=["provincia", "temperatura"])
print(t.num_rows)
""",
    "parquet_filtro": """
import pyarrow.parquet as pq
t = pq.read_table(r"{pqf}", columns=["provincia", "temperatura"],
                  filters=[("provincia", "==", "Soria")])
print(t.num_rows)
""",
    "parquet_streaming": """
import pyarrow.parquet as pq
f = pq.ParquetFile(r"{pqf}")
n = 0
suma = 0.0
for lote in f.iter_batches(batch_size=65536,
                           columns=["provincia", "temperatura"]):
    n += lote.num_rows
    suma += lote.column("temperatura").to_numpy().sum()
print(n)
""",
    "csv_streaming": """
import pandas as pd
n = 0
for trozo in pd.read_csv(r"{csv}", usecols=["provincia", "temperatura"],
                         chunksize=200_000):
    n += len(trozo)
print(n)
""",
}

# los seis motores de agosto, sin tocar, más uno nuevo marcado como tal:
# polars con el motor predeterminado, que es el que cambia en la 2.0
MOTORES = {
    "pandas (carga completa)": """
import pandas as pd
df = pd.read_csv(r"{csv}", usecols=["provincia", "temperatura"])
r = df.groupby("provincia")["temperatura"].mean()
print(len(r))
""",
    "pyarrow (lotes a mano)": """
import pyarrow.parquet as pq, collections
f = pq.ParquetFile(r"{pqf}")
suma = collections.defaultdict(float); cuenta = collections.defaultdict(int)
for lote in f.iter_batches(batch_size=65536,
                           columns=["provincia", "temperatura"]):
    import pyarrow.compute as pc
    tabla = lote.to_pandas()
    g = tabla.groupby("provincia")["temperatura"].agg(["sum", "count"])
    for k, fila in g.iterrows():
        suma[k] += fila["sum"]; cuenta[k] += fila["count"]
print(len(suma))
""",
    "polars (lazy + streaming)": """
import polars as pl
r = (pl.scan_parquet(r"{pqf}")
       .group_by("provincia")
       .agg(pl.col("temperatura").mean())
       .collect(engine="streaming"))
print(r.height)
""",
    "polars (lazy, motor predeterminado)": """
import polars as pl
r = (pl.scan_parquet(r"{pqf}")
       .group_by("provincia")
       .agg(pl.col("temperatura").mean())
       .collect())
print(r.height)
""",
    "duckdb (SQL sobre el fichero)": """
import duckdb
r = duckdb.sql(
    "SELECT provincia, avg(temperatura) FROM '{pqf}' GROUP BY provincia"
).fetchall()
print(len(r))
""",
    "arrow IPC (mapeado)": """
import pyarrow.feather as ft, pyarrow.compute as pc
# se abre con mmap: no se copia el fichero a memoria del proceso
t = ft.read_table(r"{arr}", columns=["provincia", "temperatura"],
                  memory_map=True)
r = t.group_by("provincia").aggregate([("temperatura", "mean")])
print(r.num_rows)
""",
    "duckdb (sobre el CSV)": """
import duckdb
r = duckdb.sql(
    "SELECT provincia, avg(temperatura) FROM read_csv_auto('{csv}') "
    "GROUP BY provincia"
).fetchall()
print(len(r))
""",
}

# medida añadida, no es de agosto: pandas 3.1 lee el csv en paralelo (hasta
# seis hilos) y anuncia que un solo hilo ya es de dos a tres veces más rápido
# que en la 3.0; con un hilo se separan los dos efectos
EXTRA = {
    "csv_pandas (mode.max_threads=1)": ("pandas-3.1.0rc0", """
import pandas as pd
pd.set_option("mode.max_threads", 1)
df = pd.read_csv(r"{csv}")
print(len(df))
"""),
}

# qué biblioteca decide cada motor, para elegir sus entornos
FAMILIA_MOTOR = {
    "pandas (carga completa)": "pandas",
    "pyarrow (lotes a mano)": "pandas",
    "polars (lazy + streaming)": "polars",
    "polars (lazy, motor predeterminado)": "polars",
    "duckdb (SQL sobre el fichero)": "duckdb",
    "arrow IPC (mapeado)": "pandas",
    "duckdb (sobre el CSV)": "duckdb",
}

# cada hijo informa de su propio pico, como en agosto
EPILOGO = """
import resource as _r
print("RSS_KB", _r.getrusage(_r.RUSAGE_SELF).ru_maxrss)
"""

# cifras publicadas el 11-08-2026 (resultados.json y motores.json de agosto)
AGOSTO = {
    ("seis", "csv_pandas"): (22.14, 7634.1),
    ("seis", "parquet_completo"): (1.47, 2695.0),
    ("seis", "parquet_2_columnas"): (0.77, 735.8),
    ("seis", "parquet_filtro"): (0.73, 485.5),
    ("seis", "parquet_streaming"): (1.01, 131.9),
    ("seis", "csv_streaming"): (12.52, 134.2),
    ("motores", "pandas (carga completa)"): (12.36, 1023.2),
    ("motores", "pyarrow (lotes a mano)"): (2.69, 140.5),
    ("motores", "polars (lazy + streaming)"): (0.41, 881.2),
    ("motores", "duckdb (SQL sobre el fichero)"): (0.16, 259.3),
    ("motores", "arrow IPC (mapeado)"): (1.23, 995.2),
    ("motores", "duckdb (sobre el CSV)"): (1.64, 1296.2),
}


def fichero_prueba(nombre: str) -> str:
    """Fichero que se enfría antes de cada prueba, con la regla de agosto."""
    return "datos.csv" if "csv" in nombre else "datos_snappy.parquet"


def fichero_motor(nombre: str) -> str:
    """Fichero que se enfría antes de cada motor, con la regla de agosto.

    La regla de agosto buscaba «CSV» en mayúsculas, de modo que «pandas
    (carga completa)» enfriaba el Parquet y leía el CSV desde la caché. Se
    reproduce tal cual; `calienta_motor` deja ese CSV en caché a propósito.
    """
    if "CSV" in nombre:
        return "datos.csv"
    if "arrow" in nombre:
        return "datos.arrow"
    return "datos_snappy.parquet"


def calienta_motor(nombre: str) -> str | None:
    """Fichero que se lee antes de medir, para fijar el estado de agosto."""
    return "datos.csv" if nombre == "pandas (carga completa)" else None
