"""Banco de pruebas: Polars 2.0 y DuckDB 2.0 frente a sus versiones 1.x.

Punto de entrada reejecutable. Crea con uv un entorno aislado por versión,
genera los datos, ejecuta los cuatro bancos y escribe los resultados en CSV
junto a este fichero:

- a: repetición exacta del banco de agosto (30 M de filas, seis maneras de
  recorrerlas y seis motores), en frío y mediana de tres tandas; a_thp
  diagnostica el efecto de las páginas enormes sobre la misma lectura;
- b: TPC-H a SF10, 22 consultas, una tanda en frío y tres en caliente;
- c: agregaciones sobre TPC-H SF100 bajo un tope de memoria de 8 GiB, tres
  tandas; c_referencia repite una tanda con 14 GiB;
- d: cambios silenciosos de Polars 1.x a 2.0 según su guía de migración.

Uso:
    python generar.py --datos DIR [--entornos DIR] [--derrame DIR]
                      [--duckdb2 VERSION] [--sin-thp] [--prueba]
                      [--fases entornos datos a_thp a b c c_referencia d
                               resumen]

Con `--duckdb2 2.0.0` se repite todo con la versión estable de DuckDB en
cuanto salga. Los datos (unos 40 GB) y los entornos viven fuera de este
directorio; el volcado del banco c pide más de 64 GB libres. Semilla: 7.
"""

import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import csv  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import platform  # noqa: E402
import random  # noqa: E402
import shutil  # noqa: E402
import statistics  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from pathlib import Path  # noqa: E402

from tqdm import tqdm  # noqa: E402

import banco_agosto as ba  # noqa: E402
import banco_ram as br  # noqa: E402
import banco_tpch as bt  # noqa: E402
import cambios as bc  # noqa: E402
import comun  # noqa: E402
import resumen as rs  # noqa: E402

AQUI = Path(__file__).resolve().parent
SEMILLA = 7
# numpy y el mimalloc de pyarrow piden páginas enormes con madvise; con la
# memoria fragmentada, el núcleo compacta de forma síncrona en cada petición
SIN_THP = {"NUMPY_MADVISE_HUGEPAGE": "0", "MIMALLOC_ALLOW_THP": "0"}


def argumentos() -> argparse.Namespace:
    """Lee la línea de órdenes."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--datos", type=Path,
                   default=os.environ.get("BANCO_DATOS"),
                   help="directorio de trabajo para datos (unos 40 GB)")
    p.add_argument("--entornos", type=Path,
                   default=Path(os.environ.get(
                       "BANCO_ENTORNOS",
                       Path.home() / ".cache" / "banco-polars-duckdb")),
                   help="directorio de los entornos de uv")
    p.add_argument("--duckdb2", default=comun.DUCKDB2,
                   help="versión de duckdb 2.0 (2.0.0 cuando sea estable)")
    p.add_argument("--fases", nargs="+",
                   default=["entornos", "datos", "a_thp", "a", "b", "c",
                            "c_referencia", "d", "resumen"])
    p.add_argument("--prueba", action="store_true",
                   help="tamaños pequeños; resultados en DATOS/prueba")
    p.add_argument("--agosto", type=Path, default=None,
                   help="carpeta con los ficheros de agosto, para cotejar")
    p.add_argument("--derrame", type=Path, default=None,
                   help="directorio del volcado a disco del banco c; mejor "
                        "en un disco con más de 64 GB libres")
    p.add_argument("--sin-thp", action="store_true",
                   help="en el banco a, NUMPY_MADVISE_HUGEPAGE=0 y "
                        "MIMALLOC_ALLOW_THP=0 en cada proceso, para que la "
                        "fragmentación de la memoria no entre en la medida "
                        "(ver a_diagnostico_thp.csv)")
    p.add_argument("--tandas", type=int, default=3)
    p.add_argument("--tope", type=float, default=20,
                   help="tope de memoria (GiB) de cada medida de a, b y d")
    p.add_argument("--tope-ram", type=float, default=8,
                   help="tope de memoria (GiB) del banco c")
    a = p.parse_args()
    if a.datos is None:
        p.error("falta --datos (o la variable BANCO_DATOS)")
    return a


class Banco:
    """Estado compartido por las fases: rutas, entornos y registro."""

    def __init__(self, a: argparse.Namespace):
        self.a = a
        self.prueba = a.prueba
        self.raiz = a.datos / ("prueba" if a.prueba else "")
        self.raiz.mkdir(parents=True, exist_ok=True)
        self.salida = self.raiz / "resultados" if a.prueba else AQUI
        self.salida.mkdir(parents=True, exist_ok=True)
        self.trabajo = self.raiz / "trabajo"
        self.log = comun.Registro(self.raiz / "registro.log")
        self.esp = comun.especificaciones(a.duckdb2)
        self.d2 = a.duckdb2
        self.sf = 0.1 if a.prueba else 10
        self.sf_ram = 1 if a.prueba else 100
        self.hijos_ram = 4 if a.prueba else 100
        self.tope_ram = 0.5 if a.prueba else a.tope_ram
        self.filas = 1_000_000 if a.prueba else 30_000_000
        self.lote = 200_000 if a.prueba else 2_000_000
        self.d_agosto = self.raiz / "agosto"
        self.d_tpch = self.raiz / "tpch" / f"sf{self.sf:g}"
        self.d_ram = self.raiz / "tpch" / f"sf{self.sf_ram:g}" / "lineitem"
        self.pb = self.raiz / "polars-benchmark"
        self.f_consultas = self.raiz / "tpch" / "consultas_duckdb.json"
        self.derrame = a.derrame or self.raiz / "derrame"
        random.seed(SEMILLA)

    def py(self, nombre: str) -> Path:
        return comun.py(self.a.entornos, nombre)

    def version(self, entorno: str, paquete: str) -> str:
        return self.versiones[entorno][paquete]

    def escribe(self, nombre: str, filas: list[dict]) -> Path:
        """Se guarda en csv y se muestran 15 observaciones al azar."""
        f = self.salida / nombre
        campos = []
        for fila in filas:
            for k in fila:
                if k not in campos:
                    campos.append(k)
        with open(f, "w", newline="", encoding="utf-8") as h:
            w = csv.DictWriter(h, fieldnames=campos)
            w.writeheader()
            w.writerows(filas)
        self.log(f"escrito {f.name}: {len(filas)} filas")
        rng = random.Random(SEMILLA)
        for fila in rng.sample(filas, min(15, len(filas))):
            print("   ", {k: fila[k] for k in list(fila)[:9]})
        return f


def fase_entornos(b: Banco) -> None:
    """Crea o comprueba los entornos y guarda sus versiones exactas."""
    b.versiones = comun.crea_entornos(b.a.entornos, b.esp, b.log)


def genera_agosto(b: Banco) -> list[dict]:
    """Genera la tabla de agosto con el código y las versiones de agosto."""
    fichs = ["datos.csv", "datos_snappy.parquet", "datos_zstd.parquet",
             "datos.arrow"]
    if not all((b.d_agosto / f).exists() for f in fichs):
        b.log(f"se genera la tabla de agosto ({b.filas:,} filas)")
        codigo = ba.GENERADOR.format(base=b.d_agosto, filas=b.filas,
                                     lote=b.lote)
        r = comun.mide(b.py("pandas-2.3.3"), codigo, tope_gib=b.a.tope,
                       trabajo=b.trabajo, limite_s=3600)
        if r.get("rc") != 0:
            raise RuntimeError(f"generación de agosto: {r}")
    filas = []
    for f in tqdm(fichs, desc="huellas de agosto"):
        ruta = b.d_agosto / f
        fila = {"fichero": f, "bytes": ruta.stat().st_size,
                "gib": round(ruta.stat().st_size / 1024**3, 3),
                "sha256": comun.sha256(ruta)}
        if b.a.agosto and (b.a.agosto / f).exists():
            fila["identico_a_agosto"] = (
                fila["sha256"] == comun.sha256(b.a.agosto / f))
        filas.append(fila)
    return filas


def genera_tpch(b: Banco) -> list[dict]:
    """Genera TPC-H a SF10 (una tabla por fichero) y lineitem a SF100."""
    d156 = b.py("duckdb-1.5.6")
    if not (b.d_tpch / "lineitem.parquet").exists():
        b.log(f"se genera TPC-H SF{b.sf:g}")
        codigo = bt.GENERA.format(dest=b.d_tpch, sf=b.sf, hijos=1, paso=0,
                                  solo=None, tablas=bt.TABLAS,
                                  memoria="14GB",
                                  temporal=b.raiz / "tmp-dbgen")
        r = comun.mide(d156, codigo, tope_gib=b.a.tope, trabajo=b.trabajo,
                       limite_s=7200)
        if r.get("rc") != 0:
            raise RuntimeError(f"generación TPC-H: {r}")
    if not b.f_consultas.exists():
        r = comun.mide(d156, bt.EXTRAE.format(salida=b.f_consultas),
                       tope_gib=b.a.tope, trabajo=b.trabajo)
        if r.get("rc") != 0:
            raise RuntimeError(f"extracción de consultas: {r}")
    if not (b.pb / ".git").exists():
        subprocess.run(["git", "clone", "-q", bt.PB_REPO, str(b.pb)],
                       check=True)
    subprocess.run(["git", "-C", str(b.pb), "checkout", "-q",
                    bt.PB_COMMIT], check=True)
    # lineitem a SF100 por pasos de dbgen, cuatro procesos a la vez
    hechos = {p.name for p in b.d_ram.glob("parte-*.parquet")}
    pendientes = [i for i in range(b.hijos_ram)
                  if f"parte-{i:03d}.parquet" not in hechos]

    def paso(i: int) -> dict:
        codigo = bt.GENERA.format(
            dest=b.d_ram.parent, sf=b.sf_ram, hijos=b.hijos_ram, paso=i,
            solo=["lineitem"], tablas=bt.TABLAS, memoria="3GB",
            temporal=b.raiz / f"tmp-dbgen-{i}")
        return comun.mide(d156, codigo, tope_gib=4, trabajo=b.trabajo,
                          limite_s=3600)

    if pendientes:
        b.log(f"se genera lineitem SF{b.sf_ram:g}: {len(pendientes)} pasos")
        with ThreadPoolExecutor(4) as ex:
            for r in tqdm(ex.map(paso, pendientes), total=len(pendientes),
                          desc="dbgen por pasos"):
                if r.get("rc") != 0:
                    raise RuntimeError(f"dbgen por pasos: {r}")
    filas = []
    for f in sorted(b.d_tpch.glob("*.parquet")):
        filas.append({"fichero": f"tpch-sf{b.sf:g}/{f.name}",
                      "bytes": f.stat().st_size,
                      "gib": round(f.stat().st_size / 1024**3, 3),
                      "sha256": ""})
    tam = sum(f.stat().st_size for f in b.d_ram.glob("*.parquet"))
    filas.append({"fichero": f"tpch-sf{b.sf_ram:g}/lineitem "
                  f"({b.hijos_ram} partes)", "bytes": tam,
                  "gib": round(tam / 1024**3, 3), "sha256": ""})
    return filas


def fase_datos(b: Banco) -> None:
    """Genera los tres conjuntos de datos y escribe tamanos.csv."""
    filas = genera_agosto(b) + genera_tpch(b)
    b.escribe("tamanos.csv", filas)


def _mediana(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def fase_a(b: Banco) -> None:
    """Banco a: seis maneras y seis motores, con el método de agosto."""
    csv_p = b.d_agosto / "datos.csv"
    pqf = b.d_agosto / "datos_snappy.parquet"
    arr = b.d_agosto / "datos.arrow"
    trabajos = []
    for ent in [f"pandas-{v}" for v in comun.PANDAS]:
        for nombre, cod in ba.PRUEBAS.items():
            trabajos.append(("seis", nombre, ent, cod,
                             ba.fichero_prueba(nombre), None))
    for nombre, cod in ba.MOTORES.items():
        fam = ba.FAMILIA_MOTOR[nombre]
        ents = {"pandas": [f"pandas-{v}" for v in comun.PANDAS],
                "polars": [f"polars-{v}" for v in comun.POLARS],
                "duckdb": ["duckdb-1.5.5", "duckdb-1.5.6",
                           f"duckdb-{b.d2}"]}[fam]
        for ent in ents:
            trabajos.append(("motores", nombre, ent, cod,
                             ba.fichero_motor(nombre),
                             ba.calienta_motor(nombre)))
    for nombre, (ent, cod) in ba.EXTRA.items():
        trabajos.append(("extra", nombre, ent, cod, "datos.csv", None))
    filas = []
    for bloque, nombre, ent, cod, fenf, fcal in tqdm(trabajos,
                                                     desc="banco a"):
        codigo = cod.format(csv=csv_p, pqf=pqf, arr=arr) + ba.EPILOGO
        for tanda in range(1, b.a.tandas + 1):
            if fcal:
                with open(b.d_agosto / fcal, "rb") as h:
                    while h.read(1 << 24):
                        pass
            env = SIN_THP if b.a.sin_thp else {}
            r = comun.mide(b.py(ent), codigo, enfriar=[b.d_agosto / fenf],
                           tope_gib=b.a.tope, trabajo=b.trabajo,
                           limite_s=900, env=env)
            m = comun.marcas(r.get("stdout", ""))
            ultimas = [x for x in r.get("stdout", "").split()
                       if x.isdigit()]
            filas.append({
                "bloque": bloque, "prueba": nombre, "entorno": ent,
                "pandas": b.versiones[ent].get("pandas", ""),
                "pyarrow": b.versiones[ent].get("pyarrow", ""),
                "polars": b.versiones[ent].get("polars", ""),
                "duckdb": b.versiones[ent].get("duckdb", ""),
                "tanda": tanda, "enfriado": fenf,
                "precalentado": fcal or "",
                "segundos": round(r["seg_pared"], 3) if r.get("rc") == 0
                else None,
                "pico_rss_mb": round(int(m["RSS_KB"]) / 1024, 1)
                if "RSS_KB" in m else None,
                "filas": ultimas[-2] if len(ultimas) >= 2 else "",
                "rc": r.get("rc"),
                "swap_entradas": r.get("swap_entradas"),
                "swap_salidas": r.get("swap_salidas"),
                "compact_stall": r.get("vmstat", {}).get("compact_stall"),
                "paginas_enormes": " ".join(f"{k}={v}" for k, v in
                                            SIN_THP.items())
                if b.a.sin_thp else "predeterminado",
                "error": "" if r.get("rc") == 0
                else r.get("stderr", "")[-300:]})
            b.log(f"a {bloque} {nombre} {ent} t{tanda}: "
                  f"{filas[-1]['segundos']} s, {filas[-1]['pico_rss_mb']} MB")
    b.escribe("a_tandas.csv", filas)
    resumen = []
    claves = []
    for f in filas:
        k = (f["bloque"], f["prueba"], f["entorno"])
        if k not in claves:
            claves.append(k)
    for k in claves:
        grupo = [f for f in filas if (f["bloque"], f["prueba"],
                                      f["entorno"]) == k]
        seg = _mediana([f["segundos"] for f in grupo])
        rss = _mediana([f["pico_rss_mb"] for f in grupo])
        ago = ba.AGOSTO.get((k[0], k[1]))
        fila = {"bloque": k[0], "prueba": k[1], "entorno": k[2],
                "tandas": len(grupo), "segundos_mediana": seg,
                "pico_rss_mb_mediana": rss,
                "agosto_segundos": ago[0] if ago else "",
                "agosto_pico_rss_mb": ago[1] if ago else ""}
        if ago and seg:
            fila["dif_segundos_pct"] = round(100 * (seg / ago[0] - 1), 1)
        if ago and rss:
            fila["dif_rss_pct"] = round(100 * (rss / ago[1] - 1), 1)
        resumen.append(fila)
    b.escribe("a_resumen.csv", resumen)


def fase_a_thp(b: Banco) -> None:
    """Diagnóstico de la lectura completa del CSV frente a agosto.

    Se alterna la medida normal con `NUMPY_MADVISE_HUGEPAGE=0`, que impide
    a numpy pedir páginas enormes con madvise, y se anotan los contadores
    de compactación del sistema durante cada tanda.
    """
    csv_p = b.d_agosto / "datos.csv"
    pqf = b.d_agosto / "datos_snappy.parquet"
    trabajos = [("csv_pandas", e, v, t)
                for e in ("pandas-2.3.3", "pandas-3.0.6")
                for t in range(1, b.a.tandas + 1)
                for v in ("predeterminado", "NUMPY_MADVISE_HUGEPAGE=0")]
    trabajos += [("parquet_completo", e, v, t)
                 for e in ("pandas-2.3.3", "pandas-3.0.6")
                 for t in range(1, b.a.tandas + 1)
                 for v in ("predeterminado", "MIMALLOC_ALLOW_THP=0")]
    filas = []
    for prueba, ent, var, tanda in tqdm(trabajos, desc="diagnóstico THP"):
        env = {} if var == "predeterminado" else \
            dict([var.split("=")])
        codigo = ba.PRUEBAS[prueba].format(csv=csv_p, pqf=pqf) + ba.EPILOGO
        fich = csv_p if prueba.startswith("csv") else pqf
        r = comun.mide(b.py(ent), codigo, enfriar=[fich], env=env,
                       tope_gib=b.a.tope, trabajo=b.trabajo, limite_s=900)
        m = comun.marcas(r.get("stdout", ""))
        vm = r.get("vmstat", {})
        filas.append({
            "prueba": prueba, "entorno": ent,
            "pyarrow": b.versiones[ent].get("pyarrow", ""),
            "variable": var,
            "tanda": tanda,
            "segundos": round(r["seg_pared"], 3) if r.get("rc") == 0
            else None,
            "pico_rss_mb": round(int(m["RSS_KB"]) / 1024, 1)
            if "RSS_KB" in m else None,
            "compact_stall": vm.get("compact_stall"),
            "compact_fail": vm.get("compact_fail"),
            "thp_fault_alloc": vm.get("thp_fault_alloc"),
            "thp_fault_fallback": vm.get("thp_fault_fallback"),
            "swap_entradas": vm.get("pswpin"),
            "swap_salidas": vm.get("pswpout"), "rc": r.get("rc")})
        f = filas[-1]
        b.log(f"thp {prueba} {ent} {var} t{tanda}: {f['segundos']} s, "
              f"compact_stall {f['compact_stall']}")
    for ruta, clave in (("/sys/kernel/mm/transparent_hugepage/enabled",
                         "thp_enabled"),
                        ("/sys/kernel/mm/transparent_hugepage/defrag",
                         "thp_defrag")):
        try:
            valor = Path(ruta).read_text().strip()
        except OSError:
            valor = ""
        for f in filas:
            f[clave] = valor
    b.escribe("a_diagnostico_thp.csv", filas)


def configs_tpch(b: Banco) -> list[tuple]:
    """Configuraciones del banco b: (motor, entorno, modo)."""
    cs = []
    for v in comun.POLARS:
        alt = "streaming" if v.startswith("1.") else "in-memory"
        cs += [("polars", f"polars-{v}", "auto"),
               ("polars", f"polars-{v}", alt)]
    for v in ["1.5.5", "1.5.6", b.d2]:
        cs.append(("duckdb", f"duckdb-{v}", "predeterminado"))
    return cs


def fase_b(b: Banco) -> None:
    """Banco b: TPC-H, una tanda en frío y tres en caliente por consulta."""
    consultas = json.loads(b.f_consultas.read_text())
    d_sql = b.raiz / "tpch" / "sql"
    d_sql.mkdir(exist_ok=True)
    for n, s in consultas["consultas"].items():
        (d_sql / f"q{int(n):02d}.sql").write_text(s)
    d_res = b.raiz / "resultados_tpch"
    filas = []
    trabajos = [(c, q) for c in configs_tpch(b) for q in range(1, 23)]
    for (motor, ent, modo), q in tqdm(trabajos, desc="banco b"):
        etiqueta = f"{ent}-{modo}"
        (d_res / etiqueta).mkdir(parents=True, exist_ok=True)
        for tanda in range(0, b.a.tandas + 1):
            salida = d_res / etiqueta / f"q{q:02d}.json" if tanda == 1 \
                else ""
            if motor == "polars":
                codigo = bt.POLARS.format(raiz=b.pb, datos=b.d_tpch, q=q,
                                          motor=modo, salida=salida,
                                          sf=b.sf, tablas=bt.TABLAS)
            else:
                codigo = bt.DUCKDB.format(datos=b.d_tpch, salida=salida,
                                          fsql=d_sql / f"q{q:02d}.sql",
                                          tablas=bt.TABLAS)
            r = comun.mide(b.py(ent), codigo,
                           enfriar=[b.d_tpch] if tanda == 0 else [],
                           tope_gib=b.a.tope, muestreo=True,
                           trabajo=b.trabajo, limite_s=900)
            m = comun.marcas(r.get("stdout", ""))
            ok = r.get("rc") == 0 and "T_CONSULTA" in m
            filas.append({
                "motor": motor, "entorno": ent,
                "version": b.versiones[ent][motor], "modo": modo,
                "consulta": q, "tanda": tanda,
                "cache": "fría" if tanda == 0 else "caliente",
                "t_consulta_s": round(float(m["T_CONSULTA"]), 4)
                if ok else None,
                "seg_proceso": round(r["seg_pared"], 3)
                if r.get("seg_pared") else None,
                "pico_rss_mb": round(r.get("maxrss_hijo_kb", 0) / 1024, 1),
                "pico_anon_mb": round(r.get("max_rss_anon_kb", 0) / 1024,
                                      1),
                "filas": m.get("FILAS", ""), "rc": r.get("rc"),
                "agotado": r.get("agotado"),
                "oom_kill": r.get("cgroup", {}).get("events.oom_kill", ""),
                "swap_entradas": r.get("swap_entradas"),
                "swap_salidas": r.get("swap_salidas"),
                "error": "" if ok else
                (r.get("stderr", "") or r.get("error_lanzador", ""))[-300:]
                .replace("\n", " ")})
        f = filas[-1]
        b.log(f"b {etiqueta} q{q}: {f['t_consulta_s']} s, "
              f"{f['pico_rss_mb']} MB, rc {f['rc']}")
    b.escribe("b_tpch_tandas.csv", filas)
    resumen_b(b, filas, d_res, d_sql)


def resumen_b(b: Banco, filas: list[dict], d_res: Path, d_sql: Path) -> None:
    """Resume el banco b y comprueba que los motores coinciden."""
    resumen, coinc = [], []
    ref = d_res / "duckdb-1.5.6-predeterminado"
    for motor, ent, modo in configs_tpch(b):
        for q in range(1, 23):
            g = [f for f in filas if (f["entorno"], f["modo"],
                                      f["consulta"]) == (ent, modo, q)]
            fria = [f for f in g if f["tanda"] == 0]
            cal = [f for f in g if f["tanda"] > 0]
            resumen.append({
                "motor": motor, "entorno": ent,
                "version": b.versiones[ent][motor], "modo": modo,
                "consulta": q,
                "fria_s": fria[0]["t_consulta_s"] if fria else None,
                "caliente_mediana_s": _med4([f["t_consulta_s"]
                                             for f in cal]),
                "tandas_ok": sum(f["t_consulta_s"] is not None for f in g),
                "pico_rss_mb_max": max((f["pico_rss_mb"] for f in g),
                                       default=None),
                "pico_anon_mb_max": max((f["pico_anon_mb"] for f in g),
                                        default=None),
                "errores": "; ".join(sorted({f["error"][:120] for f in g
                                             if f["error"]}))})
            a = bt.lee(ref / f"q{q:02d}.json")
            c = bt.lee(d_res / f"{ent}-{modo}" / f"q{q:02d}.json")
            fila = {"entorno": ent, "modo": modo, "consulta": q,
                    "referencia": "duckdb-1.5.6"}
            tol = bt.TOL_REDONDEO if (motor == "polars" and
                                      q in bt.REDONDEADAS) else bt.TOL_ABS
            if a is None or c is None:
                fila.update(coincide=False, detalle="sin resultado")
            else:
                fila.update(bt.compara(a, c, tol))
            if q == 11 and motor == "polars" and not fila["coincide"]:
                fila["detalle"] += (": la extensión de duckdb fija la "
                                    "fracción en 0,0001 y polars-benchmark "
                                    "usa 0,0001/SF (b_tpch_q11_ajustada.csv)")
            coinc.append(fila)
    b.escribe("b_tpch_resumen.csv", resumen)
    b.escribe("b_tpch_coincidencia.csv", coinc)


def fase_b_comprobar(b: Banco) -> None:
    """Rehace resumen y coincidencias de b desde su CSV, sin medir."""
    with open(b.salida / "b_tpch_tandas.csv", encoding="utf-8") as h:
        filas = list(csv.DictReader(h))
    for f in filas:
        f["consulta"] = int(f["consulta"])
        f["tanda"] = int(f["tanda"])
        for k in ("t_consulta_s", "pico_rss_mb", "pico_anon_mb"):
            f[k] = float(f[k]) if f[k] not in ("", "None") else None
    resumen_b(b, filas, b.raiz / "resultados_tpch",
              b.raiz / "tpch" / "sql")
    fase_b_q11(b)


def _med4(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 4) if xs else None


def fase_b_q11(b: Banco) -> None:
    """Q11 de DuckDB con la fracción de la especificación (0,0001/SF).

    La extensión tpch fija 0,0001, el valor de SF1; polars-benchmark usa
    0,0001/SF. Se ejecuta una vez con la fracción ajustada para comprobar
    que la diferencia es del parámetro y no del motor.
    """
    d_sql = b.raiz / "tpch" / "sql"
    d_res = b.raiz / "resultados_tpch"
    sql = (d_sql / "q11.sql").read_text()
    fr = f"{0.0001 / b.sf:.10f}"
    ajustada = d_sql / "q11_ajustada.sql"
    ajustada.write_text(sql.replace("0.0001000000", fr))
    filas = []
    for ent in ["duckdb-1.5.6", f"duckdb-{b.d2}"]:
        salida = d_res / f"{ent}-q11-ajustada.json"
        codigo = bt.DUCKDB.format(datos=b.d_tpch, salida=salida,
                                  fsql=ajustada, tablas=bt.TABLAS)
        r = comun.mide(b.py(ent), codigo, tope_gib=b.a.tope,
                       trabajo=b.trabajo)
        for pol in [f"polars-{v}" for v in comun.POLARS]:
            for modo in ["auto", "streaming", "in-memory"]:
                c = bt.lee(d_res / f"{pol}-{modo}" / "q11.json")
                if c is None:
                    continue
                fila = {"duckdb": ent, "polars": f"{pol}-{modo}",
                        "fraccion": fr, "rc": r.get("rc")}
                fila.update(bt.compara(bt.lee(salida), c, bt.TOL_REDONDEO))
                filas.append(fila)
    b.escribe("b_tpch_q11_ajustada.csv", filas)


def configs_ram(b: Banco) -> list[tuple]:
    """Configuraciones del banco c: (motor, entorno, etiqueta, modo, env,
    vista)."""
    pres = str(int(b.tope_ram * 1024**3 * 0.8 / 1e6))
    cs = []
    for v in comun.POLARS:
        lista = br.CONF_POLARS["1" if v.startswith("1.") else "2"]
        lista = lista + br.CONF_POLARS.get(v, [])
        for etiqueta, modo, env in lista:
            env = {k: x.format(presupuesto_mb=pres) for k, x in env.items()}
            cs.append(("polars", f"polars-{v}", etiqueta, modo, env,
                       "contenedor"))
    cs.append(("polars", "polars-2.0.0", "predeterminado", "auto", {},
               "ámbito"))
    for v in ["1.5.5", "1.5.6", b.d2]:
        cs.append(("duckdb", f"duckdb-{v}", "predeterminado", "", {},
                   "contenedor"))
    return cs


def fase_c(b: Banco) -> None:
    """Banco c: tres agregaciones sobre lineitem SF100 con tope de 8 GiB."""
    filas = _banco_c(b, configs_ram(b), b.tope_ram, b.a.tandas)
    b.escribe("c_mayor_que_ram.csv", filas)
    b.escribe("c_resumen.csv", _resume_c(filas))


def fase_c_referencia(b: Banco) -> None:
    """Las mismas consultas con un tope holgado, para saber cuánto piden.

    Una tanda por configuración, solo los motores predeterminados de la
    última versión de cada serie y el streaming de Polars 1.44.2.
    """
    tope = 2 if b.prueba else 14
    elegidas = [c for c in configs_ram(b) if c[5] == "contenedor" and (
        (c[1] == "polars-1.44.2" and c[2] == "streaming") or
        (c[1] == "polars-2.0.0" and c[2] == "predeterminado") or
        c[1] in ("duckdb-1.5.6", f"duckdb-{b.d2}"))]
    filas = _banco_c(b, elegidas, tope, 1)
    b.escribe(f"c_referencia_{tope}gib.csv", filas)


def _resume_c(filas: list[dict]) -> list[dict]:
    """Cuántas tandas terminan y medianas de lo medido, por configuración."""
    claves = []
    for f in filas:
        k = (f["entorno"], f["configuracion"], f["vista_cgroup"],
             f["consulta"])
        if k not in claves:
            claves.append(k)
    out = []
    for k in claves:
        g = [f for f in filas if (f["entorno"], f["configuracion"],
                                  f["vista_cgroup"], f["consulta"]) == k]
        ok = [f for f in g if f["termina"]]
        out.append({
            "entorno": k[0], "configuracion": k[1], "vista_cgroup": k[2],
            "consulta": k[3], "tope_gib": g[0]["tope_gib"],
            "tandas": len(g), "terminan": len(ok),
            "causas": "; ".join(sorted({f["causa"] for f in g})),
            "t_consulta_mediana_s": _mediana([f["t_consulta_s"]
                                              for f in ok]),
            "pico_anon_mb_max": max(f["pico_anon_mb"] for f in g),
            "derrame_pico_mb_max": max(f["derrame_pico_mb"] for f in g),
            "escritos_mb_max": max(f["escritos_mb"] for f in g),
            "resultado": ok[0]["resultado"] if ok else ""})
    return out


def _banco_c(b: Banco, configs: list, tope: float, tandas: int) -> list:
    """Ejecuta las consultas c1, c2 y c3 con un tope y unas tandas."""
    glob = b.d_ram / "*.parquet"
    fq1 = b.raiz / "tpch" / "sql" / "q01.sql"
    filas = []
    trabajos = [(c, q, t) for c in configs for q in ("c1", "c2", "c3")
                for t in range(1, tandas + 1)]
    for conf, q, tanda in tqdm(trabajos, desc=f"banco c ({tope} GiB)"):
        motor, ent, etiq, modo, env, vista = conf
        nombre = f"{ent}-{etiq}-{vista}-{q}-t{tanda}".replace(" ", "_")
        dd = b.derrame / nombre
        shutil.rmtree(dd, ignore_errors=True)
        dd.mkdir(parents=True)
        env = dict(env)
        if motor == "polars":
            # se aparta el volcado de /var/tmp, que es el disco del sistema
            env["POLARS_OOC_SPILL_DIR"] = str(dd)
            codigo = br.POLARS.format(raiz=b.pb, glob=glob, consulta=q,
                                      motor=modo)
        else:
            codigo = br.DUCKDB.format(glob=glob, consulta=q, fq1=fq1)
        r = comun.mide(b.py(ent), codigo, enfriar=[b.d_ram],
                       tope_gib=tope, muestreo=True, dir_derrame=dd,
                       cwd=dd, env=env, trabajo=b.trabajo,
                       limite_s=300 if b.prueba else 1800,
                       vista_contenedor=(vista == "contenedor"))
        m = comun.marcas(r.get("stdout", ""))
        io_f = r.get("io_final", {})
        cg = r.get("cgroup", {})
        ok = r.get("rc") == 0 and "T_CONSULTA" in m
        if ok:
            causa = "termina"
        elif r.get("agotado"):
            causa = "tiempo agotado"
        elif cg.get("events.oom_kill", 0) > 0 or r.get("rc") == -9:
            causa = "OOM del cgroup"
        else:
            causa = "error"
        filas.append({
            "motor": motor, "entorno": ent,
            "version": b.versiones[ent][motor], "configuracion": etiq,
            "variables": " ".join(f"{k}={v}" for k, v in env.items()
                                  if k != "POLARS_OOC_SPILL_DIR"),
            "vista_cgroup": vista, "consulta": q, "tanda": tanda,
            "tope_gib": tope, "termina": ok, "causa": causa,
            "t_consulta_s": round(float(m["T_CONSULTA"]), 2) if ok else None,
            "seg_proceso": round(r.get("seg_pared", 0), 2),
            "pico_rss_mb": round(r.get("maxrss_hijo_kb", 0) / 1024, 1),
            "pico_anon_mb": round(r.get("max_rss_anon_kb", 0) / 1024, 1),
            "pico_cgroup_mb": round(int(cg.get("memory.peak", 0))
                                    / 1024**2, 1),
            "derrame_pico_mb": round(r.get("max_derrame_bytes", 0)
                                     / 1024**2, 1),
            "escritos_mb": round((io_f.get("write_bytes", 0)
                                  - io_f.get("cancelled_write_bytes", 0))
                                 / 1024**2, 1),
            "leidos_mb": round(io_f.get("read_bytes", 0) / 1024**2, 1),
            "limite_duckdb": m.get("LIMITE_DUCKDB", ""),
            "swap_entradas": r.get("swap_entradas"),
            "swap_salidas": r.get("swap_salidas"),
            "resultado": m.get("RESULTADO", ""),
            "error": "" if ok else
            (r.get("stderr", "") or r.get("error_lanzador", ""))[-300:]
            .replace("\n", " ")})
        f = filas[-1]
        b.log(f"c {nombre}: {f['causa']}, {f['t_consulta_s']} s, "
              f"anon {f['pico_anon_mb']} MB, derrame "
              f"{f['derrame_pico_mb']} MB")
        shutil.rmtree(dd, ignore_errors=True)
    return filas


def fase_d(b: Banco) -> None:
    """Banco d: batería de cambios en las tres versiones de Polars."""
    d = b.raiz / "cambios"
    d.mkdir(parents=True, exist_ok=True)
    hijo = d / "hijo.py"
    hijo.write_text(bc.HIJO)
    casos = [{"codigo": c[4], "env": c[5]} for c in bc.CASOS]
    f_casos = d / "casos.json"
    f_casos.write_text(json.dumps(casos))
    res = {}
    for v in tqdm(comun.POLARS, desc="banco d"):
        salida = d / f"res-{v}.json"
        p = subprocess.run([str(b.py(f"polars-{v}")), str(hijo),
                            str(f_casos), str(salida)],
                           capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"cambios {v}: {p.stderr[-800:]}")
        res[v] = {x["k"]: x for x in json.loads(salida.read_text())}
        b.log(f"d polars {v}: {len(res[v])} casos")

    def resume(x: dict) -> str:
        if not x["ok"]:
            return f"{x['error']}: {x['mensaje']}"[:400]
        return json.dumps(x["valor"], ensure_ascii=False,
                          default=str)[:400]

    filas = []
    for k, (n, bloq, tit, sub, cod, env) in enumerate(bc.CASOS):
        fila = {"apartado": n, "bloque": bc.BLOQUES[bloq], "titulo": tit,
                "subcaso": sub, "variables": json.dumps(env) if env else "",
                "codigo": cod.strip()}
        for v in comun.POLARS:
            fila[f"resultado_{v}"] = resume(res[v][k])
            fila[f"avisos_{v}"] = " | ".join(res[v][k]["avisos"])[:300]
        fila["clase_1.44.2_a_2.0.0"] = bc.clasifica(res["1.44.2"][k],
                                                    res["2.0.0"][k])
        fila["clase_1.43.1_a_2.0.0"] = bc.clasifica(res["1.43.1"][k],
                                                    res["2.0.0"][k])
        fila["que_cambia"] = bc.naturaleza(res["1.44.2"][k],
                                           res["2.0.0"][k])
        filas.append(fila)
    b.escribe("d_cambios_casos.csv", filas)
    # por apartado: basta un subcaso silencioso para contarlo como tal
    orden = ["silencioso", "error nuevo", "error que desaparece",
             "error en ambas", "igual"]
    apart = []
    for n in sorted({c[0] for c in bc.CASOS}):
        g = [f for f in filas if f["apartado"] == n]
        clases = {f["clase_1.44.2_a_2.0.0"] for f in g}
        apart.append({"apartado": n, "bloque": g[0]["bloque"],
                      "titulo": g[0]["titulo"], "subcasos": len(g),
                      "clase": next(c for c in orden if c in clases),
                      "que_cambia": "; ".join(sorted({
                          f["que_cambia"] for f in g if f["que_cambia"]})),
                      "clases_subcasos": "; ".join(
                          f"{f['subcaso'] or '-'}: "
                          f"{f['clase_1.44.2_a_2.0.0']}" for f in g)})
    b.escribe("d_cambios_apartados.csv", apart)


def fase_resumen(b: Banco) -> None:
    """Escribe entorno.json y contrasta las afirmaciones con lo medido."""
    cpu = ""
    for linea in open("/proc/cpuinfo"):
        if linea.startswith("model name"):
            cpu = linea.split(":", 1)[1].strip()
            break
    mem = 0
    for linea in open("/proc/meminfo"):
        if linea.startswith("MemTotal"):
            mem = int(linea.split()[1]) * 1024
    fs = subprocess.run(["findmnt", "-n", "-o", "FSTYPE", "--target",
                         str(b.raiz)], capture_output=True,
                        text=True).stdout.strip()
    rot = ""
    try:
        dev = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "--target",
                              str(b.raiz)], capture_output=True,
                             text=True).stdout.strip()
        padre = subprocess.run(["lsblk", "-n", "-d", "-o", "PKNAME,ROTA",
                                dev], capture_output=True,
                               text=True).stdout.split()
        rot = "rotacional" if padre and padre[-1] == "1" else "estado sólido"
    except OSError:
        pass
    consultas = json.loads(b.f_consultas.read_text()) \
        if b.f_consultas.exists() else {}
    uv = subprocess.run(["uv", "--version"], capture_output=True,
                        text=True).stdout.strip()
    motores = {}
    for e in b.esp:
        if e.startswith("duckdb-"):
            motores[e] = subprocess.run(
                [str(b.py(e)), "-c", "import duckdb; print(duckdb.sql("
                 "'SELECT version() || \\' \\' || source_id FROM "
                 "pragma_version()').fetchone()[0])"],
                capture_output=True, text=True).stdout.strip()
    thp = {}
    for k in ("enabled", "defrag"):
        try:
            thp[k] = Path(f"/sys/kernel/mm/transparent_hugepage/{k}") \
                .read_text().strip()
        except OSError:
            thp[k] = ""
    thp_a = ""
    if (b.salida / "a_tandas.csv").exists():
        with open(b.salida / "a_tandas.csv", encoding="utf-8") as h:
            thp_a = sorted({f.get("paginas_enormes", "")
                            for f in csv.DictReader(h)})
    ent = {
        "fecha": time.strftime("%Y-%m-%d"),
        "cpu": cpu, "hilos": os.cpu_count(),
        "ram_gib": round(mem / 1024**3, 1),
        "nucleo": platform.release(), "sistema": platform.system(),
        "sistema_ficheros_datos": fs, "tipo_disco_datos": rot,
        "python": comun.PYTHON, "uv": uv,
        "polars_benchmark_commit": bt.PB_COMMIT,
        "polars_benchmark_licencia": "Apache-2.0",
        "duckdb_motor": motores,
        "paginas_enormes_thp": thp,
        "paginas_enormes_en_a": thp_a,
        "extension_tpch": consultas.get("version_tpch", ""),
        "tope_memoria_gib_a_b_d": b.a.tope,
        "tope_memoria_gib_c": b.tope_ram,
        "semilla": SEMILLA,
        "entornos": b.versiones,
    }
    f = b.salida / "entorno.json"
    f.write_text(json.dumps(ent, indent=1, ensure_ascii=False) + "\n")
    b.log(f"escrito {f.name}")
    filas = rs.afirmaciones(b.salida)
    if filas:
        b.escribe("afirmaciones.csv", filas)


def main() -> None:
    a = argumentos()
    b = Banco(a)
    b.log(f"inicio: fases {a.fases}, prueba={a.prueba}, duckdb2={a.duckdb2}")
    if not comun.prepara_cgroup():
        b.log("aviso: sin systemd-run; las medidas corren sin tope")
    fases = {"entornos": fase_entornos, "datos": fase_datos, "a": fase_a,
             "a_thp": fase_a_thp,
             "b": fase_b, "b_comprobar": fase_b_comprobar, "c": fase_c,
             "c_referencia": fase_c_referencia, "d": fase_d,
             "resumen": fase_resumen}
    if "entornos" not in a.fases:
        fase_entornos(b)
    for f in a.fases:
        t0 = time.time()
        b.log(f"fase {f}")
        fases[f](b)
        if f == "b":
            fase_b_q11(b)
        b.log(f"fase {f} terminada en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
