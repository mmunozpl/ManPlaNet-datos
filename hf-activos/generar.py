#!/usr/bin/env python3
"""Parámetros totales y parámetros activos por token en los cien modelos en
tendencia del Hub de Hugging Face, contados tensor a tensor.

No descarga pesos: lee la cabecera de cada fichero `.safetensors` con una
petición de rango (los primeros bytes llevan la lista de tensores con su
forma), suma los elementos de cada tensor y separa dos clases que un token
no usa enteras: los expertos enrutados que no se seleccionan, y las tablas
de consulta —el embedding de entrada y las memorias de n-gramas, como PLE o
Engram— de las que cada token lee unas pocas filas. Con el número de
expertos activos por token que declara `config.json`, los parámetros
activos son el total menos esas dos partes. Los expertos compartidos, la
atención, los MLP densos y la cabeza de salida cuentan siempre.

Los repositorios con pesos a 4 bits o empaquetados no se cuentan por tensor
(el número de elementos no es el de parámetros): se deja el total que
publica el Hub. Se guarda en csv y se escribe la ficha de procedencia.
"""
import csv
import datetime
import hashlib
import json
import os
import re
import struct
import time
import urllib.error
import urllib.request
from pathlib import Path

DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo
API = "https://huggingface.co/api/models"
UA = "Mozilla/5.0 (X11; Linux x86_64) Firefox/128.0"
N = 100
PAUSA = 0.25                 # segundos entre peticiones al Hub
CLAVES_K = ("num_experts_per_tok", "experts_per_token",
            "num_experts_per_token", "moe_topk", "topk",
            "num_selected_experts", "top_k_experts", "experts_gating_top")
CLAVES_E = ("n_routed_experts", "num_experts", "num_local_experts",
            "moe_num_experts", "num_routed_experts", "n_experts")
TABLA = re.compile(r"embed_tokens|word_embeddings|\bwte\b|ngram_embedding"
                   r"|ple_embedding|engram", re.I)
EMPAQUETADO = ("U8", "I8", "U32", "I32", "U16", "F4", "E2M1")


def pedir(url: str, rango: str | None = None) -> bytes:
    """descarga con cabecera de navegador; `rango` es un Range HTTP. Ante
    un 429 o un error del servidor espera y reintenta, para no dejar
    shards fuera del recuento."""
    cab = {"User-Agent": UA}
    if rango:
        cab["Range"] = f"bytes={rango}"
    for intento, espera in enumerate((0, 5, 20, 60, 120)):
        if espera:
            time.sleep(espera)
        try:
            req = urllib.request.Request(url, headers=cab)
            with urllib.request.urlopen(req, timeout=120) as r:
                time.sleep(PAUSA)
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 499, 500, 502, 503, 504) and intento < 4:
                continue
            raise
    raise RuntimeError("sin respuesta")


def cabecera_safetensors(url: str) -> dict:
    """la lista de tensores de un .safetensors leyendo solo su cabecera;
    con HF_ACTIVOS_CACHE definido se guarda en disco, para repetir la
    medición sin volver a pedirla."""
    cache = os.environ.get("HF_ACTIVOS_CACHE")
    f = None
    if cache:
        f = Path(cache) / (hashlib.md5(url.encode()).hexdigest() + ".json")
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    n = struct.unpack("<Q", pedir(url, "0-7")[:8])[0]
    cab = json.loads(pedir(url, f"8-{8 + n - 1}").decode("utf-8"))
    if f:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(cab), encoding="utf-8")
    return cab


def numel(forma: list) -> int:
    n = 1
    for d in forma:
        n *= d
    return n


def config_de(modelo: str) -> dict:
    try:
        url = f"https://huggingface.co/{modelo}/raw/main/config.json"
        return json.loads(pedir(url))
    except Exception:
        return {}


def texto_de(cfg: dict) -> dict:
    """las claves de lenguaje pueden vivir en text_config (multimodales)."""
    sub = cfg.get("text_config") or cfg.get("language_config") or {}
    return {**cfg, **sub} if isinstance(sub, dict) else cfg


def primero(cfg: dict, claves: tuple) -> int | None:
    for k in claves:
        v = cfg.get(k)
        if isinstance(v, int) and v > 0:
            return v
    return None


def ficheros_safetensors(modelo: str, detalle: dict) -> list[str]:
    """los shards del modelo: los del índice si lo hay; si no, los que
    siguen el patrón model-N-of-M o el model.safetensors único. Así no
    entran adaptadores LoRA u otros ficheros sueltos de la raíz."""
    raiz = [s["rfilename"] for s in detalle.get("siblings", [])
            if "/" not in s["rfilename"]]
    if "model.safetensors.index.json" in raiz:
        try:
            url = (f"https://huggingface.co/{modelo}/resolve/main/"
                   "model.safetensors.index.json")
            idx = json.loads(pedir(url))
            return sorted(set(idx.get("weight_map", {}).values()))
        except Exception:
            pass
    patron = re.compile(r"model-\d+-of-\d+\.safetensors")
    shards = sorted(f for f in raiz if patron.fullmatch(f))
    if shards:
        return shards
    if "model.safetensors" in raiz:
        return ["model.safetensors"]
    return sorted(f for f in raiz if f.endswith(".safetensors"))


def cuantizado(cfg: dict, tensores: dict) -> bool:
    """4 bits o pesos empaquetados: el número de elementos no es el de
    parámetros, y el recuento por tensor no vale."""
    q = cfg.get("quantization_config") or cfg.get("quantization") or {}
    bits = (q.get("bits") or q.get("num_bits")) if isinstance(q, dict) else None
    if isinstance(bits, int) and bits < 8:
        return True
    if str(cfg.get("expert_dtype", "")).lower() in ("fp4", "e2m1", "nvfp4",
                                                     "mxfp4", "int4"):
        return True
    return any(d in EMPAQUETADO for _, _, d in tensores.values())


def grupos_k(cfg: dict) -> list[tuple[int, int]]:
    """parejas (expertos, activos por token) declaradas en el config; la
    primera es la principal y las demás cubren familias con más de un
    enrutador (por ejemplo, expertos de atención además de los del MLP)."""
    parejas = []
    e0, k0 = primero(cfg, CLAVES_E), primero(cfg, CLAVES_K)
    if e0 and k0:
        parejas.append((e0, k0))
    for clave, val in cfg.items():
        m = re.fullmatch(r"(.+_)num_experts", clave)
        if m and isinstance(val, int) and val > 0:
            k = cfg.get(m.group(1) + "num_experts_per_tok")
            if isinstance(k, int) and k > 0:
                parejas.append((val, k))
    return parejas


def k_para(e: int, parejas: list[tuple[int, int]]) -> int | None:
    for ee, kk in parejas:
        if ee == e:
            return kk
    return parejas[0][1] if parejas else None


def contar(modelo: str, detalle: dict, cfg: dict) -> dict | None:
    """total, expertos, tablas y activos, desde las cabeceras de los shards."""
    ficheros = ficheros_safetensors(modelo, detalle)
    if not ficheros:
        return None
    tensores = {}
    for f in ficheros:
        url = f"https://huggingface.co/{modelo}/resolve/main/{f}"
        try:
            cab = cabecera_safetensors(url)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return {"sin_acceso": True}
            print(f"    [aviso] {modelo}/{f}: HTTP {e.code}; incompleto")
            return {"incompleto": True}
        except Exception as e:
            print(f"    [aviso] {modelo}/{f}: {str(e)[:60]}; incompleto")
            return {"incompleto": True}
        for nombre, info in cab.items():
            if nombre != "__metadata__":
                tensores[nombre] = (numel(info["shape"]), info["shape"],
                                    info["dtype"])
    if not tensores:
        return None
    total = sum(n for n, _, _ in tensores.values())
    t = texto_de(cfg)
    if cuantizado(t, tensores):
        return {"cuantizado": True, "params_elementos": total,
                "shards": len(ficheros), "tensores": len(tensores)}
    parejas = grupos_k(t)
    e_cfg = parejas[0][0] if parejas else None
    # expertos enrutados: por índice (…experts.N.…) o fusionados
    # (…experts.peso con la primera dimensión igual al número de expertos)
    por_capa, fusionados, tablas = {}, {}, 0
    for nombre, (n, forma, _) in tensores.items():
        bajo = nombre.lower()
        if TABLA.search(bajo) and "lm_head" not in bajo:
            tablas += n
            continue
        if "shared_expert" in bajo:
            continue
        m = re.search(r"^(.*?experts)\.(\d+)\.", nombre)
        if m:
            grupo = por_capa.setdefault(m.group(1), {})
            grupo[int(m.group(2))] = grupo.get(int(m.group(2)), 0) + n
            continue
        m = re.search(r"^(.*?experts)\.", nombre)
        if m and len(forma) >= 2:
            fusionados.setdefault(m.group(1), []).append((n, forma))
    inactivos = capas_moe = params_expertos = 0
    expertos_por_capa = k_principal = None
    for capa, exps in por_capa.items():
        e, tam = len(exps), sum(exps.values())
        k = k_para(e, parejas)
        params_expertos += tam
        if k and e > k:
            inactivos += tam * (e - k) / e
        capas_moe += 1
        if capa.endswith("mlp.experts") or expertos_por_capa is None:
            expertos_por_capa, k_principal = e, k
    for capa, lst in fusionados.items():
        dims = [f[0] for _, f in lst]
        if e_cfg in dims:
            e, dim = e_cfg, e_cfg
        elif e_cfg and any(d % e_cfg == 0 for d in dims):
            # expertos apilados por filas: [E·intermedio, oculto]
            dim = max(d for d in dims if d % e_cfg == 0)
            e = e_cfg
        else:
            e = dim = max(dims)
        lst_e = [(n, f) for n, f in lst if f[0] == dim]
        if not lst_e:
            continue
        tam = sum(n for n, _ in lst_e)
        k = k_para(e, parejas)
        params_expertos += tam
        if k and e > k:
            inactivos += tam * (e - k) / e
        capas_moe += 1
        if capa.endswith("mlp.experts") or expertos_por_capa is None:
            expertos_por_capa, k_principal = e, k
    return {"params_total": total, "params_expertos": params_expertos,
            "params_tablas": tablas, "capas_moe": capas_moe,
            "expertos_por_capa": expertos_por_capa,
            "activos_por_token": k_principal,
            "params_activos": round(total - inactivos - tablas),
            "params_activos_con_tablas": round(total - inactivos),
            "shards": len(ficheros), "tensores": len(tensores)}


def declarado(nombre: str) -> tuple[float | None, float | None]:
    """los parámetros que el nombre del repositorio declara: 35B-A3B."""
    m = re.search(r"(\d+(?:\.\d+)?)B-A(\d+(?:\.\d+)?)B", nombre, re.I)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r"[-_](\d+(?:\.\d+)?)B\b", nombre, re.I)
    return (float(m.group(1)), None) if m else (None, None)


CAMPOS = ["puesto", "modelo", "pipeline", "creado", "likes", "arquitectura",
          "tipo", "gguf", "params_total_hub", "params_elementos",
          "params_total", "params_activos", "fraccion_activa",
          "params_activos_con_tablas", "params_expertos", "params_tablas",
          "capas_moe", "expertos_por_capa", "activos_por_token",
          "declarado_total_B", "declarado_activo_B", "shards", "tensores"]
TIPOS = ("moe", "denso", "cuantizado", "gguf", "sin safetensors",
         "sin acceso", "incompleto")


def main() -> None:
    hoy = datetime.date.today().isoformat()
    lista = json.loads(pedir(f"{API}?sort=trendingScore&direction=-1"
                             f"&limit={N}&full=true"))
    filas = []
    for i, m in enumerate(lista, 1):
        mid = m["id"]
        detalle = json.loads(pedir(f"{API}/{mid}"))
        es_gguf = bool(detalle.get("gguf")) or mid.lower().endswith("gguf")
        cfg = config_de(mid) if not es_gguf else {}
        arq = (cfg.get("architectures") or ["—"])[0] if cfg else "—"
        tot_decl, act_decl = declarado(mid)
        hub = (detalle.get("safetensors") or {}).get("total")
        fila = {"puesto": i, "modelo": mid,
                "pipeline": m.get("pipeline_tag") or "",
                "creado": (m.get("createdAt") or "")[:10],
                "likes": m.get("likes", 0), "arquitectura": arq,
                "gguf": int(es_gguf), "declarado_total_B": tot_decl,
                "declarado_activo_B": act_decl, "params_total_hub": hub}
        cuenta = contar(mid, detalle, cfg) if not es_gguf else None
        if cuenta and cuenta.get("sin_acceso"):
            fila["tipo"] = "sin acceso"
        elif cuenta and cuenta.get("incompleto"):
            fila["tipo"] = "incompleto"
        elif cuenta and cuenta.get("cuantizado"):
            fila.update({k: v for k, v in cuenta.items() if k != "cuantizado"})
            fila["tipo"] = "cuantizado"
        elif cuenta:
            fila.update(cuenta)
            fila["tipo"] = "moe" if cuenta["capas_moe"] else "denso"
            fila["fraccion_activa"] = round(
                cuenta["params_activos"] / cuenta["params_total"], 4)
        else:
            fila["tipo"] = "gguf" if es_gguf else "sin safetensors"
        filas.append(fila)
        print(f"[{i:>3}] {mid[:50]:<50} {fila['tipo']:<15} "
              f"{(fila.get('params_total') or 0) / 1e9:7.1f}B total · "
              f"{(fila.get('params_activos') or 0) / 1e9:6.1f}B activos · "
              f"k={fila.get('activos_por_token')} "
              f"E={fila.get('expertos_por_capa')}")
    with (DESTINO / "activos.csv").open("w", newline="",
                                        encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    moe = [f for f in filas if f["tipo"] == "moe"]
    fr = sorted(f["fraccion_activa"] for f in moe)
    resumen = {
        "extraido": hoy, "modelos": len(filas),
        "por_tipo": {t: sum(1 for f in filas if f["tipo"] == t)
                     for t in TIPOS},
        "moe_fraccion_activa_mediana": fr[len(fr) // 2] if fr else None,
        "moe_fraccion_activa_min": fr[0] if fr else None,
        "moe_fraccion_activa_max": fr[-1] if fr else None,
        "con_A_en_el_nombre": sum(1 for f in filas
                                  if f["declarado_activo_B"]),
        "params_total_suma_B": round(
            sum(f.get("params_total") or 0 for f in filas) / 1e9, 1),
        "params_activos_suma_B": round(
            sum(f.get("params_activos") or 0 for f in filas) / 1e9, 1),
    }
    (DESTINO / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in resumen.items():
        print(f"[resumen] {k}: {v}")
    (DESTINO / "INSTANTANEA.md").write_text(f"""\
# Parámetros activos por token en los cien modelos en tendencia del Hub

Recuento tensor a tensor sobre las cabeceras de los ficheros `.safetensors`
(petición de rango: los primeros bytes de cada shard llevan la lista de
tensores con su forma), sin descargar pesos. No interviene ningún dato de
ninguna persona.

- Lista: `{API}?sort=trendingScore&direction=-1&limit={N}`
- Extraído: {hoy}

## Campos de `activos.csv`

| Columna | Origen |
|---|---|
| `puesto`, `modelo`, `pipeline`, `creado`, `likes` | la lista en tendencia del Hub |
| `arquitectura` | `architectures[0]` del `config.json` |
| `tipo` | `moe` si hay tensores de expertos enrutados; `denso` si no; `cuantizado` si los pesos van a 4 bits o empaquetados (el recuento por tensor no vale y se deja el total del Hub); `gguf` si el repositorio es una copia en ese formato; `sin safetensors` si no hay pesos en ese formato en la raíz; `sin acceso` si exige aceptar condiciones; `incompleto` si algún shard no se pudo leer |
| `params_total_hub` | el total que publica la API del Hub para el repositorio |
| `params_elementos` | en los cuantizados, elementos contados en las cabeceras (no parámetros) |
| `params_total` | suma de elementos de todos los tensores |
| `params_expertos` | elementos de los expertos enrutados (`…experts.N.…` o fusionados `…experts.peso`) |
| `params_tablas` | tablas de consulta: embedding de entrada y memorias de n-gramas (PLE, Engram) |
| `capas_moe`, `expertos_por_capa`, `activos_por_token` | capas con expertos, expertos por capa y el `k` del config |
| `params_activos` | total − expertos no usados por token − tablas; expertos compartidos, atención, MLP densos y cabeza de salida cuentan siempre |
| `params_activos_con_tablas` | lo mismo sin descontar las tablas, que es la convención de muchas fichas |
| `fraccion_activa` | `params_activos / params_total` |
| `declarado_total_B`, `declarado_activo_B` | lo que el nombre del repositorio dice (`35B-A3B`) |
| `shards`, `tensores` | cuántos ficheros y tensores se leyeron |
""", encoding="utf-8")


if __name__ == "__main__":
    main()
