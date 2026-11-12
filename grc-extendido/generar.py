# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "numpy==2.3.4",
#     "pandas==2.3.3",
#     "scipy==1.16.3",
#     "tqdm==4.67.1",
# ]
# ///
"""Competencias de GRC más allá del SGSI, medidas sobre datos reales.

Seis bloques, cada uno sobre una fuente pública:

1. ``competencias``: los ocho roles de gobierno, riesgo y cumplimiento del
   marco NICE (NIST SP 800-181r1, componentes v2.2.0): cuántas tareas,
   conocimientos y destrezas tiene cada uno, cuántos comparten y cuánto se
   parecen entre sí (índice de Jaccard).
2. ``requisitos``: cuántos requisitos añade subir de categoría, en las líneas
   base de NIST SP 800-53B (catálogo OSCAL) y en las medidas del anexo II del
   Esquema Nacional de Seguridad (RD 311/2022, texto consolidado del BOE).
3. ``incidentes``: la base comunitaria VERIS (VCDB, CC BY-SA 4.0): reparto de
   acciones y actores, peso de los socios y proveedores, e importes de pérdida
   declarados, con el ajuste lognormal que alimenta una simulación de Monte
   Carlo de pérdida anual.
4. ``muestreo``: tamaños de muestra para pruebas de control por atributos y su
   comprobación por simulación sobre la población real de VERIS.
5. ``proveedores``: vigencia de los certificados del registro público del ENS
   (medición ``ens-certificados`` de este repositorio).
6. ``privacidad``: artículos de seguridad en las resoluciones de la AEPD
   (medición ``aepd-correctivos`` de este repositorio).

Uso::

    uv run generar.py

Requisitos: uv (lee las dependencias de la cabecera) o Python 3.10 con numpy,
pandas, scipy y tqdm. Unos 10 MB de descarga.
"""

import argparse
import html
import io
import itertools
import json
import logging
import re
import time
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from tqdm import tqdm

DIR = Path(__file__).resolve().parent
DATA = DIR.parent
UA = "ManPlaNet-medicion/1.0 (+https://manpla.net; investigacion GRC)"
NICE = ("https://csrc.nist.gov/csrc/media/Projects/cprt/documents/nice/"
        "v2-2-0_nf_components.json")
OSCAL = ("https://raw.githubusercontent.com/usnistgov/oscal-content/main/"
         "nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_{}-baseline_profile.json")
BOE_ENS = "https://www.boe.es/buscar/act.php?id=BOE-A-2022-7191"
VCDB = ("https://github.com/vz-risk/VCDB/raw/master/data/joined/"
        "vcdb.json.zip")
FECHA_CORTE = date(2026, 11, 12)
SEMILLA = 20261112
# los ocho roles de la categoría de supervisión y gobierno que forman el GRC
ROLES = {
    "OG-WRL-002": "política y planificación",
    "OG-WRL-012": "evaluación de controles",
    "OG-WRL-013": "autorización de sistemas",
    "OG-WRL-008": "cumplimiento de privacidad",
    "OG-WRL-016": "auditoría de programas",
    "OG-WRL-017": "riesgo de la cadena de suministro",
    "OG-WRL-007": "dirección ejecutiva",
    "OG-WRL-006": "asesoría legal",
}
# hipótesis declaradas de la simulación: no salen de VERIS, que no tiene
# denominador para calcular frecuencias anuales
INCIDENTES_ANUALES = 0.3
AÑOS_SIMULADOS = 100_000
log = logging.getLogger("grc-extendido")


def bajar(url: str, destino: Path) -> Path:
    """Descarga un fichero si no está en la caché.

    Args:
        url: dirección del fichero.
        destino: ruta local.

    Returns:
        La ruta local del fichero.
    """
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for intento in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                destino.write_bytes(r.read())
                return destino
        except Exception as e:  # se reintenta con espera creciente
            log.warning("fallo %s (%s), intento %d", url, e, intento + 1)
            time.sleep(5 * (intento + 1))
    raise RuntimeError(f"no se pudo descargar {url}")


def competencias(cache: Path) -> dict:
    """Roles GRC del marco NICE: tamaños, solapes y núcleo común."""
    d = json.loads(bajar(NICE, cache / "nice-v2-2-0.json").read_text("utf-8"))
    els = {e["element_identifier"]: e for e in d["elements"]}
    rel = defaultdict(set)
    for r in d["relationships"]:
        s, t = r["source_element_identifier"], r["dest_element_identifier"]
        if (els.get(s, {}).get("element_type") == "work_role"
                and els.get(t, {}).get("element_type") in
                ("task", "knowledge", "skill")):
            rel[s].add(t)
    filas = []
    for k, nombre in ROLES.items():
        c = Counter(els[t]["element_type"] for t in rel[k])
        filas.append({"rol": k, "nombre_nice": els[k]["title"],
                      "nombre": nombre, "enunciados": len(rel[k]),
                      "tareas": c["task"], "conocimientos": c["knowledge"],
                      "destrezas": c["skill"]})
    pd.DataFrame(filas).to_csv(DIR / "nice_roles.csv", index=False)
    pares = []
    for a, b in itertools.combinations(ROLES, 2):
        inter, union = rel[a] & rel[b], rel[a] | rel[b]
        pares.append({"rol_a": a, "rol_b": b, "comunes": len(inter),
                      "jaccard": round(len(inter) / len(union), 3)})
    pd.DataFrame(pares).to_csv(DIR / "nice_solapes.csv", index=False)
    cuenta = Counter(t for k in ROLES for t in rel[k])
    enun = []
    for t, n in sorted(cuenta.items(), key=lambda x: (-x[1], x[0])):
        enun.append({"id": t, "tipo": els[t]["element_type"], "roles": n,
                     "en_roles": " ".join(k for k in ROLES if t in rel[k]),
                     "texto": els[t].get("text", "")})
    e = pd.DataFrame(enun)
    e.to_csv(DIR / "nice_enunciados.csv", index=False)
    doc = d["documents"][0]
    return {"version": doc.get("version"), "enunciados_union": len(e),
            "en_cuatro_o_mas": int((e.roles >= 4).sum()),
            "en_dos_o_mas": int((e.roles >= 2).sum()),
            "en_un_solo_rol": int((e.roles == 1).sum()),
            "en_todos": int((e.roles == len(ROLES)).sum()),
            "tks_marco": sum(1 for x in els.values() if x.get("element_type")
                             in ("task", "knowledge", "skill"))}


def requisitos(cache: Path) -> dict:
    """Requisitos por categoría: líneas base del NIST y medidas del ENS."""
    filas = []
    for base in ("LOW", "MODERATE", "HIGH", "PRIVACY"):
        p = json.loads(bajar(OSCAL.format(base),
                             cache / f"oscal-{base}.json").read_text("utf-8"))
        ids = [i for imp in p["profile"]["imports"]
               for inc in imp.get("include-controls", [])
               for i in inc.get("with-ids", [])]
        familias = Counter(i.split("-")[0].upper() for i in ids)
        filas.append({"marco": "NIST SP 800-53B", "nivel": base.lower(),
                      "requisitos": len(ids),
                      "controles": sum(1 for i in ids if "." not in i),
                      "mejoras": sum(1 for i in ids if "." in i),
                      "familias": len(familias)})
    # el anexo II del ENS: cada medida lleva una tabla con la categoría o el
    # nivel y sus refuerzos; se lee la primera tabla entre su título y el de la
    # medida siguiente. Los niveles se igualan a la categoría (hipótesis: un
    # sistema de categoría alta tiene alguna dimensión en nivel alto)
    s = bajar(BOE_ENS, cache / "ens.html").read_text("utf-8", errors="ignore")
    s = s[s.find("ANEXO II"):]
    titulos = list(re.finditer(
        r"\[(org\.\d+|(?:op|mp)\.[a-z]+\.\d+)\]\.?\s*</p>", s))
    medidas, vistos, compuestas = [], set(), []
    for i, m in enumerate(titulos):
        cod = m.group(1)
        if cod in vistos:
            continue
        vistos.add(cod)
        fin_seg = titulos[i + 1].start() if i + 1 < len(titulos) else len(s)
        tab = re.search(r'<table class="tabla">(.*?)</table>',
                        s[m.end():fin_seg], re.S)
        if not tab:
            compuestas.append(cod)
            continue
        celdas = [[re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c)))
                   .strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", f, re.S)]
                  for f in re.findall(r"<tr>(.*?)</tr>", tab.group(1), re.S)]
        if len(celdas) != 3 or len(celdas[2]) != 4 or celdas[1][0] not in (
                "categoría", "nivel"):
            compuestas.append(cod)
            continue
        previo = None
        for cat, v in zip(("básica", "media", "alta"), celdas[2][1:]):
            v = previo if v == "=" else v.replace(" ", "")
            previo = v
            aplica = v != "n.a."
            # un refuerzo a elegir entre varios ([R1oR2]) cuenta como uno
            refuerzos = (len(re.findall(r"R\d", re.sub(r"\[[^\]]*\]", "R0", v)))
                         if aplica else 0)
            medidas.append({"medida": cod, "por": celdas[1][0],
                            "categoria": cat, "valor": v,
                            "aplica": aplica, "refuerzos": refuerzos})
    md = pd.DataFrame(medidas)
    md.to_csv(DIR / "ens_medidas_categoria.csv", index=False)
    for cat, g in md.groupby("categoria", sort=False):
        filas.append({"marco": "ENS (RD 311/2022)", "nivel": cat,
                      "requisitos": int(g.aplica.sum() + g.refuerzos.sum()),
                      "controles": int(g.aplica.sum()),
                      "mejoras": int(g.refuerzos.sum()), "familias": 3})
    pd.DataFrame(filas).to_csv(DIR / "requisitos_categoria.csv", index=False)
    return {"ens_medidas_leidas": int(md.medida.nunique()),
            "ens_medidas_compuestas": compuestas,
            "ens_medidas_anexo": len(vistos)}


def incidentes(cache: Path) -> tuple[pd.DataFrame, dict]:
    """VERIS: acciones, actores, socios, importes y pérdida simulada."""
    z = zipfile.ZipFile(bajar(VCDB, cache / "vcdb.json.zip"))
    d = json.loads(z.read(z.namelist()[0]))
    filas = []
    for x in d:
        imp = x.get("impact", {}) or {}
        filas.append({
            "anio": x.get("timeline", {}).get("incident", {}).get("year"),
            "acciones": " ".join(sorted(x.get("action", {}).keys())),
            "actores": " ".join(sorted(x.get("actor", {}).keys())),
            "empleados": x.get("victim", {}).get("employee_count"),
            "descubrimiento": " ".join(sorted(
                (x.get("discovery_method") or {}).keys())),
            "importe": imp.get("overall_amount"),
            "moneda": imp.get("iso_currency_code"),
        })
    inc = pd.DataFrame(filas)
    n = len(inc)
    acc = Counter(a for s in inc.acciones for a in s.split())
    act = Counter(a for s in inc.actores for a in s.split())
    reparto = [{"campo": "accion", "valor": k, "incidentes": v,
                "pct": round(100 * v / n, 1)} for k, v in acc.most_common()]
    reparto += [{"campo": "actor", "valor": k, "incidentes": v,
                 "pct": round(100 * v / n, 1)} for k, v in act.most_common()]
    pd.DataFrame(reparto).to_csv(DIR / "veris_reparto.csv", index=False)
    por_anio = inc.groupby("anio").size().rename("incidentes").reset_index()
    por_anio.to_csv(DIR / "veris_por_anio.csv", index=False)
    # importes en dólares: la moneda más frecuente; no se convierte ninguna
    usd = inc[(inc.moneda == "USD") & (inc.importe > 0)].importe.astype(float)
    # se excluye por inverosímil todo importe superior a 10.000 millones de
    # dólares: hay uno, un billón atribuido a una organización de 1.001 a
    # 10.000 empleados
    excluidos = int((usd > 1e10).sum())
    usd_todos = usd.copy()
    usd = usd[usd <= 1e10]
    usd.sort_values().reset_index(drop=True).rename("importe_usd").to_csv(
        DIR / "veris_importes_usd.csv", index=False)
    mu, sigma = float(np.log(usd).mean()), float(np.log(usd).std(ddof=1))
    # simulación de pérdida anual: frecuencia de Poisson (hipótesis declarada)
    # y magnitud lognormal ajustada a los importes reales de VERIS
    rng = np.random.default_rng(SEMILLA)
    k = rng.poisson(INCIDENTES_ANUALES, AÑOS_SIMULADOS)
    total = np.zeros(AÑOS_SIMULADOS)
    idx = np.repeat(np.arange(AÑOS_SIMULADOS), k)
    np.add.at(total, idx, rng.lognormal(mu, sigma, k.sum()))
    umbrales = np.logspace(3, 9, 61)
    curva = pd.DataFrame({"perdida_usd": umbrales,
                          "prob_superar": [(total > u).mean() for u in umbrales]})
    curva.to_csv(DIR / "perdida_excedencia.csv", index=False)
    q = np.quantile(total, [0.5, 0.9, 0.95, 0.99])
    sens, ks_corr, ic = sensibilidad(usd_todos, usd, rng, total)
    res = {"incidentes": n, "con_importe": int(inc.importe.notna().sum()),
           "importes_usd": int(len(usd)), "importes_excluidos": excluidos,
           "usd_mediana": float(usd.median()), "usd_max": float(usd.max()),
           "lognormal_mu": round(mu, 3), "lognormal_sigma": round(sigma, 3),
           # el p de Kolmogórov-Smirnov con parámetros estimados de la misma
           # muestra no vale: se calibra por simulación, reajustando en cada una
           "ks_p_corregido": ks_corr,
           "p95_ic": ic["p95"], "p99_ic": ic["p99"],
           "incidentes_anuales_hipotesis": INCIDENTES_ANUALES,
           "anios_simulados": AÑOS_SIMULADOS,
           "perdida_esperada": float(total.mean()),
           "anios_sin_perdida_pct": round(100 * float((total == 0).mean()), 1),
           # parte de toda la pérdida simulada que cae en el 1 % y el 5 % de
           # los años con más pérdida
           "pct_perdida_top1": round(100 * float(total[total >= np.quantile(
               total, .99)].sum() / total.sum()), 1),
           "pct_perdida_top5": round(100 * float(total[total >= np.quantile(
               total, .95)].sum() / total.sum()), 1),
           "p50": float(q[0]), "p90": float(q[1]), "p95": float(q[2]),
           "p99": float(q[3]),
           "socio_pct": round(100 * act["partner"] / n, 1),
           "socio_incidentes": act["partner"]}
    return inc, res


def anual(rng: np.random.Generator, muestreador, anios: int) -> np.ndarray:
    """Pérdida de cada año simulado con frecuencia de Poisson."""
    k = rng.poisson(INCIDENTES_ANUALES, anios)
    total = np.zeros(anios)
    np.add.at(total, np.repeat(np.arange(anios), k), muestreador(k.sum()))
    return total


def sensibilidad(usd_todos: pd.Series, usd: pd.Series, rng: np.random.Generator,
                 base: np.ndarray) -> tuple[pd.DataFrame, float, dict]:
    """Sensibilidad de los percentiles al modelo y a la regla de exclusión.

    Args:
        usd_todos: importes en dólares sin excluir ninguno.
        usd: importes tras la regla de exclusión (hasta 10.000 millones).
        rng: generador aleatorio con la semilla de la medición.
        base: pérdidas anuales de la simulación principal, que se reutiliza
            para el escenario de la regla de la medición.

    Returns:
        La tabla de escenarios, el p de Kolmogórov-Smirnov calibrado por
        simulación y los intervalos de remuestreo de P95 y P99.
    """
    def lognormal(x):
        lx = np.log(x)
        m, sd = float(lx.mean()), float(lx.std(ddof=1))
        return m, sd, (lambda n: rng.lognormal(m, sd, n))

    filas = []
    escenarios = [
        ("lognormal, regla de la medición (hasta 10.000 M$)", usd),
        ("lognormal, sin excluir ningún importe", usd_todos),
        ("lognormal, excluidos los importes de más de 100 M$", usd[usd <= 1e8]),
    ]
    for i, (nombre, x) in enumerate(escenarios):
        m, sd, f = lognormal(x.to_numpy())
        t = base if i == 0 else anual(rng, f, AÑOS_SIMULADOS)
        filas.append({"escenario": nombre, "importes": len(x), "mu": round(m, 3),
                      "sigma": round(sd, 3), "p95": float(np.quantile(t, .95)),
                      "p99": float(np.quantile(t, .99)), "media": float(t.mean())})
    emp = usd.to_numpy()
    t = anual(rng, lambda n: rng.choice(emp, n, replace=True), AÑOS_SIMULADOS)
    filas.append({"escenario": "sin modelo: remuestreo de los importes reales",
                  "importes": len(emp), "mu": None, "sigma": None,
                  "p95": float(np.quantile(t, .95)),
                  "p99": float(np.quantile(t, .99)), "media": float(t.mean())})
    tab = pd.DataFrame(filas)
    tab.to_csv(DIR / "perdida_sensibilidad.csv", index=False)
    lx = np.log(emp)
    try:
        gof = stats.goodness_of_fit(stats.norm, lx, statistic="ks",
                                    n_mc_samples=9999, rng=rng)
    except TypeError:  # versiones de scipy anteriores a 1.15
        gof = stats.goodness_of_fit(stats.norm, lx, statistic="ks",
                                    n_mc_samples=9999, random_state=rng)
    # incertidumbre de los percentiles: se reajusta la lognormal a 400
    # remuestras de los importes y se simulan 20.000 años con cada una
    p95, p99 = [], []
    for _ in range(400):
        r = rng.choice(lx, len(lx), replace=True)
        m, sd = r.mean(), r.std(ddof=1)
        t = anual(rng, lambda n: rng.lognormal(m, sd, n), 20_000)
        p95.append(np.quantile(t, .95)); p99.append(np.quantile(t, .99))
    ic = {"p95": [float(np.quantile(p95, .025)), float(np.quantile(p95, .975))],
          "p99": [float(np.quantile(p99, .025)), float(np.quantile(p99, .975))]}
    return tab, round(float(gof.pvalue), 3), ic


def tamano_cero_desvios(p_tol: float, conf: float, k: int) -> int:
    """Menor muestra que permite concluir tasa < p_tol con k desvíos."""
    n = k + 1
    while stats.binom.cdf(k, n, p_tol) > 1 - conf:
        n += 1
    return n


def muestreo(inc: pd.DataFrame) -> dict:
    """Muestras para pruebas de control y su comprobación con VERIS."""
    rng = np.random.default_rng(SEMILLA)
    filas = []
    for conf in (0.90, 0.95):
        for p_tol in (0.05, 0.10):
            for k in (0, 1, 2):
                filas.append({"confianza": conf, "tasa_tolerable": p_tol,
                              "desvios_admitidos": k,
                              "muestra": tamano_cero_desvios(p_tol, conf, k)})
    tab = pd.DataFrame(filas)
    tab.to_csv(DIR / "muestras_atributos.csv", index=False)
    # población real: incidentes con un socio o proveedor entre los actores
    socio = inc.actores.str.contains("partner").to_numpy()
    p_real = socio.mean()
    sim = []
    for k in (0, 1, 2):
        n = tamano_cero_desvios(0.05, 0.95, k)
        aprob = 0
        for _ in range(10_000):
            m = rng.choice(len(socio), n, replace=False)
            aprob += socio[m].sum() <= k
        sim.append({"desvios_admitidos": k, "muestra": n,
                    "tasa_real_pct": round(100 * p_real, 2),
                    "aprobadas_pct": round(100 * aprob / 10_000, 1),
                    "aprobadas_teorico_pct": round(
                        100 * stats.binom.cdf(k, n, p_real), 1)})
    # estimación de una proporción: incidentes con un error entre las acciones
    err = inc.acciones.str.contains("error").to_numpy()
    p_err = err.mean()
    n_est = int(np.ceil(1.96 ** 2 * p_err * (1 - p_err) / 0.05 ** 2))
    cubre = 0
    for _ in range(10_000):
        m = err[rng.choice(len(err), n_est, replace=False)]
        ph = m.mean()
        mitad = 1.96 * np.sqrt(ph * (1 - ph) / n_est)
        cubre += (ph - mitad) <= p_err <= (ph + mitad)
    pd.DataFrame(sim).to_csv(DIR / "muestreo_simulado.csv", index=False)
    return {"socio_tasa_real_pct": round(100 * p_real, 2),
            "error_tasa_real_pct": round(100 * p_err, 2),
            "muestra_estimacion": n_est,
            "cobertura_ic95_pct": round(100 * cubre / 10_000, 1)}


def proveedores() -> dict:
    """Vigencia de los certificados del registro del ENS."""
    c = pd.read_csv(DATA / "ens-certificados" / "salidas" / "certificados.csv")
    c = c[c.listado == "categoria"].copy()
    venc = pd.to_datetime(c.fecha_vencimiento, errors="coerce")
    # el corte es el día en que se leyó el registro, no el de hoy
    vol = json.loads((DATA / "ens-certificados" / "salidas" / "volumenes.json")
                     .read_text("utf-8"))
    corte = pd.Timestamp(vol["fecha_consulta"])
    c["estado"] = np.select(
        [venc.isna(), venc < corte, venc < corte + pd.Timedelta(days=90)],
        ["sin fecha", "vencido", "vence en 90 días"], "vigente")
    t = (c.groupby(["categoria", "estado"]).size().rename("certificados")
         .reset_index())
    t.to_csv(DIR / "ens_vigencia.csv", index=False)
    m = (venc.dt.to_period("M").astype(str).value_counts().sort_index()
         .rename_axis("mes").rename("vencimientos").reset_index())
    m.to_csv(DIR / "ens_vencimientos_mes.csv", index=False)
    return {"fecha_registro": vol["fecha_consulta"],
            "certificados_categoria": int(len(c)),
            "vencidos": int((c.estado == "vencido").sum()),
            "vencen_90_dias": int((c.estado == "vence en 90 días").sum()),
            "sin_fecha": int((c.estado == "sin fecha").sum())}


def privacidad() -> dict:
    """Artículos de seguridad en las resoluciones de la AEPD."""
    r = pd.read_csv(DATA / "aepd-correctivos" / "salidas" / "resoluciones.csv")
    arts = r.articulos.fillna("")
    claves = {"5.1.f) integridad y confidencialidad": r"5\.1\.f\)",
              "25 protección desde el diseño": r"(?<![\d.])25(?:\.\d)? RGPD",
              "32 seguridad del tratamiento": r"(?<![\d.])32(?:\.\d)? RGPD",
              "33 notificación a la autoridad": r"(?<![\d.])33(?:\.\d)? RGPD",
              "34 comunicación a los afectados": r"(?<![\d.])34(?:\.\d)? RGPD",
              "35 evaluación de impacto": r"(?<![\d.])35(?:\.\d)? RGPD"}
    filas = []
    for nombre, pat in claves.items():
        sel = arts.str.contains(pat, regex=True)
        filas.append({"articulo": nombre, "resoluciones": int(sel.sum()),
                      "pct": round(100 * sel.mean(), 1),
                      "importe_final_eur": float(r.loc[sel, "importe_final"]
                                                 .fillna(0).sum())})
    seg = arts.str.contains("|".join(claves.values()), regex=True)
    pd.DataFrame(filas).to_csv(DIR / "aepd_articulos_seguridad.csv",
                               index=False)
    return {"resoluciones": int(len(r)),
            "con_articulo_de_seguridad": int(seg.sum()),
            "pct_seguridad": round(100 * seg.mean(), 1),
            "importe_seguridad_eur": float(r.loc[seg, "importe_final"]
                                           .fillna(0).sum()),
            "importe_total_eur": float(r.importe_final.fillna(0).sum())}


def main() -> None:
    """Punto de entrada."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", type=Path, default=DIR / "descargas")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    res = {"fecha_corte": FECHA_CORTE.isoformat(), "semilla": SEMILLA}
    pasos = tqdm(["competencias", "requisitos", "incidentes", "muestreo",
                  "proveedores", "privacidad"], desc="bloques")
    for paso in pasos:
        if paso == "competencias":
            res["nice"] = competencias(a.cache)
        elif paso == "requisitos":
            res["requisitos"] = requisitos(a.cache)
        elif paso == "incidentes":
            inc, res["veris"] = incidentes(a.cache)
        elif paso == "muestreo":
            res["muestreo"] = muestreo(inc)
        elif paso == "proveedores":
            res["proveedores"] = proveedores()
        else:
            res["privacidad"] = privacidad()
    (DIR / "resumen.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log.info("salidas escritas en %s", DIR)


if __name__ == "__main__":
    main()
