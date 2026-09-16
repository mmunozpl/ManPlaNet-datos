#!/usr/bin/env python3
"""Dos experimentos sintéticos sobre el evaluador dentro del bucle de mejora.

1. El mejor de k semillas. Un modelo con exactitud real p se evalúa k veces
   sobre un banco de n preguntas y se publica la mejor de las k. Sin que la
   capacidad cambie, la cifra publicada sube: es el máximo de k variables
   con ruido. Se calcula la inflación esperada por la aproximación normal
   —desviación sqrt(p(1-p)/n) por la esperanza del máximo de k normales—
   y se contrasta con la simulación binomial exacta.

2. El asaltante sin modelo. Un participante que no sabe nada de la tarea
   envía vectores de respuestas al azar a un marcador con n ejemplos de
   respuesta binaria, lee la puntuación y se queda con los que superan el
   50 %; su envío es el voto por mayoría de los conservados (el «boosting
   attack» de Blum y Hardt, 2015). Se enfrenta a cuatro evaluadores: el
   ingenuo, que contesta siempre con la puntuación exacta y publica la
   mejor vista; la escalera de Blum y Hardt, que solo publica una mejora
   mayor que eta y la redondea, de modo que el asaltante solo puede
   conservar los vectores que la hacen subir; el anclado, que devuelve
   la exacta durante la época y, al cerrarla, publica la del envío
   combinado sobre un conjunto de anclaje que nunca da retroalimentación;
   y el rotado, cuyo anclaje es la otra mitad del conjunto público y
   cambia de mitad en cada época. En paralelo se mide la exactitud real de cada
   envío sobre un conjunto privado.

Todo es sintético: no interviene ningún dato de ninguna persona. Escribe
los csv, el resumen y la ficha de procedencia junto a sí mismo.
"""
import csv
import datetime
import json
from pathlib import Path

import numpy as np
from scipy.stats import norm
from tqdm import tqdm

DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo
SEMILLA = 20260917

# experimento 1: mejor de k semillas
TAMANOS = (100, 200, 500, 1000, 2000, 5000)
EXACTITUDES = (0.5, 0.7, 0.9)
KS = (1, 2, 3, 5, 10, 20, 50, 100)
REPETICIONES = 20_000

# experimento 2: el asaltante sin modelo
N_MARCADOR = 1000            # ejemplos del conjunto público
N_PRIVADO = 20_000           # ejemplos del conjunto privado, nunca consultado
CONSULTAS = 2000
ETA = 0.01                   # paso de la escalera
EPOCA = 100                  # consultas por época de los evaluadores anclados
TAMANOS_ASALTO = (200, 1000, 5000)
REPETICIONES_ASALTO = 20
EVALUADORES = ("ingenuo", "escalera", "anclado", "rotado", "real")


def esperanza_maximo(k: int, muestras: int = 400_000) -> float:
    """Esperanza del máximo de k normales estándar independientes.

    Args:
        k: número de variables.
        muestras: puntos de la cuadratura sobre la normal.

    Returns:
        E[max(Z_1..Z_k)], integrando k·z·φ(z)·Φ(z)^(k-1).
    """
    if k == 1:
        return 0.0
    z = np.linspace(-8, 8, muestras)
    f = k * z * norm.pdf(z) * norm.cdf(z) ** (k - 1)
    return float(np.trapezoid(f, z))


def mejor_de_k(rng: np.random.Generator) -> list[dict]:
    """Inflación de la cifra publicada al quedarse con la mejor de k.

    Args:
        rng: generador.

    Returns:
        una fila por (n, p, k): desviación en puntos, inflación esperada por
        la aproximación normal y la simulada con binomiales exactas.
    """
    filas = []
    emax = {k: esperanza_maximo(k) for k in KS}
    for n in tqdm(TAMANOS, desc="mejor de k"):
        for p in EXACTITUDES:
            sigma = np.sqrt(p * (1 - p) / n)
            # se simulan de una vez las k=100 tiradas; el máximo de las
            # primeras k sirve para cada k menor
            aciertos = rng.binomial(n, p, size=(REPETICIONES, max(KS)))
            exact = aciertos / n
            for k in KS:
                mejor = exact[:, :k].max(axis=1)
                filas.append({
                    "n": n, "p": p, "k": k,
                    "sigma_puntos": round(100 * sigma, 3),
                    "inflacion_esperada_puntos":
                        round(100 * sigma * emax[k], 3),
                    "inflacion_simulada_puntos":
                        round(100 * (mejor.mean() - p), 3),
                    "percentil_90_puntos":
                        round(100 * (np.quantile(mejor, 0.9) - p), 3),
                })
    return filas


def exactitud(u: np.ndarray, y: np.ndarray) -> float:
    """Fracción de coincidencias entre dos vectores de ±1."""
    return 0.5 * (1 + float((u * y).mean()))


def asalto(n: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    """Una tirada del ataque por mayoría contra los cuatro evaluadores.

    Args:
        n: ejemplos del conjunto público.
        rng: generador.

    Returns:
        series por consulta: puntuación publicada por cada evaluador y
        exactitud real del envío combinado sobre el conjunto privado.
    """
    y_pub = rng.choice([-1, 1], size=n)
    y_ancla = rng.choice([-1, 1], size=n)
    y_priv = rng.choice([-1, 1], size=N_PRIVADO)
    mitad = n // 2
    # el envío combinado se mantiene como suma incremental de los vectores
    # conservados; el rotado lleva la suya porque conserva con otro criterio
    suma_pub = np.zeros(n)
    suma_ancla = np.zeros(n)
    suma_priv = np.zeros(N_PRIVADO)
    suma_esc = np.zeros(n)
    suma_rot = np.zeros(n)
    s = {c: np.zeros(CONSULTAS) for c in EVALUADORES}
    mejor_ingenuo = 0.0
    publicado_escalera = 0.0
    publicado_anclado = 0.5
    publicado_rotado = 0.5
    for t in range(CONSULTAS):
        u = rng.choice([-1, 1], size=n)
        ex_pub = exactitud(u, y_pub)
        # ingenuo y anclado: retroalimentación exacta sobre todo el público
        if ex_pub > 0.5:
            suma_pub += u
            # el mismo envío, prolongado al azar sobre los conjuntos que el
            # asaltante no ve: su exactitud real
            suma_ancla += rng.choice([-1, 1], size=n)
            suma_priv += rng.choice([-1, 1], size=N_PRIVADO)
        voto = np.where(suma_pub >= 0, 1, -1)
        ex_voto = exactitud(voto, y_pub)
        mejor_ingenuo = max(mejor_ingenuo, ex_pub, ex_voto)
        s["ingenuo"][t] = mejor_ingenuo
        # escalera: el asaltante solo ve si la cifra publicada sube, así
        # que conserva justo los vectores que la hacen subir; envía el
        # vector y, después, su voto por mayoría
        subio = False
        if ex_pub > publicado_escalera + ETA:
            publicado_escalera = round(ex_pub / ETA) * ETA
            subio = True
        if subio:
            suma_esc += u
        ex_voto_esc = exactitud(np.where(suma_esc >= 0, 1, -1), y_pub)
        if ex_voto_esc > publicado_escalera + ETA:
            publicado_escalera = round(ex_voto_esc / ETA) * ETA
        s["escalera"][t] = publicado_escalera
        if (t + 1) % EPOCA == 0:
            publicado_anclado = exactitud(
                np.where(suma_ancla >= 0, 1, -1), y_ancla)
        s["anclado"][t] = publicado_anclado
        s["real"][t] = exactitud(np.where(suma_priv >= 0, 1, -1), y_priv)
        # rotado: retroalimentación solo sobre la mitad activa; al cerrar la
        # época se publica el voto sobre la otra mitad, y se cambian
        activa = slice(0, mitad) if (t // EPOCA) % 2 == 0 else slice(mitad, n)
        otra = slice(mitad, n) if (t // EPOCA) % 2 == 0 else slice(0, mitad)
        if exactitud(u[activa], y_pub[activa]) > 0.5:
            suma_rot += u
        if (t + 1) % EPOCA == 0:
            voto_rot = np.where(suma_rot >= 0, 1, -1)
            publicado_rotado = exactitud(voto_rot[otra], y_pub[otra])
        s["rotado"][t] = publicado_rotado
    return s


def asaltos() -> tuple[list[dict], list[dict]]:
    """El ataque repetido, para el n principal y para la tabla por tamaños.

    Returns:
        la serie media por consulta para n=N_MARCADOR, y el resumen a
        cuatro alturas de consulta para cada tamaño.
    """
    series: list[dict] = []
    resumen: list[dict] = []
    for n in TAMANOS_ASALTO:
        acum = {c: np.zeros(CONSULTAS) for c in EVALUADORES}
        for r in tqdm(range(REPETICIONES_ASALTO), desc=f"asalto n={n}"):
            una = asalto(n, np.random.default_rng(SEMILLA + 1000 * n + r))
            for c in acum:
                acum[c] += una[c] / REPETICIONES_ASALTO
        if n == N_MARCADOR:
            for t in range(CONSULTAS):
                fila = {"consulta": t + 1}
                fila.update({c: round(100 * acum[c][t], 3)
                             for c in EVALUADORES})
                series.append(fila)
        for q in (100, 500, 1000, 2000):
            fila = {"n": n, "consultas": q}
            fila.update({c: round(100 * acum[c][q - 1], 2)
                         for c in EVALUADORES})
            resumen.append(fila)
    return series, resumen


def escribir_csv(nombre: str, filas: list[dict]) -> None:
    """Guarda las filas en csv junto al guion.

    Args:
        nombre: fichero de destino.
        filas: diccionarios con las mismas claves.
    """
    with open(DESTINO / nombre, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


def main() -> None:
    """Corre los dos experimentos y persiste csv, resumen y ficha."""
    semillas = mejor_de_k(np.random.default_rng(SEMILLA))
    escribir_csv("semillas.csv", semillas)
    series, por_tamano = asaltos()
    escribir_csv("asalto-serie.csv", series)
    escribir_csv("asalto-por-tamano.csv", por_tamano)

    def fila(n, p, k):
        return next(f for f in semillas
                    if f["n"] == n and f["p"] == p and f["k"] == k)

    ultimo = series[-1]
    res = {
        "fecha": datetime.date.today().isoformat(),
        "semilla": SEMILLA,
        "repeticiones_semillas": REPETICIONES,
        "repeticiones_asalto": REPETICIONES_ASALTO,
        "mejor_de_k": {
            "n500_p07_k5": fila(500, 0.7, 5)["inflacion_simulada_puntos"],
            "n500_p07_k10": fila(500, 0.7, 10)["inflacion_simulada_puntos"],
            "n500_p07_k100":
                fila(500, 0.7, 100)["inflacion_simulada_puntos"],
            "n100_p07_k10": fila(100, 0.7, 10)["inflacion_simulada_puntos"],
            "n5000_p07_k10":
                fila(5000, 0.7, 10)["inflacion_simulada_puntos"],
            "esperanza_maximo":
                {k: round(esperanza_maximo(k), 3) for k in KS},
        },
        "asalto": {
            "n": N_MARCADOR, "consultas": CONSULTAS, "eta": ETA,
            "epoca": EPOCA,
            "final": {c: ultimo[c] for c in EVALUADORES},
            "por_tamano": por_tamano,
        },
    }
    (DESTINO / "resumen.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    ficha = "\n".join([
        "# El evaluador dentro del bucle: dos experimentos sintéticos", "",
        f"Simulaciones con `numpy` {np.__version__}, semilla {SEMILLA}, "
        f"generadas el {res['fecha']}. No interviene ningún dato de ninguna "
        "persona: las etiquetas, los envíos y las tiradas son aleatorios.", "",
        "## `semillas.csv` — el mejor de k", "",
        "Un modelo con exactitud real `p` evaluado `k` veces sobre `n` "
        "preguntas; cada evaluación es una binomial(n, p)/n y se publica la "
        f"mejor de las k. {REPETICIONES} repeticiones por celda.", "",
        "| Columna | Origen |", "|---|---|",
        "| `n`, `p`, `k` | tamaño del banco, exactitud real, evaluaciones "
        "entre las que se elige |",
        "| `sigma_puntos` | 100·sqrt(p(1-p)/n): la desviación de una "
        "evaluación, en puntos |",
        "| `inflacion_esperada_puntos` | sigma por la esperanza del máximo "
        "de k normales estándar (integración numérica) |",
        "| `inflacion_simulada_puntos` | media de (mejor de k − p), en "
        "puntos, sobre las repeticiones |",
        "| `percentil_90_puntos` | percentil 90 de la misma diferencia |", "",
        "## `asalto-serie.csv` y `asalto-por-tamano.csv` — el asaltante "
        "sin modelo", "",
        "Marcador con `n` ejemplos de respuesta binaria equilibrada; el "
        f"asaltante envía {CONSULTAS} vectores al azar, lee lo que el "
        "evaluador publica y combina por mayoría los que le convienen "
        "(Blum y Hardt, 2015). Cuatro evaluadores sobre la misma secuencia "
        "de envíos; cada columna es la cifra que ese evaluador publica tras "
        "cada consulta, y el asaltante solo ve esa cifra:", "",
        "| Columna | Evaluador |", "|---|---|",
        "| `ingenuo` | devuelve la puntuación exacta y publica la mejor "
        "vista; el asaltante conserva los vectores que superan el 50 % |",
        f"| `escalera` | solo publica una mejora mayor que eta={ETA}, "
        "redondeada a múltiplos de eta; el asaltante conserva los vectores "
        "que la hacen subir |",
        f"| `anclado` | devuelve la exacta durante la época de {EPOCA} "
        "consultas y, al cerrarla, publica la del envío combinado sobre un "
        "conjunto de anclaje de `n` ejemplos que nunca da "
        "retroalimentación |",
        "| `rotado` | como el anclado, pero el anclaje es la otra mitad del "
        "conjunto público y las mitades se intercambian en cada época |",
        f"| `real` | exactitud del envío combinado sobre {N_PRIVADO} "
        "ejemplos privados |", "",
        f"Media de {REPETICIONES_ASALTO} tiradas. La serie es para "
        f"n={N_MARCADOR}; la tabla por tamaño, para n en {TAMANOS_ASALTO} "
        "a 100, 500, 1000 y 2000 consultas.", "",
    ])
    (DESTINO / "INSTANTANEA.md").write_text(ficha, encoding="utf-8")
    print(json.dumps(res["mejor_de_k"], ensure_ascii=False, indent=1))
    print("asalto final:", res["asalto"]["final"])
    for f in por_tamano:
        print(f)


if __name__ == "__main__":
    main()
