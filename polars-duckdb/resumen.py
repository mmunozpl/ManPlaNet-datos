"""Contraste de las afirmaciones de los fabricantes con lo medido.

Lee los CSV que escriben los bancos y produce `afirmaciones.csv`: cada fila
cita literalmente una afirmación (anuncio de Polars 2.0, notas de la versión
py-2.0.0, guía de migración, entradas de DuckDB del 17-08 y del 02-09-2026),
dice qué prueba la pone a prueba y deja la cifra medida con su CSV de origen.
"""

import csv
import math
import statistics
from pathlib import Path

# apartados de la guía que llevan el aviso «Danger» (16, contados a mano)
PELIGRO = [1, 6, 7, 8, 10, 11, 12, 13, 15, 19, 20, 21, 32, 34, 35, 44]

POLARS_ANUNCIO = "pola.rs/posts/announcing-polars-2 (02-09-2026)"
POLARS_NOTAS = "github.com/pola-rs/polars/releases/tag/py-2.0.0"
POLARS_GUIA = "docs.pola.rs/releases/upgrade/2"
DUCKDB_ALFA = "duckdb.org/2026/09/02/try-duckdb-20-alpha"
DUCKDB_AVANCE = "duckdb.org/2026/08/17/duckdb-20-highlights"


def lee(f: Path) -> list[dict]:
    """Lee un CSV a lista de diccionarios; vacía si no existe."""
    if not f.exists():
        return []
    with open(f, encoding="utf-8") as h:
        return list(csv.DictReader(h))


def _f(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def geo(xs: list[float]) -> float | None:
    """Media geométrica de valores positivos."""
    xs = [x for x in xs if x and x > 0]
    if not xs:
        return None
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def serie(res: list[dict], ent: str, modo: str, campo: str) -> dict:
    """Valores por consulta de una configuración del banco b."""
    return {int(r["consulta"]): _f(r[campo]) for r in res
            if r["entorno"] == ent and r["modo"] == modo}


def compara_b(res: list[dict], a: tuple, b: tuple,
              campo: str = "caliente_mediana_s") -> dict:
    """Cociente a/b sobre las consultas que terminan en ambas."""
    sa, sb = serie(res, *a, campo), serie(res, *b, campo)
    qs = [q for q in sa if sa[q] and sb.get(q)]
    if not qs:
        return {}
    cocientes = [sa[q] / sb[q] for q in qs]
    return {"consultas": len(qs),
            "suma_a": round(sum(sa[q] for q in qs), 3),
            "suma_b": round(sum(sb[q] for q in qs), 3),
            "cociente_sumas": round(sum(sa[q] for q in qs)
                                    / sum(sb[q] for q in qs), 2),
            "media_geometrica": round(geo(cocientes), 2),
            "b_gana": sum(c > 1 for c in cocientes),
            "b_gana_10pct": sum(c > 1.1 for c in cocientes),
            "b_pierde_10pct": sum(c < 1 / 1.1 for c in cocientes),
            "max": round(max(cocientes), 2),
            "min": round(min(cocientes), 2)}


def afirmaciones(salida: Path) -> list[dict]:
    """Construye las filas de afirmaciones.csv."""
    res = lee(salida / "b_tpch_resumen.csv")
    ram = lee(salida / "c_resumen.csv")
    apart = lee(salida / "d_cambios_apartados.csv")
    filas = []

    def fila(fuente, cita, prueba, medida, valor, origen):
        filas.append({"fuente": fuente, "cita": cita, "prueba": prueba,
                      "medida": medida, "valor": valor, "origen": origen})

    cita5 = ("In aggregate we expect the streaming engine to be easily 5x "
             "faster.")
    for v, im, st in [("2.0.0", "in-memory", "auto"),
                      ("1.44.2", "auto", "streaming")]:
        c = compara_b(res, (f"polars-{v}", im), (f"polars-{v}", st))
        if c:
            fila(POLARS_ANUNCIO, cita5,
                 f"TPC-H SF10, Polars {v}: in-memory frente a streaming, "
                 "mediana de tres tandas en caliente",
                 "cociente de la suma de tiempos (in-memory / streaming)",
                 c["cociente_sumas"], "b_tpch_resumen.csv")
            fila(POLARS_ANUNCIO, cita5, f"ídem, Polars {v}",
                 "media geométrica de los cocientes por consulta",
                 c["media_geometrica"], "b_tpch_resumen.csv")
            fila(POLARS_ANUNCIO, cita5, f"ídem, Polars {v}",
                 "consultas en que streaming es al menos 5 veces más rápido",
                 sum(1 for q, x in _cocientes(
                     res, (f"polars-{v}", im),
                     (f"polars-{v}", st)).items() if x >= 5),
                 "b_tpch_resumen.csv")
            fila(POLARS_ANUNCIO, cita5, f"ídem, Polars {v}",
                 "consultas en que streaming es más rápido (de "
                 f"{c['consultas']})", c["b_gana"], "b_tpch_resumen.csv")
    c = compara_b(res, ("polars-1.44.2", "auto"), ("polars-2.0.0", "auto"))
    if c:
        cita = ("Calling collect on a LazyFrame will now default to the "
                "streaming engine, leading to massive memory and "
                "performance improvements on most queries for users.")
        fila(POLARS_ANUNCIO, cita,
             "TPC-H SF10, motor predeterminado: 1.44.2 frente a 2.0.0",
             "cociente de la suma de tiempos en caliente (1.44.2 / 2.0.0)",
             c["cociente_sumas"], "b_tpch_resumen.csv")
        fila(POLARS_ANUNCIO, cita, "ídem",
             f"consultas más rápidas en 2.0.0 (de {c['consultas']})",
             c["b_gana"], "b_tpch_resumen.csv")
        m = compara_b(res, ("polars-1.44.2", "auto"),
                      ("polars-2.0.0", "auto"), "pico_anon_mb_max")
        r = compara_b(res, ("polars-1.44.2", "auto"),
                      ("polars-2.0.0", "auto"), "pico_rss_mb_max")
        fila(POLARS_ANUNCIO, cita, "ídem, memoria anónima de pico",
             "media geométrica del cociente de picos (1.44.2 / 2.0.0)",
             m.get("media_geometrica"), "b_tpch_resumen.csv")
        fila(POLARS_ANUNCIO, cita, "ídem, memoria anónima de pico",
             f"consultas con menos pico en 2.0.0 (de {m.get('consultas')})",
             m.get("b_gana"), "b_tpch_resumen.csv")
        fila(POLARS_ANUNCIO, cita, "ídem, pico de memoria residente",
             "media geométrica del cociente de picos (1.44.2 / 2.0.0)",
             r.get("media_geometrica"), "b_tpch_resumen.csv")
        ambos = _ambos(res)
        fila(POLARS_ANUNCIO, cita, "ídem",
             "consultas más rápidas y con menos pico anónimo en 2.0.0",
             ambos, "b_tpch_resumen.csv")
    d2 = sorted({r["entorno"] for r in res
                 if r["entorno"].startswith("duckdb-2")})
    for e in d2:
        c = compara_b(res, ("duckdb-1.5.6", "predeterminado"),
                      (e, "predeterminado"))
        if not c:
            continue
        cita = ("Most are expected to be fine, some are expected to "
                "complete visibly faster, and some might result in an "
                "error.")
        fila(DUCKDB_ALFA, cita, f"TPC-H SF10: DuckDB 1.5.6 frente a {e}",
             "cociente de la suma de tiempos en caliente (1.5.6 / 2.0)",
             c["cociente_sumas"], "b_tpch_resumen.csv")
        fila(DUCKDB_ALFA, cita, "ídem",
             "media geométrica de los cocientes por consulta",
             c["media_geometrica"], "b_tpch_resumen.csv")
        fila(DUCKDB_ALFA, cita, "ídem",
             "consultas al menos un 10 % más rápidas en 2.0",
             c["b_gana_10pct"], "b_tpch_resumen.csv")
        fila(DUCKDB_ALFA, cita, "ídem",
             "consultas al menos un 10 % más lentas en 2.0",
             c["b_pierde_10pct"], "b_tpch_resumen.csv")
        err = sum(1 for r in res if r["entorno"] == e and
                  int(r["tandas_ok"] or 0) < 4)
        fila(DUCKDB_ALFA, cita, "ídem", "consultas con algún error en 2.0",
             err, "b_tpch_resumen.csv")
    # banco c
    for r in ram:
        if r["entorno"] == "polars-2.0.0" and \
                r["configuracion"] == "predeterminado":
            fila(POLARS_NOTAS,
                 "Enable OOC by default with 80% of available RAM as "
                 "threshold (#29741)",
                 f"lineitem SF100 bajo tope de {r['tope_gib']} GiB, "
                 f"consulta {r['consulta']}, vista {r['vista_cgroup']}",
                 "tandas que terminan / pico anónimo MB / volcado pico MB",
                 f"{r['terminan']} de {r['tandas']} / "
                 f"{r['pico_anon_mb_max']} / {r['derrame_pico_mb_max']}",
                 "c_resumen.csv")
    for r in ram:
        if r["entorno"].startswith("duckdb") and r["consulta"] == "c3":
            fila(DUCKDB_AVANCE,
                 "aggregations now spill to disk when they outgrow memory "
                 "(#24499)",
                 f"máximo de l_comment por l_orderkey, SF100, tope "
                 f"{r['tope_gib']} GiB, {r['entorno']}",
                 "tandas que terminan / volcado pico MB / escritos MB",
                 f"{r['terminan']} de {r['tandas']} / "
                 f"{r['derrame_pico_mb_max']} / {r['escritos_mb_max']}",
                 "c_resumen.csv")
    # banco d
    if apart:
        sil = [int(a["apartado"]) for a in apart
               if a["clase"] == "silencioso"]
        fila(POLARS_GUIA,
             "This change may silently impact the results of your "
             "pipelines.",
             "un ejemplo mínimo por apartado, Polars 1.44.2 frente a 2.0.0",
             "apartados con aviso «Danger» que cambian sin error (de 16)",
             sum(1 for n in PELIGRO if n in sil), "d_cambios_apartados.csv")
        fila(POLARS_GUIA, "(sin aviso «Danger»)", "ídem",
             "apartados sin aviso que cambian sin error",
             sum(1 for n in sil if n not in PELIGRO),
             "d_cambios_apartados.csv")
    return filas


def _cocientes(res, a, b) -> dict:
    sa = serie(res, *a, "caliente_mediana_s")
    sb = serie(res, *b, "caliente_mediana_s")
    return {q: sa[q] / sb[q] for q in sa if sa[q] and sb.get(q)}


def _ambos(res) -> int:
    ta = serie(res, "polars-1.44.2", "auto", "caliente_mediana_s")
    tb = serie(res, "polars-2.0.0", "auto", "caliente_mediana_s")
    ma = serie(res, "polars-1.44.2", "auto", "pico_anon_mb_max")
    mb = serie(res, "polars-2.0.0", "auto", "pico_anon_mb_max")
    return sum(1 for q in ta if ta[q] and tb.get(q) and ma.get(q)
               and mb.get(q) and tb[q] < ta[q] and mb[q] < ma[q])


def mediana(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None
