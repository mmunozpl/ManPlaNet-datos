"""Banco d: cambios de Polars 1.x a 2.0 que alteran el resultado sin error.

Un ejemplo mínimo por apartado de la guía de migración
(https://docs.pola.rs/releases/upgrade/2/), tomado de la propia guía cuando
lo trae. Los apartados se contaron a mano sobre la guía descargada el
15-10-2026: 51 subapartados en cinco bloques más el bloque de retiradas, que
es una tabla sin subapartados y cuenta como uno. Cada ejemplo deja su
resultado en `r`; el hijo lo reduce a una forma canónica (esquema y filas)
para comparar versiones sin depender de cómo se imprime cada una.

Los casos de orden de filas usan dos millones de filas y cinco tandas,
porque con tres filas el orden puede coincidir por azar.
"""

BLOQUES = {
    "I": "Cambios incompatibles",
    "C": "Conversiones y operaciones que ya no se admiten",
    "A": "Cambios de forma de la API",
    "V": "Lectura de CSV",
    "R": "Retirada de funcionalidad obsoleta",
    "D": "Obsolescencias",
}

# (número de apartado, bloque, título en la guía, subcaso, código, env)
CASOS = [
    (1, "I", "The Lazy API defaults to the streaming engine", "unpivot", """
lf = pl.LazyFrame({"a": ["x", "y", "z"], "b": [1, 2, 3], "c": [4, 5, 6]})
r = lf.unpivot(pl.selectors.numeric(), index="a").collect()
""", None),
    (1, "I", "The Lazy API defaults to the streaming engine",
     "join izquierdo, 2 M filas: ¿conserva el orden de la izquierda?", """
n = 2_000_000
rng = np.random.default_rng(7)
izq = pl.LazyFrame({"k": rng.permutation(n), "i": np.arange(n)})
der = pl.LazyFrame({"k": np.arange(n), "v": np.arange(n) * 2})
r = []
for _ in range(5):
    out = izq.join(der, on="k", how="left").collect()
    r.append(bool((out["i"] == pl.Series(np.arange(n))).all()))
""", None),
    (1, "I", "The Lazy API defaults to the streaming engine",
     "group_by, 2 M filas y 1000 claves: ¿orden de aparición?", """
n = 2_000_000
rng = np.random.default_rng(7)
claves = rng.integers(0, 1000, n)
lf = pl.LazyFrame({"g": claves, "x": np.ones(n)})
prim = pl.Series(claves).unique(maintain_order=True).to_list()
ordenes = []
for _ in range(5):
    out = lf.group_by("g").agg(pl.col("x").sum()).collect()
    ordenes.append(out["g"].to_list())
r = {"aparicion": [o == prim for o in ordenes],
     "ordenes_distintos": len({tuple(o) for o in ordenes})}
""", None),
    (2, "I", "pl.read_csv is now dispatched to pl.scan_csv(...).collect()",
     "columns por posición", """
data = b"a,b,c,d\\n1,2,3,4\\n1,2,3,4\\n"
r = pl.read_csv(data, columns=[2, 1, 3])
""", None),
    (2, "I", "pl.read_csv is now dispatched to pl.scan_csv(...).collect()",
     "schema_overrides en lista", """
data = b"a,b,c,d\\n1,2,3,4\\n1,2,3,4\\n"
r = pl.read_csv(data, schema_overrides=[pl.String]).dtypes
""", None),
    (3, "I", "pl.read_ipc is now dispatched to pl.scan_ipc(...).collect() "
     "for all non-use_pyarrow inputs", "", """
f = TMP + "/d.arrow"
pl.DataFrame({"a": [1, 2]}).write_ipc(f)
r = pl.read_ipc(f, memory_map=True)
""", None),
    (4, "I", "Change default show_graph() plan_stage to \"physical\"", "", """
lf = pl.LazyFrame({"a": ["x", "y"], "b": [1, 2]})
r = lf.group_by("a").agg(pl.all().sum()).show_graph(raw_output=True)
""", None),
    (5, "I", "Remove LazyFrame.profile()", "", """
lf = pl.LazyFrame({"a": ["x", "y"], "b": [1, 2]})
r = lf.group_by("a", maintain_order=True).agg(pl.all().sum()).profile()[0]
""", None),
    (6, "I", "Update the strict behavior of pl.concat()/pl.union()", "", """
df1 = pl.DataFrame({"a": [1, 2, 3]})
df2 = pl.DataFrame({"b": [4, 5]})
r = pl.concat([df1, df2], how="horizontal")
""", None),
    (7, "I", "Set explode() empty_as_null=False by default", "", """
r = pl.DataFrame({"a": [[1, 2, 3], [], [4, 5, 6]]}).explode("a")
""", None),
    (8, "I", "Change supertype of signed integer types and UInt64 from "
     "Float64 to Int128", "", """
lf = pl.LazyFrame({"a": [1, 2, 3], "b": [1, 2, 3]},
                  schema={"a": pl.Int64, "b": pl.UInt64})
r = lf.select((pl.col("a") + pl.col("b")).alias("result")).collect()
""", None),
    (9, "I", "Make coercion casts for is_in() strict instead of lossy", "", """
r = pl.Series([1]).is_in(pl.Series([1.99]))
""", None),
    (10, "I", "Stop coercing pl.col(...) to a selector in selector &, |, ^",
     "", """
df = pl.DataFrame({"a": [1, 2], "b": [3, 4], "mask": [1, 0]})
r = df.select(pl.selectors.integer() & pl.col("mask"))
""", None),
    (11, "I", "Set the output name of pl.datetime and pl.repeat to their "
     "leftmost argument name", "", """
df = pl.DataFrame({"year": [2001], "month": [1], "day": [1], "hour": [23]})
r = df.select(pl.datetime("year", "month", "day", "hour"))
""", None),
    (12, "I", "Preserve outer nulls in list/array to_struct()", "", """
s = pl.Series([None], dtype=pl.List(pl.Int64))
r = s.list.to_struct(fields=["a", "b", "c"]).to_list()
""", None),
    (13, "I", "Do not reset seek position when scanning from file-like "
     "objects", "parquet tras escribir", """
buf = io.BytesIO()
pl.DataFrame({"a": [1, 2, 3]}).write_parquet(buf)
r = pl.read_parquet(buf)
""", None),
    (13, "I", "Do not reset seek position when scanning from file-like "
     "objects", "csv con el cursor a mitad", """
buf = io.BytesIO(b"a\\n1\\n2\\n3\\n")
buf.read(4)
r = pl.read_csv(buf)
""", None),
    (14, "I", "Preserve height in zero-width DataFrame/LazyFrame operations",
     "", """
df = pl.DataFrame({"a": [2, 1, 3], "b": ["a", "b", "c"], "c": [1, 2, 3]})
r = df.drop("*").shape
""", None),
    (15, "I", "Always return Series from from_arrow(<ArrowStreamExportable>)",
     "", """
class SoloFlujo:
    def __init__(self, obj):
        self._obj = obj
    def __arrow_c_stream__(self, requested_schema=None):
        return self._obj.__arrow_c_stream__(requested_schema)
r = pl.from_arrow(SoloFlujo(pl.DataFrame({"x": [1, 2, 3]})))
""", None),
    (16, "I", "Remove the DataFrame Interchange Protocol", "", """
r = type(pl.DataFrame({"a": [1, 2, 3]}).__dataframe__()).__name__
""", None),
    (17, "I", "Allow transposing an empty DataFrame", "", """
r = pl.DataFrame().transpose()
""", None),
    (18, "I", "shift(n=None) now raises", "", """
r = pl.DataFrame({"a": pl.Series([1, 2, 3], dtype=pl.Int32)}).shift(None)
""", None),
    (19, "I", "Unknown Arrow extension types load as extension dtypes", "", """
campo = pa.field("id", pa.int64(),
                 metadata={b"ARROW:extension:name": b"google:sqlType:integer"})
tabla = pa.table([pa.array([1, 2, 3])], schema=pa.schema([campo]))
r = pl.from_arrow(tabla)
""", None),
    (20, "I", "Load Arrow, Parquet and Iceberg map columns as the new Map "
     "dtype", "", """
tabla = pa.table({"m": pa.array([[("a", 1), ("b", 2)], None],
                                type=pa.map_(pa.string(), pa.int64()))})
r = pl.from_arrow(tabla)
""", None),
    (21, "I", "Resolve struct arithmetic supertypes per field",
     "campos numéricos", """
df = pl.DataFrame({"i": [1], "f": pl.Series([2], dtype=pl.Float32),
                   "s": ["a"]})
r = df.select(pl.struct("i", "f") + 1.5)
""", None),
    (21, "I", "Resolve struct arithmetic supertypes per field",
     "campo de texto", """
df = pl.DataFrame({"i": [1], "s": ["a"]})
r = df.select(pl.struct("i", "s") + 1)
""", None),
    (22, "I", "Widen the Decimal precision of rounding, sign() and sums", "",
     """
s = pl.Series([Decimal("9.5"), Decimal("-0.5")], dtype=pl.Decimal(2, 1))
r = s.round(0)
""", None),
    (23, "I", "Defer SQL query resolution to collect()", "", """
ctx = pl.SQLContext(t=pl.LazyFrame({"a": [1, 2]}))
r = type(ctx.execute("SELECT * FROM derived")).__name__
""", None),
    (24, "I", "Use SQL result scales for decimal * and / in SQL", "", """
df = pl.DataFrame({"a": [Decimal("0.05")], "b": [Decimal("0.03")]},
                  schema={"a": pl.Decimal(7, 2), "b": pl.Decimal(7, 2)})
r = df.sql("SELECT a * b AS product, a / b AS ratio FROM self")
""", None),
    (25, "I", "Type exact SQL numeric literals as Decimal, and truncate SQL "
     "% and DIV", "", """
df = pl.DataFrame({"z": [1]})
r = df.sql("SELECT 1.5 AS lit, -7 % 2 AS resto, DIV(-7.5, 2) AS div, "
           "ROUND(2.5) AS red, CAST(1 AS DECIMAL(10, 2)) * 1.0000 AS mul "
           "FROM self")
""", None),
    (26, "I", "Read the Parquet ENUM logical type as String", "", """
f = TMP + "/enum.parquet"
crea_enum(f)
r = pl.read_parquet(f)
""", None),
    (27, "C", "Disable casting from integers to categoricals, and from "
     "categoricals to integers", "", """
r = pl.Series([None, 1, 0, 2], dtype=pl.UInt32).cast(pl.Enum(["a", "b", "c"]))
""", None),
    (28, "C", "Remove casts from string to temporal types", "", """
r = pl.Series(["2022-08-30"]).cast(pl.Date)
""", None),
    (29, "C", "Disallow casting from non-nested types to pl.List(..)", "", """
r = pl.Series("a", [1, 2, 3], dtype=pl.Int32).cast(pl.List(pl.Int32))
""", None),
    (30, "C", "Do not allow boolean operators between booleans and integer "
     "types", "", """
lf = pl.LazyFrame({"bool": [True, False], "int": [1, 2]},
                  schema={"bool": pl.Boolean, "int": pl.Int32})
r = lf.select(pl.col("bool") & pl.col("int")).collect()
""", None),
    (31, "C", "Remove support for std()/var() on the Duration dtype", "", """
r = pl.Series([timedelta(days=1), timedelta(days=2),
               timedelta(days=4)]).std()
""", None),
    (32, "C", "Disable invalid struct casts when strict=True", "", """
r = pl.Series("x", [{"a": 1, "b": 2}]).cast(pl.Struct({"a": pl.Int64}))
""", None),
    (33, "C", "Disallow flat dtypes where a list is expected", "", """
df = pl.DataFrame({"a": [[1, 2], [3, 4]], "b": [0, 1]})
r = df.select(pl.col("a").list.gather(0))
""", None),
    (34, "C", "Convert time units in is_in() and list.contains()", "", """
aguja = pl.Series([datetime(2020, 1, 1)], dtype=pl.Datetime("ns"))
valores = pl.Series([datetime(2020, 1, 1)], dtype=pl.Datetime("us"))
r = aguja.is_in(valores)
""", None),
    (35, "C", "Stop comparing Decimal needles against float data in is_in()",
     "", """
precios = pl.Series("price", [Decimal("1.00"), Decimal("2.50")],
                    dtype=pl.Decimal(10, 2))
r = precios.is_in([1.005, 2.5])
""", None),
    (36, "C", "Raise when comparing naive and time-zone-aware datetimes in "
     "is_in()", "", """
valores = pl.Series([[datetime(2020, 1, 1)]]).list.eval(
    pl.element().dt.replace_time_zone("UTC"))
r = valores.list.contains(pl.lit(datetime(2020, 1, 1)))
""", None),
    (37, "C", "Treat labels outside an Enum as absent in is_in() and "
     "list.contains()", "", """
r = pl.Series([["a", "z"]]).list.contains(pl.lit("a", pl.Enum(["a", "b"])))
""", None),
    (38, "C", "Raise on non-numeric input to log(), log1p() and exp()", "", """
r = pl.Series(["a", "b"]).log()
""", None),
    (39, "A", "Simplify list.to_struct API", "", """
df = pl.DataFrame({"n": [[0, 1, 2], [0, 1]]})
r = df.select(pl.col("n").list.to_struct(upper_bound=3))
""", None),
    (40, "A", "Make add_business_days() and str.to_decimal() keyword-only "
     "arguments strict", "", """
r = pl.Series([date(2020, 1, 1)]).dt.add_business_days(
    5, (True, True, True, True, True, False, False))
""", None),
    (41, "A", "Replace multi-seed hash API with a single seed",
     "cuatro semillas", """
r = pl.DataFrame({"a": [1, 2, 3]}).with_columns(pl.all().hash(10, 20, 30, 40))
""", None),
    (41, "A", "Replace multi-seed hash API with a single seed",
     "semilla por defecto", """
r = pl.Series("a", [1, 2, 3]).hash()
""", None),
    (42, "A", "Do not support list type anymore for Series.search_sorted()",
     "", """
r = pl.Series([1, 2, 3]).search_sorted([1, 2])
""", None),
    (43, "A", "Raise an error on struct.rename_fields() with an incorrect "
     "number of fields", "", """
r = pl.Series("s", [{"a": 1, "b": 2}]).struct.rename_fields(["x"])
""", None),
    (44, "A", "Remove the ordering parameter and the 'physical'/'lexical' "
     "special case on pl.Categorical()", "ordering=", """
r = repr(pl.Categorical(ordering="lexical"))
""", None),
    (44, "A", "Remove the ordering parameter and the 'physical'/'lexical' "
     "special case on pl.Categorical()", 'Categorical("physical")', """
r = pl.Series(["b", "a", "c"], dtype=pl.Categorical("physical")).sort()
""", None),
    (45, "V", "Set csv infer_schema_files default value to 10", "", """
r = pl.scan_csv([b"a\\n1"] * 10 + [b"a\\nA"]).collect().tail(1)
""", None),
    (46, "V", "Start csv column name counting at 0", "", """
r = pl.read_csv(b"a,1,10;b,2,20", eol_char=";", has_header=False)
""", None),
    (47, "V", "Respect file column order when schema is given for scan_csv()",
     "", """
r = pl.scan_csv(b"a,b\\nA,B\\n",
                schema={"b": pl.String, "a": pl.String}).collect()
""", None),
    (48, "V", "Automatically disable raise_if_empty when has_header=False "
     "and schema is given", "", """
r = pl.read_csv(b"", has_header=False, schema={"a": pl.Int64})
""", None),
    (49, "R", "Removal of deprecated functionality (tabla)", "melt", """
r = pl.LazyFrame({"a": [1], "b": [2]}).melt(id_vars="a",
                                           value_vars="b").collect()
""", None),
    (49, "R", "Removal of deprecated functionality (tabla)",
     "join(join_nulls=)", """
df = pl.DataFrame({"a": [1, None]})
r = df.join(df, on="a", join_nulls=True)
""", None),
    (49, "R", "Removal of deprecated functionality (tabla)",
     "POLARS_AUTO_STRUCTIFY=1", """
df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
r = df.select(pl.col("a", "b") + 1)
""", {"POLARS_AUTO_STRUCTIFY": "1"}),
    (50, "D", "Mark read_avro()/write_avro() as unstable", "", """
f = TMP + "/d.avro"
pl.DataFrame({"a": [1, 2]}).write_avro(f)
r = pl.read_avro(f)
""", None),
    (51, "D", "Deprecate redundant strict=True on horizontal "
     "pl.concat()/pl.union()", "", """
r = pl.concat([pl.DataFrame({"a": [1]}), pl.DataFrame({"b": [2]})],
              how="horizontal", strict=True)
""", None),
    (52, "D", "Deprecate cut()/qcut() in favour of the bin_* methods",
     "cut con etiquetas", """
r = pl.DataFrame({"foo": [-2, -1, 0, 1, 2]}).with_columns(
    pl.col("foo").cut([-1, 1], labels=["a", "b", "c"]).alias("bin"))
""", None),
    (52, "D", "Deprecate cut()/qcut() in favour of the bin_* methods",
     "qcut sin etiquetas", """
r = pl.Series([1, 2, 3, 4, 5, 6, 7, 8]).qcut(4)
""", None),
]

# el hijo: ejecuta cada caso en un espacio de nombres limpio y reduce el
# resultado a una forma canónica serializable
HIJO = r'''
import io, json, os, struct, subprocess, sys, tempfile, traceback, warnings
from datetime import date, datetime, timedelta
from decimal import Decimal
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import polars as pl

CASOS = json.load(open(sys.argv[1]))
SALIDA = sys.argv[2]
SOLO = int(sys.argv[3]) if len(sys.argv) > 3 else None


def crea_enum(f):
    """parquet con anotación ENUM: dos bytes del pie de uno de pyarrow."""
    pq.write_table(pa.table({"color": ["RED", "GREEN"]}), f,
                   store_schema=False, write_statistics=False)
    with open(f, "rb") as h:
        b = bytearray(h.read())
    n = struct.unpack("<I", b[-8:-4])[0]
    ini = len(b) - 8 - n
    i = ini + b[ini:].find(b"color")
    assert b[i + 5:i + 9] == bytes([0x25, 0x00, 0x4C, 0x1C])
    b[i + 6] = 0x08
    b[i + 8] = 0x4C
    with open(f, "wb") as h:
        h.write(b)


def canon(x):
    if isinstance(x, pl.DataFrame):
        return {"tipo": "DataFrame",
                "esquema": {k: str(v) for k, v in x.schema.items()},
                "filas": [[canon(v) for v in f] for f in x.rows()]}
    if isinstance(x, pl.Series):
        return {"tipo": "Series", "nombre": x.name, "dtype": str(x.dtype),
                "valores": [canon(v) for v in x.to_list()]}
    if isinstance(x, pl.Schema):
        return {k: str(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [canon(v) for v in x]
    if isinstance(x, dict):
        return {str(k): canon(v) for k, v in x.items()}
    if isinstance(x, (bool, int, float, str)) or x is None:
        return x
    if isinstance(x, bytes):
        return "bytes:" + x.hex()
    if isinstance(x, (Decimal, date, datetime, timedelta)):
        return f"{type(x).__name__}:{x}"
    if isinstance(x, pl.DataType) or (isinstance(x, type)
                                      and issubclass(x, pl.DataType)):
        return "dtype:" + str(x)
    return "repr:" + repr(x)


res = []
tmp = tempfile.mkdtemp()
for k, caso in enumerate(CASOS):
    if SOLO is not None and k != SOLO:
        continue
    if caso["env"] and SOLO is None:
        # el caso pide variables al importar: proceso propio
        env = dict(os.environ)
        env.update(caso["env"])
        f2 = SALIDA + f".{k}"
        subprocess.run([sys.executable, __file__, sys.argv[1], f2, str(k)],
                       env=env)
        res.extend(json.load(open(f2)))
        continue
    ns = {"pl": pl, "pa": pa, "np": np, "io": io, "TMP": tmp,
          "Decimal": Decimal, "date": date, "datetime": datetime,
          "timedelta": timedelta, "crea_enum": crea_enum}
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        try:
            exec(caso["codigo"], ns)
            fila = {"ok": True, "valor": canon(ns.get("r"))}
        except BaseException as e:
            fila = {"ok": False, "error": type(e).__name__,
                    "mensaje": str(e).strip().split("\n")[0][:300]}
    fila["avisos"] = sorted({f"{a.category.__name__}: "
                             f"{str(a.message).splitlines()[0][:160]}"
                             for a in avisos})
    fila["k"] = k
    res.append(fila)
json.dump(res, open(SALIDA, "w"), default=str)
print("HECHO", len(res))
'''


def clasifica(a: dict, b: dict) -> str:
    """Clasifica el paso de una versión a otra para un caso.

    Args:
        a: resultado en la versión de partida.
        b: resultado en la versión de llegada.

    Returns:
        Una de: silencioso, error nuevo, error que desaparece, igual,
        error en ambas.
    """
    if a["ok"] and b["ok"]:
        return "igual" if a["valor"] == b["valor"] else "silencioso"
    if a["ok"]:
        return "error nuevo"
    if b["ok"]:
        return "error que desaparece"
    return "error en ambas"


def _norm(x):
    """Iguala decimales escritos con distinta escala («10» y «10.0»)."""
    if isinstance(x, str) and x.startswith("Decimal:"):
        from decimal import Decimal
        return ("Decimal", Decimal(x[8:]))
    if isinstance(x, list):
        return [_norm(v) for v in x]
    if isinstance(x, dict):
        return {k: _norm(v) for k, v in x.items()}
    return x


def naturaleza(a: dict, b: dict) -> str:
    """Dice qué cambia entre dos resultados sin error.

    Args:
        a: resultado en la versión de partida.
        b: resultado en la versión de llegada.

    Returns:
        Lista separada por comas de lo que cambia, o cadena vacía.
    """
    if not (a["ok"] and b["ok"]) or a["valor"] == b["valor"]:
        return ""
    va, vb = a["valor"], b["valor"]
    if isinstance(va, str) and va.startswith("digraph"):
        return "presentación (dibujo del plan)"
    if isinstance(va, list) and va and all(isinstance(x, bool)
                                           for x in va):
        return "orden de filas"
    if isinstance(va, dict) and isinstance(vb, dict) and \
            va.get("tipo") != vb.get("tipo"):
        return "clase de objeto (DataFrame a Series)"
    partes = []
    if isinstance(va, dict) and va.get("tipo") == "DataFrame":
        ea, eb = va["esquema"], vb["esquema"]
        fa, fb = _norm(va["filas"]), _norm(vb["filas"])
        if list(ea) != list(eb):
            partes.append("nombres de columna")
        if list(ea.values()) != list(eb.values()):
            partes.append("tipos")
        if fa != fb:
            if len(fa) != len(fb):
                partes.append("número de filas")
            elif sorted(map(str, fa)) == sorted(map(str, fb)):
                partes.append("orden de filas")
            else:
                partes.append("valores")
        return ", ".join(partes)
    if isinstance(va, dict) and va.get("tipo") == "Series":
        if va["nombre"] != vb["nombre"]:
            partes.append("nombre")
        if va["dtype"] != vb["dtype"]:
            partes.append("tipos")
        if _norm(va["valores"]) != _norm(vb["valores"]):
            partes.append("valores")
        return ", ".join(partes)
    return "valores"
