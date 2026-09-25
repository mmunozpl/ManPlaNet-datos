#!/usr/bin/env python3
"""Una fila real de la proyección de salida de Pythia-410M, para la figura
de la rejilla de la entrada: los 64 pesos de la cabeza 3 en la fila 100 de
`gpt_neox.layers.12.attention.dense.weight`, y su redondeo INT4 simétrico
por fila (escala = máximo de la fila / 7), el mismo cuantizador del trabajo.

Necesita los pesos públicos de EleutherAI/pythia-410m en la caché de
Hugging Face; escribe `fila-w_o-pythia.csv` junto a sí mismo. Solo 64
números de una matriz de 1024×1024: no redistribuye el modelo.
"""
import csv
import glob
import json
import os
from pathlib import Path

import numpy as np
from safetensors import safe_open

CAPA, CABEZA, FILA, BITS = 12, 3, 100, 4
DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo

snap = glob.glob(os.path.expanduser(
    "~/.cache/huggingface/hub/models--EleutherAI--pythia-410m/snapshots/*/"))[0]
cfg = json.load(open(snap + "config.json"))
hd = cfg["hidden_size"] // cfg["num_attention_heads"]
with safe_open(snap + "model.safetensors", "pt") as f:
    W = f.get_tensor(f"gpt_neox.layers.{CAPA}.attention.dense.weight")
W = W.float().numpy()
fila = W[FILA, CABEZA * hd:(CABEZA + 1) * hd]          # 64 pesos
qmax = 2 ** (BITS - 1) - 1                                # 7: rango simétrico
escala = np.abs(fila).max() / qmax
q = np.clip(np.round(fila / escala), -qmax, qmax)
with open(DESTINO / "fila-w_o-pythia.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["indice", "peso", "nivel", "peso_cuantizado"])
    for i, (p, n) in enumerate(zip(fila, q)):
        w.writerow([i, f"{p:.8f}", int(n), f"{n * escala:.8f}"])
print(f"capa {CAPA} cabeza {CABEZA} fila {FILA}: {len(fila)} pesos, "
      f"escala {escala:.6f}, niveles usados {len(set(q.tolist()))}, "
      f"error medio {np.abs(fila - q * escala).mean():.6f}")
