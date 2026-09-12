#!/usr/bin/env python3
"""Simulación del muestreo de máscaras de I-JEPA, con sus parámetros.

Reimplementa el procedimiento de `src/masks/multiblock.py` del repositorio
de los autores con la configuración `in1k_vith14_ep300.yaml`, y mide qué
produce: cuántos parches conserva el contexto, dónde caen los bloques sobre
la rejilla y qué efecto tiene el truncado al mínimo del lote.

No descarga imágenes ni pesos: solo genera máscaras, que son índices sobre
una rejilla de parches.
"""
import csv
import datetime
import json
import math
from pathlib import Path

import numpy as np

# --- configuración de los autores, in1k_vith14_ep300.yaml -------------------
CROP = 224
PATCH = 14
LADO = CROP // PATCH               # 16 parches por lado
N = LADO * LADO                    # 256 parches
ENC_SCALE = (0.85, 1.0)
PRED_SCALE = (0.15, 0.2)
ASPECT = (0.75, 1.5)
NENC, NPRED = 1, 4
MIN_KEEP = 10
LOTE = 128                         # data.batch_size
SEMILLA = 20260910
DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo


def tamano_bloque(rng, escala, aspecto):
    """Tamaño de bloque. Una sola extracción gobierna escala Y proporción,
    igual que en el original: quedan perfectamente correlacionadas."""
    r = rng.random()
    s = escala[0] + r * (escala[1] - escala[0])
    max_keep = int(N * s)
    ar = aspecto[0] + r * (aspecto[1] - aspecto[0])
    h = int(round(math.sqrt(max_keep * ar)))
    w = int(round(math.sqrt(max_keep / ar)))
    while h >= LADO:
        h -= 1
    while w >= LADO:
        w -= 1
    return h, w


def muestrear_bloque(rng, hw, regiones=None):
    """Coloca un bloque; si hay regiones aceptables, lo recorta a ellas y
    reintenta hasta superar min_keep, relajando cada 20 intentos."""
    h, w = hw
    tries, timeout, relajaciones = 0, 20, 0
    while True:
        top = rng.integers(0, LADO - h)     # el original excluye el extremo
        left = rng.integers(0, LADO - w)
        m = np.zeros((LADO, LADO), dtype=np.int32)
        m[top:top + h, left:left + w] = 1
        if regiones is not None:
            for k in range(max(len(regiones) - tries, 0)):
                m = m * regiones[k]
        idx = np.flatnonzero(m)
        if len(idx) > MIN_KEEP:
            comp = np.ones((LADO, LADO), dtype=np.int32)
            comp[top:top + h, left:left + w] = 0
            return idx, comp, relajaciones
        timeout -= 1
        if timeout == 0:
            tries += 1
            relajaciones += 1
            timeout = 20


def simular(n_lotes: int) -> dict:
    rng = np.random.default_rng(SEMILLA)
    ctx_bruto, ctx_truncado, obj_bruto = [], [], []
    min_enc_lote, min_pred_lote = [], []
    cob_obj = np.zeros(N, dtype=np.int64)
    cob_ctx = np.zeros(N, dtype=np.int64)
    tam_pred, tam_enc, relaj = [], [], 0

    for _ in range(n_lotes):
        # el tamaño se sortea UNA vez por lote; solo varía la posición
        p_hw = tamano_bloque(rng, PRED_SCALE, ASPECT)
        e_hw = tamano_bloque(rng, ENC_SCALE, (1.0, 1.0))   # contexto cuadrado
        tam_pred.append(p_hw)
        tam_enc.append(e_hw)
        enc_lote, pred_lote = [], []
        for _ in range(LOTE):
            comps, objs = [], []
            for _ in range(NPRED):
                idx, comp, r = muestrear_bloque(rng, p_hw)
                objs.append(idx); comps.append(comp); relaj += r
                obj_bruto.append(len(idx))
            idx_e, _, r = muestrear_bloque(rng, e_hw, regiones=comps)
            relaj += r
            ctx_bruto.append(len(idx_e))
            enc_lote.append(idx_e); pred_lote.append(objs)
        me = min(len(x) for x in enc_lote)
        mp = min(len(y) for x in pred_lote for y in x)
        min_enc_lote.append(me); min_pred_lote.append(mp)
        for idx_e in enc_lote:
            rec = idx_e[:me]                 # truncado en orden de barrido
            ctx_truncado.append(len(rec))
            cob_ctx[rec] += 1
        for objs in pred_lote:
            for idx in objs:
                cob_obj[idx[:mp]] += 1

    return dict(ctx_bruto=np.array(ctx_bruto), ctx_truncado=np.array(ctx_truncado),
                obj_bruto=np.array(obj_bruto), min_enc=np.array(min_enc_lote),
                min_pred=np.array(min_pred_lote), cob_obj=cob_obj,
                cob_ctx=cob_ctx, tam_pred=tam_pred, tam_enc=tam_enc,
                relajaciones=relaj, n_lotes=n_lotes)


def main(n_lotes: int = 40) -> None:
    r = simular(n_lotes)
    DESTINO.mkdir(parents=True, exist_ok=True)

    with (DESTINO / "cobertura.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fila", "columna", "veces_objetivo", "veces_contexto"])
        for i in range(N):
            w.writerow([i // LADO, i % LADO, int(r["cob_obj"][i]),
                        int(r["cob_ctx"][i])])

    with (DESTINO / "muestras.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["contexto_bruto", "contexto_truncado"])
        for a, b in zip(r["ctx_bruto"], r["ctx_truncado"]):
            w.writerow([int(a), int(b)])

    res = {
        "semilla": SEMILLA, "lotes": n_lotes, "lote": LOTE,
        "imagenes": n_lotes * LOTE, "rejilla": [LADO, LADO], "parches": N,
        "contexto_bruto": {"media": float(r["ctx_bruto"].mean()),
                           "mediana": float(np.median(r["ctx_bruto"])),
                           "min": int(r["ctx_bruto"].min()),
                           "max": int(r["ctx_bruto"].max())},
        "contexto_truncado": {"media": float(r["ctx_truncado"].mean()),
                              "min": int(r["ctx_truncado"].min()),
                              "max": int(r["ctx_truncado"].max())},
        "objetivo_bruto": {"media": float(r["obj_bruto"].mean()),
                           "min": int(r["obj_bruto"].min()),
                           "max": int(r["obj_bruto"].max())},
        "min_enc_por_lote": {"media": float(r["min_enc"].mean()),
                             "min": int(r["min_enc"].min())},
        "relajaciones": int(r["relajaciones"]),
        "tam_pred": sorted({tuple(map(int, t)) for t in r["tam_pred"]}),
        "tam_enc": sorted({tuple(map(int, t)) for t in r["tam_enc"]}),
        "extraido": datetime.date.today().isoformat(),
    }
    (DESTINO / "resumen.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
