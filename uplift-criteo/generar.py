"""Incrementalidad publicitaria medida sobre el dato de uplift de Criteo.

El dato es el conjunto que publica Criteo AI Lab con el artículo de Diemert,
Betlei, Renaudin y Amini (AdKDD 2018) y su versión ampliada (arXiv
2111.10106): 13.979.592 filas, una por usuario de varias pruebas de
incrementalidad (experimentos aleatorizados en los que una parte de la
población se queda sin publicidad), con doce atributos anonimizados y las
columnas ``treatment``, ``exposure``, ``visit`` y ``conversion``. Licencia
CC BY-NC-SA 4.0. Los agregados que escribe este guion se derivan de ese
conjunto y se publican con la misma licencia.

La dirección oficial (go.criteo.net) redirige a un almacén que ya no
resuelve, de modo que la descarga se hace de la copia que publica la propia
Criteo en su organización verificada de Hugging Face, fijada a una revisión
y comprobada por su SHA-256.

Etapas, todas reejecutables (el crudo se guarda en ``crudo/``):

1. ``descarga``: el CSV comprimido, con su huella.
2. ``diseno``: grupos, equilibrio de los atributos, comparación ingenua de
   expuestos y no expuestos, efecto sobre los expuestos (estimador de
   Wald), ajuste por regresión de Lin y prueba de dos muestras con
   clasificador.
3. ``contrastes``: prueba z, t de Welch, Mann-Whitney, permutación y
   bootstrap sobre los catorce millones de filas.
4. ``cobertura``: qué ocurre con esas pruebas en submuestras pequeñas.
5. ``potencia``: tamaño de muestra analítico comprobado por Monte Carlo, y
   el efecto mínimo detectable de una encuesta de *brand lift*.
6. ``modelos``: siete modelos de uplift (S, T, X y transformación de
   clase; logística y HistGradientBoosting), curvas Qini, calibración y
   separabilidad por tamaño de prueba.
7. ``segmentos``: k-medias sobre las predicciones del X-learner y sobre
   los atributos, y deciles del uplift predicho.
8. ``escala``: el cálculo central en SQL con DuckDB sobre el CSV y sobre
   Parquet, frente a pandas.

Uso, desde la raíz del repositorio de datos::

    uv sync --frozen --group generadores
    uv run python uplift-criteo/generar.py                 # todas
    uv run python uplift-criteo/generar.py --etapa modelos # una sola

Requisitos: unos 300 MB de descarga y 12 GB de memoria (pico medido de
12,2 GB); la ejecución completa tardó 17 minutos y medio en un ordenador de
sobremesa de 32 hilos, nueve de ellos en la etapa de modelos.
"""

import argparse
import hashlib
import json
import logging
import os
import platform
import time
import urllib.request
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy import stats
from scipy.special import gammaln
from sklearn.cluster import KMeans
from sklearn.ensemble import (HistGradientBoostingClassifier,
                              HistGradientBoostingRegressor)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, silhouette_score
from tqdm import tqdm

DIR = Path(__file__).resolve().parent
CRUDO = DIR / "crudo"
UA = "Mozilla/5.0"
# la dirección que da la página de Criteo AI Lab; redirige a un almacén de
# Azure que el 16-11-2026 ya no resolvía (NXDOMAIN)
URL_OFICIAL = "http://go.criteo.net/criteo-research-uplift-v2.1.csv.gz"
# la copia de la organización verificada de Criteo en Hugging Face, fijada
# a la revisión 2424920019e49d52d72c13ac1143ec5d53af276b
REVISION = "2424920019e49d52d72c13ac1143ec5d53af276b"
URL = ("https://huggingface.co/datasets/criteo/criteo-uplift/resolve/"
       f"{REVISION}/criteo-research-uplift-v2.1.csv.gz")
FICHERO = CRUDO / "criteo-research-uplift-v2.1.csv.gz"
PARQUET = CRUDO / "criteo-uplift-v2.1.parquet"
PREDICCIONES = CRUDO / "predicciones_prueba.npz"
SHA256 = "2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc"
BYTES = 311_422_618
# cifras clave que publica Criteo para la versión 2.1
CLAVE = {"filas": 13_979_592, "visita": 0.046992, "conversion": 0.00292,
         "tratamiento": 0.85}
ATRIBUTOS = [f"f{i}" for i in range(12)]
SEMILLA = 2026
Z = stats.norm.ppf(0.975)
log = logging.getLogger("uplift-criteo")


# --- utilidades --------------------------------------------------------------

def mostrar(df: pd.DataFrame, nombre: str, k: int = 15) -> None:
    """Muestra k filas al azar de un artefacto recién escrito.

    Args:
        df: tabla escrita.
        nombre: nombre del fichero, para el rótulo.
        k: filas que se muestran.
    """
    print(f"\n--- {nombre}: {len(df)} filas; {min(k, len(df))} al azar ---")
    with pd.option_context("display.width", 160, "display.max_columns", 30):
        print(df.sample(min(k, len(df)), random_state=SEMILLA).to_string())


def guardar(df: pd.DataFrame, nombre: str) -> None:
    """Escribe un CSV junto al guion y muestra una muestra."""
    df.to_csv(DIR / nombre, index=False, float_format="%.10g")
    mostrar(df, nombre)


def actualizar_resumen(claves: dict) -> None:
    """Funde claves nuevas en ``resumen.json`` y lo muestra."""
    ruta = DIR / "resumen.json"
    res = json.loads(ruta.read_text("utf-8")) if ruta.exists() else {}
    res.update(claves)
    ruta.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n",
                    "utf-8")
    plano = pd.DataFrame({"clave": list(res), "valor": [
        json.dumps(v, ensure_ascii=False)[:70] for v in res.values()]})
    mostrar(plano, "resumen.json")


def sha256(ruta: Path) -> str:
    """Suma SHA-256 de un fichero, con barra de progreso."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f, tqdm(total=ruta.stat().st_size, unit="B",
                                     unit_scale=True, desc="sha256") as b:
        while bloque := f.read(1 << 22):
            h.update(bloque)
            b.update(len(bloque))
    return h.hexdigest()


def diferencia(y: np.ndarray, t: np.ndarray) -> tuple[float, float]:
    """Diferencia de proporciones entre tratamiento y control y su error.

    Args:
        y: resultado binario.
        t: indicador de tratamiento.

    Returns:
        La diferencia y su error típico sin agrupar (de Wald).
    """
    p1, p0 = y[t == 1].mean(), y[t == 0].mean()
    n1, n0 = (t == 1).sum(), (t == 0).sum()
    return p1 - p0, np.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)


# --- 1. descarga -------------------------------------------------------------

def descargar() -> dict:
    """Descarga el CSV comprimido si falta y comprueba su SHA-256.

    Returns:
        La procedencia del fichero, para el resumen.
    """
    CRUDO.mkdir(exist_ok=True)
    if not FICHERO.exists() or FICHERO.stat().st_size != BYTES:
        req = urllib.request.Request(URL, headers={"User-Agent": UA})
        tmp = FICHERO.with_suffix(".parcial")
        with urllib.request.urlopen(req, timeout=120) as r, \
                open(tmp, "wb") as f, \
                tqdm(total=BYTES, unit="B", unit_scale=True,
                     desc="descarga") as b:
            while bloque := r.read(1 << 20):
                f.write(bloque)
                b.update(len(bloque))
        tmp.rename(FICHERO)
    huella = sha256(FICHERO)
    if huella != SHA256:
        raise RuntimeError(f"SHA-256 distinta: {huella}")
    log.info("fichero comprobado: %s", huella)
    return {"url": URL, "url_oficial": URL_OFICIAL, "revision_hf": REVISION,
            "sha256": huella, "bytes": FICHERO.stat().st_size,
            "licencia": "CC BY-NC-SA 4.0", "version": "2.1"}


def cargar() -> dict[str, np.ndarray]:
    """Lee el CSV con DuckDB y lo deja en matrices de numpy.

    Returns:
        Atributos en float32 y las cuatro columnas binarias en int8.
    """
    t0 = time.perf_counter()
    df = duckdb.sql(f"SELECT * FROM read_csv('{FICHERO}')").df()
    log.info("%d filas leídas en %.1f s", len(df), time.perf_counter() - t0)
    datos = {"X": df[ATRIBUTOS].to_numpy(np.float32)}
    for c in ("treatment", "exposure", "visit", "conversion"):
        datos[c] = df[c].to_numpy(np.int8)
    return datos


# --- 2. diseño experimental --------------------------------------------------

def diseno(d: dict[str, np.ndarray]) -> None:
    """Grupos, equilibrio, comparación ingenua y estimadores del diseño."""
    t, e, v, c = d["treatment"], d["exposure"], d["visit"], d["conversion"]
    X = d["X"].astype(np.float64)
    filas = []
    for (ti, ei), m in [((0, 0), (t == 0) & (e == 0)),
                        ((1, 0), (t == 1) & (e == 0)),
                        ((1, 1), (t == 1) & (e == 1))]:
        filas.append({"tratamiento": ti, "expuesto": ei, "n": int(m.sum()),
                      "visitas": int(v[m].sum()),
                      "conversiones": int(c[m].sum())})
    grupos = pd.DataFrame(filas)
    grupos["tasa_visita"] = grupos.visitas / grupos.n
    grupos["tasa_conversion"] = grupos.conversiones / grupos.n
    guardar(grupos, "grupos.csv")
    if ((t == 0) & (e == 1)).any() or ((v == 0) & (c == 1)).any():
        raise RuntimeError("exposición en control o conversión sin visita")

    # se mide el equilibrio con la diferencia estandarizada de medias
    def dem(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return (a.mean(0) - b.mean(0)) / np.sqrt((a.var(0) + b.var(0)) / 2)

    dem_t = dem(X[t == 1], X[t == 0])
    dem_e = dem(X[e == 1], X[e == 0])
    # error típico de la diferencia estandarizada bajo independencia
    ee_t = np.sqrt(1 / (t == 1).sum() + 1 / (t == 0).sum())
    balance = pd.DataFrame({
        "atributo": ATRIBUTOS,
        "modalidades": [int(len(np.unique(X[:, i]))) for i in range(12)],
        "dem_tratamiento_control": dem_t,
        "dem_expuestos_no_expuestos": dem_e,
        "z_tratamiento_control": dem_t / ee_t})
    guardar(balance, "balance.csv")

    res = {}
    for nombre, y in (("visita", v), ("conversion", c)):
        itt, ee = diferencia(y, t)
        pi = e[t == 1].mean()
        r_c = y[t == 0].mean()
        r_te0 = y[(t == 1) & (e == 0)].mean()
        r_e1 = y[e == 1].mean()
        r_e0 = y[e == 0].mean()
        # tasa que habrían tenido los expuestos sin anuncio (exclusión:
        # el tratamiento solo actúa a través de la exposición)
        contraf = (r_c - (1 - pi) * r_te0) / pi
        # ajuste de Lin: mínimos cuadrados con interacciones centradas
        Xc = (X - X.mean(0)) / X.std(0)
        D = np.column_stack([np.ones(len(t)), t, Xc, Xc * t[:, None]])
        yy = y.astype(np.float64)
        beta, *_ = np.linalg.lstsq(D, yy, rcond=None)
        resid = yy - D @ beta
        pan = np.linalg.inv(D.T @ D)
        De = D * resid[:, None]
        ee_lin = float(np.sqrt((pan @ (De.T @ De) @ pan)[1, 1]))
        res[nombre] = {
            "tasa_tratamiento": float(y[t == 1].mean()), "tasa_control": r_c,
            "itt": float(itt), "ee_itt": float(ee),
            "relativo_itt": float(itt / r_c),
            "tasa_expuestos": float(r_e1), "tasa_no_expuestos": float(r_e0),
            "tasa_tratados_no_expuestos": float(r_te0),
            "ingenua": float(r_e1 - r_e0),
            "pi_exposicion": float(pi),
            "efecto_expuestos": float(itt / pi),
            "tasa_expuestos_sin_anuncio": float(contraf),
            "sesgo_seleccion": float(contraf - r_e0),
            "lin": float(beta[1]), "ee_lin": ee_lin}
        del D, De, Xc

    # prueba de dos muestras con clasificador: ¿se distingue el grupo?
    rng = np.random.default_rng(SEMILLA)
    idx = rng.permutation(len(t))
    ent, pru = idx[:5_000_000], idx[5_000_000:8_000_000]
    aucs = {}
    for etiqueta, objetivo in (("tratamiento", t),
                               ("placebo", rng.permutation(t))):
        m = HistGradientBoostingClassifier(max_iter=200,
                                           random_state=SEMILLA)
        m.fit(d["X"][ent], objetivo[ent])
        aucs[etiqueta] = float(roc_auc_score(
            objetivo[pru], m.predict_proba(d["X"][pru])[:, 1]))
    n1 = int((t[pru] == 1).sum())
    n0 = len(pru) - n1
    ee_auc = float(np.sqrt((n1 + n0 + 1) / (12 * n1 * n0)))
    filas = [{"prueba": k, "auc": a, "ee_nulo": ee_auc,
              "z": (a - 0.5) / ee_auc, "n_prueba": len(pru)}
             for k, a in aucs.items()]
    guardar(pd.DataFrame(filas), "c2st.csv")
    actualizar_resumen({
        "filas": int(len(t)), "n_tratamiento": int((t == 1).sum()),
        "n_control": int((t == 0).sum()),
        "n_expuestos": int(e.sum()),
        "proporcion_tratamiento": float(t.mean()),
        "tasa_visita": float(v.mean()), "tasa_conversion": float(c.mean()),
        "tasa_exposicion": float(e.mean()),
        "cifras_clave_criteo": CLAVE,
        "dem_max_tratamiento": float(np.abs(dem_t).max()),
        "dem_max_expuestos": float(np.abs(dem_e).max()),
        "diseno": res, "c2st": aucs, "c2st_ee": ee_auc})


# --- 3. contrastes sobre el dato completo ------------------------------------

def contrastes(d: dict[str, np.ndarray]) -> None:
    """Cinco maneras de contrastar la diferencia, sobre todas las filas."""
    t = d["treatment"]
    rng = np.random.default_rng(SEMILLA)
    n1, n0 = int((t == 1).sum()), int((t == 0).sum())
    filas, nulas = [], []
    for nombre, y in (("visita", d["visit"]), ("conversion", d["conversion"])):
        y1, y0 = int(y[t == 1].sum()), int(y[t == 0].sum())
        p1, p0 = y1 / n1, y0 / n0
        dif = p1 - p0
        k = y1 + y0
        pp = k / (n1 + n0)
        # prueba z de dos proporciones: error agrupado para el contraste y
        # sin agrupar (Wald) para el intervalo
        ee_w = np.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
        ee_a = np.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n0))
        z = dif / ee_a
        t0 = time.perf_counter()
        filas.append({"resultado": nombre, "metodo": "z de dos proporciones",
                      "estimacion": dif, "ic_inf": dif - Z * ee_w,
                      "ic_sup": dif + Z * ee_w, "estadistico": z,
                      "p": 2 * stats.norm.sf(abs(z)),
                      "segundos": time.perf_counter() - t0})
        a, b = y[t == 1].astype(np.float64), y[t == 0].astype(np.float64)
        t0 = time.perf_counter()
        w = stats.ttest_ind(a, b, equal_var=False)
        ic = w.confidence_interval()
        filas.append({"resultado": nombre, "metodo": "t de Welch",
                      "estimacion": dif, "ic_inf": ic.low, "ic_sup": ic.high,
                      "estadistico": w.statistic, "p": w.pvalue,
                      "segundos": time.perf_counter() - t0})
        t0 = time.perf_counter()
        u = stats.mannwhitneyu(a, b, method="asymptotic",
                               use_continuity=False)
        # con datos 0/1, U/(n1 n0) = 0,5 + (p1 - p0)/2
        filas.append({"resultado": nombre, "metodo": "Mann-Whitney",
                      "estimacion": 2 * (u.statistic / (n1 * n0) - 0.5),
                      "ic_inf": np.nan, "ic_sup": np.nan,
                      "estadistico": (u.statistic - n1 * n0 / 2) / np.sqrt(
                          n1 * n0 * (n1 + n0 + 1) / 12 * (
                              1 - (k ** 3 - k + (n1 + n0 - k) ** 3
                                   - (n1 + n0 - k)) / ((n1 + n0) ** 3
                                                       - (n1 + n0)))),
                      "p": u.pvalue, "segundos": time.perf_counter() - t0})
        del a, b
        # permutación: con un resultado binario, el número de éxitos que
        # caen en el grupo tratado al barajar las etiquetas sigue una
        # hipergeométrica; se extraen 10.000 permutaciones de ella
        t0 = time.perf_counter()
        perm = rng.hypergeometric(k, n1 + n0 - k, n1, size=10_000)
        dperm = perm / n1 - (k - perm) / n0
        p_perm = (1 + int((np.abs(dperm) >= abs(dif)).sum())) / 10_001
        filas.append({"resultado": nombre, "metodo": "permutación",
                      "estimacion": dif, "ic_inf": np.nan, "ic_sup": np.nan,
                      "estadistico": dif / dperm.std(), "p": p_perm,
                      "segundos": time.perf_counter() - t0})
        # bootstrap: remuestrear n filas con reemplazo dentro de un grupo
        # con y éxitos da una binomial(n, y/n); 10.000 réplicas
        t0 = time.perf_counter()
        boot = (rng.binomial(n1, p1, 10_000) / n1
                - rng.binomial(n0, p0, 10_000) / n0)
        lo, hi = np.percentile(boot, [2.5, 97.5])
        filas.append({"resultado": nombre, "metodo": "bootstrap",
                      "estimacion": dif, "ic_inf": lo, "ic_sup": hi,
                      "estadistico": dif / boot.std(), "p": np.nan,
                      "segundos": time.perf_counter() - t0})
        nulas.append({"resultado": nombre, "ee_wald": ee_w,
                      "ee_agrupado": ee_a, "de_permutacion": dperm.std(),
                      "de_bootstrap": boot.std(),
                      "max_permutacion": np.abs(dperm).max()})
    # comprobación literal: 200 réplicas remuestreando filas de verdad
    i1, i0 = np.flatnonzero(t == 1), np.flatnonzero(t == 0)
    lit = {"visita": [], "conversion": []}
    for _ in tqdm(range(200), desc="bootstrap literal"):
        b1 = rng.choice(i1, n1)
        b0 = rng.choice(i0, n0)
        for nombre, y in (("visita", d["visit"]),
                          ("conversion", d["conversion"])):
            lit[nombre].append(y[b1].mean() - y[b0].mean())
    for fila in nulas:
        fila["de_bootstrap_literal_200"] = float(np.std(lit[fila["resultado"]],
                                                        ddof=1))
    guardar(pd.DataFrame(filas), "contrastes.csv")
    guardar(pd.DataFrame(nulas), "contrastes_dispersion.csv")


# --- 4. cobertura en submuestras ---------------------------------------------

def p_permutacion(n1: int, n0: int, k: int, dif: float) -> float:
    """p bilateral exacto de la permutación para un resultado binario.

    Args:
        n1: filas tratadas.
        n0: filas de control.
        k: éxitos totales.
        dif: diferencia observada de proporciones.

    Returns:
        La probabilidad, bajo la hipótesis nula, de una diferencia al menos
        tan grande en valor absoluto.
    """
    soporte = np.arange(max(0, k - n0), min(k, n1) + 1)
    d = soporte / n1 - (k - soporte) / n0
    x = soporte[np.abs(d) >= abs(dif) - 1e-12]
    # se evalúa la hipergeométrica con logaritmos de factoriales, más
    # rápido que el objeto de scipy.stats dentro de un bucle

    def lnc(a, b):
        return gammaln(a + 1) - gammaln(b + 1) - gammaln(a - b + 1)

    logp = lnc(k, x) + lnc(n1 + n0 - k, n1 - x) - lnc(n1 + n0, n1)
    return float(min(1.0, np.exp(logp).sum()))


def cobertura(d: dict[str, np.ndarray]) -> None:
    """Cobertura y error de tipo I de las pruebas en submuestras."""
    t = d["treatment"]
    rng = np.random.default_rng(SEMILLA + 1)
    tamanos, R, B = [2_000, 5_000, 20_000, 100_000, 500_000], 2_000, 1_000
    filas = []
    for nombre, y in (("visita", d["visit"]), ("conversion", d["conversion"])):
        verdad, _ = diferencia(y, t)
        for n in tamanos:
            reg = {k: [] for k in ("cub_wald", "cub_boot", "rz", "rperm",
                                   "rboot", "nz", "nperm", "nboot",
                                   "ceros", "ancho_wald", "ancho_boot")}
            for _ in tqdm(range(R), desc=f"{nombre} n={n}", leave=False):
                idx = rng.choice(len(t), n, replace=False)
                ts, ys = t[idx], y[idx]
                for nula in (False, True):
                    tt = rng.permutation(ts) if nula else ts
                    n1 = int(tt.sum())
                    n0 = n - n1
                    y1 = int(ys[tt == 1].sum())
                    y0 = int(ys.sum()) - y1
                    p1, p0 = y1 / n1, y0 / n0
                    dif = p1 - p0
                    pp = (y1 + y0) / n
                    ee_a = np.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n0))
                    rz = ee_a > 0 and abs(dif / ee_a) > Z
                    rperm = p_permutacion(n1, n0, y1 + y0, dif) < 0.05
                    boot = (rng.binomial(n1, p1, B) / n1
                            - rng.binomial(n0, p0, B) / n0)
                    lo, hi = np.percentile(boot, [2.5, 97.5])
                    rboot = lo > 0 or hi < 0
                    if nula:
                        reg["nz"].append(rz)
                        reg["nperm"].append(rperm)
                        reg["nboot"].append(rboot)
                        continue
                    ee_w = np.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
                    reg["cub_wald"].append(abs(dif - verdad) <= Z * ee_w)
                    reg["cub_boot"].append(lo <= verdad <= hi)
                    reg["ancho_wald"].append(2 * Z * ee_w)
                    reg["ancho_boot"].append(hi - lo)
                    reg["rz"].append(rz)
                    reg["rperm"].append(rperm)
                    reg["rboot"].append(rboot)
                    reg["ceros"].append(y0 == 0)
            fila = {"resultado": nombre, "n": n, "replicas": R,
                    "verdad": verdad}
            fila.update({k: float(np.mean(v)) for k, v in reg.items()})
            filas.append(fila)
            log.info("%s n=%d cobertura wald %.3f boot %.3f", nombre, n,
                     fila["cub_wald"], fila["cub_boot"])
    guardar(pd.DataFrame(filas), "cobertura.csv")


# --- 5. potencia y tamaño de muestra -----------------------------------------

def potencia_analitica(p1: float, p0: float, n: np.ndarray, w1: float,
                       alfa: float = 0.05) -> np.ndarray:
    """Potencia de la prueba z bilateral de dos proporciones.

    Args:
        p1: proporción en tratamiento.
        p0: proporción en control.
        n: tamaño total de la muestra.
        w1: fracción de la muestra que va a tratamiento.
        alfa: nivel de significación.

    Returns:
        La probabilidad de rechazar la hipótesis nula.
    """
    n1, n0 = w1 * n, (1 - w1) * n
    pb = w1 * p1 + (1 - w1) * p0
    s0 = np.sqrt(pb * (1 - pb) * (1 / n1 + 1 / n0))
    s1 = np.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    za = stats.norm.ppf(1 - alfa / 2)
    return stats.norm.cdf((abs(p1 - p0) - za * s0) / s1)


def n_necesario(p1: float, p0: float, w1: float, objetivo: float) -> int:
    """Tamaño total mínimo para alcanzar una potencia dada."""
    lo, hi = 10, 10 ** 10
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if potencia_analitica(p1, p0, np.array(mid), w1) >= objetivo:
            hi = mid
        else:
            lo = mid
    return hi


def potencia(d: dict[str, np.ndarray]) -> None:
    """Potencia analítica frente a Monte Carlo sobre submuestras reales."""
    t = d["treatment"]
    rng = np.random.default_rng(SEMILLA + 2)
    rejillas = {"visita": [2_000, 5_000, 10_000, 15_000, 20_000, 30_000,
                           50_000],
                "conversion": [10_000, 25_000, 50_000, 75_000, 100_000,
                               150_000, 250_000]}
    w1 = float(t.mean())
    filas, necesarios = [], []
    res = json.loads((DIR / "resumen.json").read_text("utf-8"))
    for nombre, y in (("visita", d["visit"]), ("conversion", d["conversion"])):
        p1, p0 = y[t == 1].mean(), y[t == 0].mean()
        for n in rejillas[nombre]:
            rech = 0
            R = 2_000
            for _ in tqdm(range(R), desc=f"potencia {nombre} n={n}",
                          leave=False):
                idx = rng.choice(len(t), n, replace=False)
                ts, ys = t[idx], y[idx]
                n1 = int(ts.sum())
                n0 = n - n1
                y1 = int(ys[ts == 1].sum())
                y0 = int(ys.sum()) - y1
                pp = (y1 + y0) / n
                ee = np.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n0))
                rech += ee > 0 and abs((y1 / n1 - y0 / n0) / ee) > Z
            mc = rech / R
            filas.append({"resultado": nombre, "n": n, "replicas": R,
                          "potencia_mc": mc,
                          "ee_mc": np.sqrt(mc * (1 - mc) / R),
                          "potencia_analitica": float(potencia_analitica(
                              p1, p0, np.array(n), w1))})
        # el efecto ajustado de Lin como hipótesis alternativa más pequeña
        lin = res["diseno"][nombre]["lin"]
        for etiqueta, q1 in (("observado", p1), ("ajustado", p0 + lin)):
            for asig in (w1, 0.5):
                for obj in (0.8, 0.9):
                    necesarios.append({
                        "resultado": nombre, "efecto": etiqueta,
                        "diferencia": q1 - p0, "asignacion": asig,
                        "potencia": obj,
                        "n_total": n_necesario(q1, p0, asig, obj)})
    guardar(pd.DataFrame(filas), "potencia.csv")
    guardar(pd.DataFrame(necesarios), "tamano_muestra.csv")
    # encuesta de brand lift: efecto mínimo detectable con la mitad de las
    # respuestas en cada grupo, para tres valores de partida supuestos
    enc = []
    for base in (0.10, 0.30, 0.50):
        for por_grupo in (250, 500, 1_000, 2_000, 5_000):
            lo, hi = 0.0, 1 - base
            for _ in range(60):
                mid = (lo + hi) / 2
                if potencia_analitica(base + mid, base,
                                      np.array(2 * por_grupo), 0.5) >= 0.8:
                    hi = mid
                else:
                    lo = mid
            enc.append({"base_supuesta": base, "respuestas_por_grupo":
                        por_grupo, "efecto_minimo_detectable": hi,
                        "relativo": hi / base})
    guardar(pd.DataFrame(enc), "encuesta.csv")


# --- 6. modelos de uplift ----------------------------------------------------

def hgb_clasificador() -> HistGradientBoostingClassifier:
    """Árboles con gradiente por histogramas, con parámetros fijos."""
    return HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.1, max_leaf_nodes=31,
        min_samples_leaf=100, early_stopping=False, random_state=SEMILLA)


def hgb_regresor() -> HistGradientBoostingRegressor:
    """La versión de regresión, para la segunda etapa del X-learner."""
    return HistGradientBoostingRegressor(
        max_iter=200, learning_rate=0.1, max_leaf_nodes=31,
        min_samples_leaf=100, early_stopping=False, random_state=SEMILLA)


def logistica() -> LogisticRegression:
    """Regresión logística con regularización L2 por defecto."""
    return LogisticRegression(max_iter=1_000)


def acumulados(orden: np.ndarray, t: np.ndarray, y: np.ndarray,
               w: np.ndarray | None = None) -> tuple[np.ndarray, ...]:
    """Sumas acumuladas por tratamiento y respuesta en un orden dado."""
    tt, yy = t[orden].astype(np.float64), y[orden].astype(np.float64)
    ww = np.ones(len(orden)) if w is None else w[orden].astype(np.float64)
    return (np.cumsum(ww * tt), np.cumsum(ww * (1 - tt)),
            np.cumsum(ww * tt * yy), np.cumsum(ww * (1 - tt) * yy))


def qini(orden: np.ndarray, t: np.ndarray, y: np.ndarray,
         w: np.ndarray | None = None) -> tuple[np.ndarray, float, float]:
    """Curva Qini y su área por encima del azar.

    La curva cuenta, para los k primeros según el modelo, las visitas
    incrementales q(k) = R_T(k) - R_C(k) N_T(k)/N_C(k). El área se mide
    entre esa curva y la diagonal que une el origen con q(n), y se da de
    dos maneras: en proporción de las visitas incrementales del conjunto,
    q(n), y en visitas incrementales por cada mil usuarios, que no depende
    de dividir por q(n) y es estable en muestras pequeñas.

    Args:
        orden: índices de la prueba, de mayor a menor uplift predicho.
        t: tratamiento.
        y: resultado.
        w: pesos de un bootstrap de Poisson, o None.

    Returns:
        La curva normalizada en cada k, el área normalizada y el área por
        cada mil usuarios.
    """
    nt, nc, yt, yc = acumulados(orden, t, y, w)
    q = yt - yc * np.divide(nt, nc, out=np.zeros_like(nt), where=nc > 0)
    x = np.arange(1, len(q) + 1) / len(q)
    bruta = float(np.trapezoid(q - x * q[-1], x))
    n_ef = float(nt[-1] + nc[-1])
    return q / q[-1], bruta / q[-1], 1000 * bruta / n_ef


def ordenar(u: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Orden descendente por uplift predicho, con empates al azar."""
    return np.lexsort((rng.random(len(u)), -u))


def modelos(d: dict[str, np.ndarray]) -> None:
    """Entrena, evalúa y segmenta siete modelos de uplift de la visita."""
    X, t, y = d["X"], d["treatment"], d["visit"]
    rng = np.random.default_rng(SEMILLA + 3)
    idx = rng.permutation(len(t))
    corte = int(0.8 * len(t))
    ent, pru = np.sort(idx[:corte]), np.sort(idx[corte:])
    Xe, Xp, te, tp, ye, yp = X[ent], X[pru], t[ent], t[pru], y[ent], y[pru]
    media, de = Xe.mean(0), Xe.std(0)
    Ze, Zp = (Xe - media) / de, (Xp - media) / de
    w1 = float(te.mean())
    # pesos que equilibran tratamiento y control para la transformación
    peso = np.where(te == 1, 0.5 / w1, 0.5 / (1 - w1))
    zc = (te * ye + (1 - te) * (1 - ye)).astype(np.int8)
    predicciones, costes = {}, []

    def medir(nombre: str, familia: str, base: str, ajustar, predecir,
              parametros: str) -> None:
        t0 = time.perf_counter()
        estado = ajustar()
        s_ent = time.perf_counter() - t0
        t0 = time.perf_counter()
        u = predecir(estado)
        s_pred = time.perf_counter() - t0
        predicciones[nombre] = u
        costes.append({"modelo": nombre, "familia": familia, "base": base,
                       "segundos_entrenamiento": s_ent,
                       "segundos_prediccion": s_pred,
                       "parametros": parametros})
        log.info("%s: %.1f s + %.1f s", nombre, s_ent, s_pred)

    # S-learner logístico: interacciones de cada atributo con el tratamiento
    def s_log_ajustar():
        return logistica().fit(np.column_stack([Ze, te, Ze * te[:, None]]),
                               ye)

    def s_log_predecir(m):
        uno = np.ones((len(tp), 1))
        a = m.predict_proba(np.column_stack([Zp, uno, Zp]))[:, 1]
        b = m.predict_proba(np.column_stack([Zp, 0 * uno, 0 * Zp]))[:, 1]
        return a - b

    medir("S · logística", "S", "logística", s_log_ajustar, s_log_predecir,
          "25 coeficientes y la ordenada")

    def t_ajustar(fab, A):
        def f():
            return (fab().fit(A[te == 1], ye[te == 1]),
                    fab().fit(A[te == 0], ye[te == 0]))
        return f

    def t_predecir(A):
        def f(ms):
            return ms[0].predict_proba(A)[:, 1] - ms[1].predict_proba(A)[:, 1]
        return f

    medir("T · logística", "T", "logística", t_ajustar(logistica, Ze),
          t_predecir(Zp), "2 × 12 coeficientes y sus ordenadas")

    def tc_ajustar(fab, A):
        def f():
            return fab().fit(A, zc, sample_weight=peso)
        return f

    def tc_predecir(A):
        def f(m):
            return 2 * m.predict_proba(A)[:, 1] - 1
        return f

    medir("TC · logística", "TC", "logística", tc_ajustar(logistica, Ze),
          tc_predecir(Zp), "12 coeficientes y la ordenada")

    def s_hgb_ajustar():
        return hgb_clasificador().fit(np.column_stack([Xe, te]), ye)

    def s_hgb_predecir(m):
        uno = np.ones(len(tp), dtype=np.float32)
        return (m.predict_proba(np.column_stack([Xp, uno]))[:, 1]
                - m.predict_proba(np.column_stack([Xp, 0 * uno]))[:, 1])

    medir("S · árboles", "S", "árboles", s_hgb_ajustar, s_hgb_predecir,
          "200 árboles de hasta 31 hojas")
    t_modelos = {}

    def t_hgb_ajustar():
        ms = t_ajustar(hgb_clasificador, Xe)()
        t_modelos["T"] = ms
        return ms

    medir("T · árboles", "T", "árboles", t_hgb_ajustar, t_predecir(Xp),
          "2 × 200 árboles de hasta 31 hojas")
    mu0_p = t_modelos["T"][1].predict_proba(Xp)[:, 1]

    # X-learner: efectos imputados con el modelo del otro grupo y una
    # regresión por grupo, combinadas con la propensión (constante)
    def x_ajustar():
        m1, m0 = t_modelos["T"]
        d1 = ye[te == 1] - m0.predict_proba(Xe[te == 1])[:, 1]
        d0 = m1.predict_proba(Xe[te == 0])[:, 1] - ye[te == 0]
        return (hgb_regresor().fit(Xe[te == 1], d1),
                hgb_regresor().fit(Xe[te == 0], d0))

    def x_predecir(rs):
        return w1 * rs[1].predict(Xp) + (1 - w1) * rs[0].predict(Xp)

    medir("X · árboles", "X", "árboles", x_ajustar, x_predecir,
          "2 × 200 árboles más los dos del T-learner")
    medir("TC · árboles", "TC", "árboles", tc_ajustar(hgb_clasificador, Xe),
          tc_predecir(Xp), "200 árboles de hasta 31 hojas")
    # el tiempo del X-learner incluye su primera etapa, el T-learner
    for c in costes:
        if c["modelo"] == "X · árboles":
            c["segundos_entrenamiento"] += next(
                k["segundos_entrenamiento"] for k in costes
                if k["modelo"] == "T · árboles")

    nombres = list(predicciones)
    ordenes = {m: ordenar(predicciones[m], rng) for m in nombres}
    # curvas Qini y área, con 200 réplicas de un bootstrap de Poisson
    # pareado (los mismos pesos por fila para todos los modelos)
    puntos = np.linspace(0, 1, 201)
    curvas, areas = [], {}
    for m in nombres:
        qn, area, _ = qini(ordenes[m], tp, yp)
        areas[m] = area
        k = np.clip((puntos * len(qn)).astype(int) - 1, 0, len(qn) - 1)
        curvas.append(pd.DataFrame({"modelo": m, "fraccion": puntos,
                                    "qini": np.where(puntos == 0, 0, qn[k])}))
    guardar(pd.concat(curvas, ignore_index=True), "qini_curvas.csv")

    def bootstrap(sub: np.ndarray, B: int,
                  semilla: int) -> dict[str, pd.DataFrame]:
        """Áreas Qini de cada modelo en B réplicas sobre una submuestra."""
        r = np.random.default_rng(semilla)
        ords = {m: ordenar(predicciones[m][sub], r) for m in nombres}
        norm, abso = [], []
        for b in tqdm(range(B), desc=f"bootstrap n={len(sub)}", leave=False):
            w = r.poisson(1.0, len(sub)).astype(np.float64)
            fn, fa = {"replica": b}, {"replica": b}
            for m in nombres:
                _, fn[m], fa[m] = qini(ords[m], tp[sub], yp[sub], w)
            norm.append(fn)
            abso.append(fa)
        return {"norm": pd.DataFrame(norm), "abs": pd.DataFrame(abso)}

    todo = np.arange(len(tp))
    reps = bootstrap(todo, 200, SEMILLA + 4)
    rep = reps["norm"]
    mejor = max(areas, key=areas.get)
    filas = []
    for m in nombres:
        nt, nc, yt, yc = acumulados(ordenes[m], tp, yp)
        q = yt - yc * nt / np.maximum(nc, 1)
        captura = {f"captura_{int(100 * f)}": float(
            q[int(f * len(q)) - 1] / q[-1]) for f in (0.1, 0.2, 0.3, 0.5)}
        dif = rep[mejor] - rep[m]
        # calibración: deciles del uplift predicho frente al observado
        dec = np.array_split(ordenes[m], 10)
        pred = [predicciones[m][g].mean() for g in dec]
        obs = [yp[g][tp[g] == 1].mean() - yp[g][tp[g] == 0].mean()
               for g in dec]
        pend = float(np.polyfit(pred, obs, 1)[0])
        fila = {"modelo": m, "area_qini": areas[m],
                "area_ic_inf": float(rep[m].quantile(0.025)),
                "area_ic_sup": float(rep[m].quantile(0.975)),
                "area_de": float(rep[m].std()),
                "dif_con_mejor_ic_inf": float(dif.quantile(0.025)),
                "dif_con_mejor_ic_sup": float(dif.quantile(0.975)),
                "uplift_medio_predicho": float(predicciones[m].mean()),
                "pendiente_calibracion": pend,
                "error_calibracion": float(np.mean(np.abs(
                    np.array(pred) - np.array(obs))))}
        fila.update(captura)
        filas.append(fila)
    tabla = pd.DataFrame(filas).merge(pd.DataFrame(costes), on="modelo")
    guardar(tabla, "modelos.csv")
    guardar(rep, "qini_bootstrap.csv")
    guardar(reps["abs"], "qini_bootstrap_por_mil.csv")

    cal = []
    for m in nombres:
        for i, g in enumerate(np.array_split(ordenes[m], 10)):
            g1, g0 = g[tp[g] == 1], g[tp[g] == 0]
            p1, p0 = yp[g1].mean(), yp[g0].mean()
            cal.append({"modelo": m, "decil": i + 1,
                        "predicho": float(predicciones[m][g].mean()),
                        "observado": float(p1 - p0),
                        "ee": float(np.sqrt(p1 * (1 - p1) / len(g1)
                                            + p0 * (1 - p0) / len(g0)))})
    guardar(pd.DataFrame(cal), "calibracion.csv")

    # separabilidad: con cuántas filas de prueba se distinguen los modelos
    sep = []
    for n in (10_000, 100_000, 1_000_000, len(tp)):
        sub = todo if n == len(tp) else np.sort(
            np.random.default_rng(SEMILLA + n).choice(len(tp), n,
                                                      replace=False))
        r = (reps if n == len(tp) else
             bootstrap(sub, 200, SEMILLA + 5 + n))["abs"]
        pares = sum(
            not (r[a] - r[b]).quantile(0.025) <= 0
            <= (r[a] - r[b]).quantile(0.975)
            for i, a in enumerate(nombres) for b in nombres[i + 1:])
        for m in nombres:
            # áreas en visitas incrementales por cada mil usuarios
            sep.append({"n_prueba": n, "modelo": m,
                        "area_ic_inf": float(r[m].quantile(0.025)),
                        "area_mediana": float(r[m].median()),
                        "area_ic_sup": float(r[m].quantile(0.975)),
                        "pares_distinguibles": int(pares),
                        "pares_totales": len(nombres) * (len(nombres) - 1)
                        // 2})
    guardar(pd.DataFrame(sep), "separabilidad.csv")

    # se guardan las predicciones de la prueba para la etapa de segmentos
    np.savez_compressed(PREDICCIONES, prueba=pru,
                        tau=predicciones["X · árboles"], mu0=mu0_p)
    actualizar_resumen({"modelos": {
        "n_entrenamiento": int(len(ent)), "n_prueba": int(len(pru)),
        "mejor": mejor,
        "itt_prueba": float(yp[tp == 1].mean() - yp[tp == 0].mean())}})


# --- segmentación ------------------------------------------------------------

def perfil(etiquetas: np.ndarray, t: np.ndarray, y: np.ndarray,
           e: np.ndarray) -> pd.DataFrame:
    """Tamaño, efecto observado y exposiciones de cada grupo.

    Además del uplift (tratamiento menos control), descompone la tasa de los
    expuestos de cada grupo con el estimador de Wald: la tasa que habrían
    tenido sin anuncio y la parte de sus visitas que habría ocurrido igual.

    Args:
        etiquetas: grupo de cada fila.
        t: tratamiento.
        y: visita.
        e: exposición.

    Returns:
        Una fila por grupo.
    """
    filas = []
    for g in np.unique(etiquetas):
        m = etiquetas == g
        m1, m0 = m & (t == 1), m & (t == 0)
        me1, me0 = m1 & (e == 1), m1 & (e == 0)
        p1, p0 = y[m1].mean(), y[m0].mean()
        pi = me1.sum() / m1.sum()
        r_e1, r_e0 = y[me1].mean(), y[me0].mean()
        contraf = (p0 - (1 - pi) * r_e0) / pi
        filas.append({"grupo": int(g), "n": int(m.sum()),
                      "cuota": float(m.mean()),
                      "tasa_control": float(p0), "tasa_tratamiento": float(p1),
                      "uplift": float(p1 - p0),
                      "ee": float(np.sqrt(p1 * (1 - p1) / m1.sum()
                                          + p0 * (1 - p0) / m0.sum())),
                      "tratados": int(m1.sum()),
                      "exposiciones": int(me1.sum()),
                      "tasa_exposicion": float(pi),
                      "tasa_expuestos": float(r_e1),
                      "efecto_expuestos": float((p1 - p0) / pi),
                      "tasa_expuestos_sin_anuncio": float(contraf),
                      "cuota_visitas_expuestos_igual": float(contraf / r_e1),
                      "visitas_anadidas_tratados": float((p1 - p0) * m1.sum())})
    df = pd.DataFrame(filas)
    # visitas añadidas por grupo, sumando la comparación dentro de cada uno
    inc = df.uplift * df.n
    df["cuota_incremental"] = inc / inc.sum()
    df["cuota_exposiciones"] = df.exposiciones / df.exposiciones.sum()
    df["exposiciones_por_visita_anadida"] = (df.exposiciones
                                             / df.visitas_anadidas_tratados)
    return df


def segmentos(d: dict[str, np.ndarray]) -> None:
    """Segmentación con las predicciones que guardó la etapa de modelos."""
    z = np.load(PREDICCIONES)
    pru = z["prueba"]
    segmentar(z["tau"], z["mu0"], d["X"][pru], d["treatment"][pru],
              d["visit"][pru], d["exposure"][pru])


def segmentar(tau: np.ndarray, mu0: np.ndarray, X: np.ndarray, t: np.ndarray,
              y: np.ndarray, e: np.ndarray) -> None:
    """k-medias sobre (respuesta sin anuncio, uplift) y sobre los atributos.

    Args:
        tau: uplift predicho por el X-learner en la prueba.
        mu0: probabilidad de visita sin anuncio, del modelo de control.
        X: atributos de la prueba.
        t: tratamiento.
        y: visita.
        e: exposición.
    """
    rng = np.random.default_rng(SEMILLA + 6)
    lg = np.log(np.clip(mu0, 1e-6, 1 - 1e-6) / np.clip(1 - mu0, 1e-6, 1))
    lo, hi = np.percentile(tau, [0.5, 99.5])
    E = np.column_stack([lg, np.clip(tau, lo, hi)])
    E = (E - E.mean(0)) / E.std(0)
    Xs = (X - X.mean(0)) / X.std(0)
    ajuste = rng.choice(len(t), 300_000, replace=False)
    sil = rng.choice(len(t), 20_000, replace=False)
    filas = []
    for k in tqdm(range(2, 9), desc="siluetas"):
        for espacio, A in (("predicciones", E), ("atributos", Xs)):
            km = KMeans(k, n_init=10, random_state=SEMILLA).fit(A[ajuste])
            filas.append({"espacio": espacio, "k": k,
                          "silueta": float(silhouette_score(
                              A[sil], km.predict(A[sil]),
                              random_state=SEMILLA))})
    siluetas = pd.DataFrame(filas)
    guardar(siluetas, "siluetas.csv")
    perfiles = []
    k = int(siluetas[siluetas.espacio == "predicciones"]
            .sort_values("silueta").k.iloc[-1])
    for espacio, A in (("predicciones", E), ("atributos", Xs)):
        km = KMeans(k, n_init=10, random_state=SEMILLA).fit(A[ajuste])
        et = km.predict(A)
        p = perfil(et, t, y, e)
        p.insert(0, "espacio", espacio)
        p["k"] = k
        p["mu0_medio"] = [float(mu0[et == g].mean()) for g in p.grupo]
        p["tau_medio"] = [float(tau[et == g].mean()) for g in p.grupo]
        perfiles.append(p)
    guardar(pd.concat(perfiles, ignore_index=True), "segmentos.csv")
    # deciles del uplift predicho: la alternativa sin agrupamiento; los
    # empates se rompen al azar, porque el orden del fichero no es aleatorio
    orden = ordenar(tau, rng)
    et = np.empty(len(t), dtype=int)
    for i, g in enumerate(np.array_split(orden, 10)):
        et[g] = i + 1
    p = perfil(et, t, y, e)
    p["mu0_medio"] = [float(mu0[et == g].mean()) for g in p.grupo]
    p["tau_medio"] = [float(tau[et == g].mean()) for g in p.grupo]
    guardar(p, "deciles_uplift.csv")


# --- 7. escala ---------------------------------------------------------------

CONSULTA = """\
WITH celdas AS (
    SELECT treatment AS t, exposure AS e, count(*) AS n,
           sum(visit) AS v, sum(conversion) AS c
    FROM {fuente}
    GROUP BY ALL
), grupos AS (
    SELECT sum(n) FILTER (WHERE t = 1) AS n1,
           sum(n) FILTER (WHERE t = 0) AS n0,
           sum(v) FILTER (WHERE t = 1) / n1 AS v1,
           sum(v) FILTER (WHERE t = 0) / n0 AS v0,
           sum(c) FILTER (WHERE t = 1) / n1 AS c1,
           sum(c) FILTER (WHERE t = 0) / n0 AS c0,
           sum(n) FILTER (WHERE e = 1) / n1 AS pi,
           sum(v) FILTER (WHERE e = 1) / sum(n) FILTER (WHERE e = 1) AS ve1,
           sum(v) FILTER (WHERE e = 0) / sum(n) FILTER (WHERE e = 0) AS ve0
    FROM celdas
)
SELECT n1, n0,
       v1 - v0 AS itt_visita,
       sqrt(v1 * (1 - v1) / n1 + v0 * (1 - v0) / n0) AS ee_visita,
       itt_visita - 1.959964 * ee_visita AS ic_inf_visita,
       itt_visita + 1.959964 * ee_visita AS ic_sup_visita,
       c1 - c0 AS itt_conversion,
       sqrt(c1 * (1 - c1) / n1 + c0 * (1 - c0) / n0) AS ee_conversion,
       ve1 - ve0 AS ingenua_visita,
       pi,
       itt_visita / pi AS efecto_expuestos_visita
FROM grupos
"""


def escala(d: dict[str, np.ndarray]) -> None:
    """El cálculo central en SQL con DuckDB, en CSV y en Parquet."""
    (DIR / "consulta_central.sql").write_text(
        CONSULTA.format(fuente="read_csv('criteo-research-uplift-v2.1"
                               ".csv.gz')"), "utf-8")
    print((DIR / "consulta_central.sql").read_text("utf-8"))
    con = duckdb.connect()
    # en DuckDB 2.0 una relación ya no tiene fetchone()
    hilos = int(con.sql("SELECT current_setting('threads')").fetchall()[0][0])
    filas = []

    def cronometrar(nombre: str, sql: str, veces: int) -> pd.DataFrame:
        tiempos, r = [], None
        for _ in range(veces):
            t0 = time.perf_counter()
            r = con.sql(sql).df()
            tiempos.append(time.perf_counter() - t0)
        filas.append({"paso": nombre, "ejecuciones": veces,
                      "primera_s": tiempos[0],
                      "mediana_s": float(np.median(tiempos))})
        return r

    r_csv = cronometrar("DuckDB · consulta sobre el CSV comprimido",
                        CONSULTA.format(fuente=f"read_csv('{FICHERO}')"), 3)
    t0 = time.perf_counter()
    con.sql(f"COPY (SELECT * FROM read_csv('{FICHERO}')) TO '{PARQUET}' "
            "(FORMAT parquet, COMPRESSION zstd)")
    filas.append({"paso": "DuckDB · conversión a Parquet", "ejecuciones": 1,
                  "primera_s": time.perf_counter() - t0,
                  "mediana_s": time.perf_counter() - t0})
    r_pq = cronometrar("DuckDB · consulta sobre Parquet",
                       CONSULTA.format(fuente=f"read_parquet('{PARQUET}')"),
                       5)
    t0 = time.perf_counter()
    df = pd.read_csv(FICHERO)
    s_lee = time.perf_counter() - t0
    filas.append({"paso": "pandas · lectura del CSV comprimido",
                  "ejecuciones": 1, "primera_s": s_lee, "mediana_s": s_lee})
    tiempos = []
    for _ in range(5):
        t0 = time.perf_counter()
        g = df.groupby(["treatment", "exposure"])[["visit", "conversion"]] \
            .agg(["count", "sum"])
        tiempos.append(time.perf_counter() - t0)
    filas.append({"paso": "pandas · agregación en memoria", "ejecuciones": 5,
                  "primera_s": tiempos[0],
                  "mediana_s": float(np.median(tiempos))})
    del df, g
    itt, _ = diferencia(d["visit"], d["treatment"])
    for r in (r_csv, r_pq):
        if abs(float(r.itt_visita.iloc[0]) - itt) > 1e-12:
            raise RuntimeError("DuckDB y numpy no coinciden")
    tabla = pd.DataFrame(filas)
    tabla["hilos"] = hilos
    guardar(tabla, "escala.csv")
    guardar(r_pq, "consulta_central.csv")
    actualizar_resumen({"escala": {
        "hilos": hilos, "bytes_csv_gz": FICHERO.stat().st_size,
        "bytes_parquet": PARQUET.stat().st_size}})


# --- principal ---------------------------------------------------------------

ETAPAS = ["diseno", "contrastes", "cobertura", "potencia", "modelos",
          "segmentos", "escala"]


def main() -> None:
    """Ejecuta las etapas pedidas, en orden."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--etapa", choices=["descarga"] + ETAPAS,
                    help="una sola etapa (por defecto, todas)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    procedencia = descargar()
    actualizar_resumen({
        "fecha": date.today().isoformat(), "dato": procedencia,
        "semilla": SEMILLA,
        "versiones": {"python": platform.python_version(),
                      "numpy": np.__version__, "pandas": pd.__version__,
                      "scipy": scipy.__version__,
                      "scikit-learn": sklearn.__version__,
                      "duckdb": duckdb.__version__},
        "hilos_cpu": os.cpu_count()})
    if a.etapa == "descarga":
        return
    datos = cargar()
    for etapa in ETAPAS if a.etapa is None else [a.etapa]:
        t0 = time.perf_counter()
        globals()[etapa](datos)
        log.info("etapa %s: %.0f s", etapa, time.perf_counter() - t0)


if __name__ == "__main__":
    main()
