"""Lectura de un modelo abierto derivado sin descargar sus pesos.

Caso: ``abacusai/Smaug-Nemotron-3.5``, un ajuste fino agéntico de
``nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16`` (120.000 millones de
parámetros, 249 GB en BF16). Todo sale de la API pública de Hugging Face y
de lecturas por rango de bytes sobre los ``safetensors``, con las dos
revisiones fijadas; no hace falta GPU ni descargar los pesos completos.

Etapas, todas reejecutables (lo descargado se guarda en ``crudo/``):

1. ``metadatos``: ficheros, huellas y commits de los repositorios.
2. ``codigo``: qué ficheros de código y configuración difieren, y con qué
   revisión de la base coincide el código del derivado.
3. ``fichas``: las cifras de evaluación de cada versión de la ficha del
   derivado y la de Terminal-Bench 2.1 en cada versión de la de NVIDIA.
4. ``cabeceras``: la cabecera de los 64 ``safetensors`` de cada modelo.
5. ``censo``: una ventana de 4 KiB de cada uno de los 43.079 tensores (tres
   en los que no son expertos enrutados), comparada byte a byte.
6. ``rango``: dos tensores completos y los valores singulares de su
   diferencia, frente a la misma diferencia barajada.
7. ``ruido``: error típico de cada diferencia por muestreo de tareas.
8. ``derivados``: el árbol de modelos derivados de la base y los modelos
   del Hub cuyo nombre anuncia que se les han quitado los rechazos.
9. ``rechazos``: las tasas de rechazo que declaran dos derivados sin
   rechazos, transcritas de sus fichas a revisión fijada.
10. ``contraste``: el censo y el rango repetidos sobre dos derivados más,
    Heretic (misma base, ablación de los rechazos) y Smaug-Uncensored
    (sobre Qwen3.8-27B, LoRA de rango 16), con el papel de cada matriz en
    el flujo residual.
11. ``inventario``: los pares base-derivado sin rechazos más descargados del
    Hub con pesos completos, con licencia, disposición de los tensores y si
    la ficha publica cifras de rechazo; la conducta no se mide.

Uso, desde la raíz del repositorio de datos::

    uv sync --frozen --group generadores
    uv run python smaug-nemotron/generar.py                # todas
    uv run python smaug-nemotron/generar.py --etapa censo  # una sola

Requisitos: menos de 1 GB de descarga (los tensores completos de las etapas
``rango`` y ``contraste``) y alrededor de dos horas, casi todas en los dos
censos del modelo de NVIDIA.
Hugging Face limita a 3.000 resoluciones de fichero cada cinco minutos, así
que cada ``safetensors`` se resuelve una sola vez y las lecturas por rango
van contra la URL firmada a la que redirige.
"""

import argparse
import csv
import glob
import hashlib
import json
import random
import re
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

AQUI = Path(__file__).resolve().parent
CRUDO = AQUI / "crudo"
UA = {"User-Agent": "Mozilla/5.0"}
HF = "https://huggingface.co"

DERIVADO = "abacusai/Smaug-Nemotron-3.5"
BASE = "nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16"
NVFP4 = "abacusai/Smaug-Nemotron-3.5-NVFP4"
REV = {
    DERIVADO: "3c8ce0116f0f33846d3677392ea9a69aae21519c",
    BASE: "fb0ee0bc6b3f70342afd8d84cb80dbadbaa8a1fe",
    NVFP4: "bfaba74d60559641e9d44f320a63691a2ec3263f",
}
# revisión de la base anterior a su commit del 22-10-2026
BASE_PREVIA = "1f8953f7f0"
CORTOS = {"s": DERIVADO, "b": BASE}
SHARDS = [f"model-{i:05d}-of-00063.safetensors" for i in range(1, 64)]
SHARDS.append("model-summary-idxs.safetensors")
VENTANA = 4096
SEMILLA = 2026

# derivados que declaran haber quitado los rechazos, a revisión fijada
HERETIC = ("spiritfather/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-heretic-ara",
           "508adb514cf1ad2177dcce3452146629e35b22f9")
UNCENSORED = ("abacusai/Smaug-Uncensored",
              "e4bbcf7aec54ab72f4ce720569f3b3dc7b973087")
QWEN = ("Qwen/Qwen3.8-27B", "37561816e66b5b9153b1b64c10968c18c1e6f4a0")
REV.update({HERETIC[0]: HERETIC[1], UNCENSORED[0]: UNCENSORED[1],
            QWEN[0]: QWEN[1]})
# claves cortas de todos los repositorios que se leen por rangos
REPOS = {**CORTOS, "h": HERETIC[0], "u": UNCENSORED[0], "q": QWEN[0]}
SHARDS_QWEN = [f"model-{i:05d}-of-00018.safetensors" for i in range(1, 19)]
TERMINOS_SIN_RECHAZOS = ("abliterated", "uncensored", "heretic")


# --- utilidades de red -------------------------------------------------------

def pedir(url: str, cabeceras: dict | None = None, intentos: int = 8,
          bruto: bool = False):
    """Hace una petición GET con reintentos ante 429 y errores de red.

    Args:
        url: dirección completa.
        cabeceras: cabeceras adicionales (por ejemplo, ``Range``).
        intentos: número máximo de intentos.
        bruto: si es cierto, devuelve también la respuesta.

    Returns:
        Los bytes leídos, o la tupla (bytes, respuesta) si ``bruto``.
    """
    for i in range(intentos):
        try:
            r = urllib.request.urlopen(
                urllib.request.Request(url, headers={**UA, **(cabeceras or {})}),
                timeout=300)
            datos = r.read()
            return (datos, r) if bruto else datos
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            espera = int(e.headers.get("Retry-After") or 0) or 5 * (i + 1)
            time.sleep(espera)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"sin respuesta: {url}")


def api(ruta: str) -> dict | list:
    """Lee un recurso JSON de la API de Hugging Face."""
    return json.loads(pedir(f"{HF}/api/{ruta}"))


def fichero(repo: str, rev: str, nombre: str) -> bytes:
    """Descarga un fichero de un repositorio a una revisión, con caché."""
    destino = CRUDO / "ficheros" / repo.replace("/", "__") / rev / nombre
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(pedir(f"{HF}/{repo}/resolve/{rev}/{nombre}"))
    return destino.read_bytes()


class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_abridor = urllib.request.build_opener(_SinRedireccion)
_firmadas: dict = {}


def firmada(clave: str, shard: str, renovar: bool = False) -> str:
    """Resuelve una vez la URL firmada del CDN para un shard.

    Args:
        clave: clave corta del repositorio en ``REPOS``.
        shard: nombre del fichero ``safetensors``.
        renovar: fuerza una resolución nueva (la firma caduca).

    Returns:
        La URL a la que redirige ``resolve``.
    """
    if renovar or (clave, shard) not in _firmadas:
        repo = REPOS[clave]
        url = f"{HF}/{repo}/resolve/{REV[repo]}/{shard}"
        for i in range(10):
            try:
                _abridor.open(urllib.request.Request(url, method="HEAD",
                                                     headers=UA), timeout=60)
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 307, 308):
                    _firmadas[(clave, shard)] = e.headers["Location"]
                    break
                time.sleep(int(e.headers.get("Retry-After") or 0) or 5 * (i + 1))
        else:
            raise RuntimeError(f"no se resuelve {url}")
    return _firmadas[(clave, shard)]


def rango(clave: str, shard: str, ini: int, largo: int) -> bytes:
    """Lee ``largo`` bytes de un shard a partir de ``ini``."""
    for i in range(8):
        try:
            return pedir(firmada(clave, shard, renovar=i > 0),
                         {"Range": f"bytes={ini}-{ini + largo - 1}"},
                         intentos=2)
        except (RuntimeError, urllib.error.HTTPError):
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"rango fallido {clave} {shard} {ini}")


def bf16(datos: bytes) -> np.ndarray:
    """Convierte bytes BF16 en ``float32`` sin pérdida."""
    u = np.frombuffer(datos, dtype="<u2").astype(np.uint32) << 16
    return u.view(np.float32)


def escribir(df: pd.DataFrame, nombre: str, muestra: bool = True) -> None:
    """Guarda un CSV junto al guion y muestra 15 filas al azar."""
    df.to_csv(AQUI / nombre, index=False)
    print(f"\n{nombre}: {len(df)} filas")
    if muestra and len(df):
        print(df.sample(min(15, len(df)), random_state=SEMILLA).to_string())


def resumen_actualizar(**claves) -> None:
    """Añade claves a ``resumen.json`` sin borrar las de otras etapas."""
    ruta = AQUI / "resumen.json"
    r = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    r.update(claves)
    r["fecha"] = date.today().isoformat()
    ruta.write_text(json.dumps(r, ensure_ascii=False, indent=1),
                    encoding="utf-8")


# --- 1. metadatos ------------------------------------------------------------

def etapa_metadatos() -> None:
    """Ficheros con su huella y commits de los tres repositorios."""
    filas, commits = [], []
    for repo in (DERIVADO, BASE, NVFP4):
        d = api(f"models/{repo}/revision/{REV[repo]}?blobs=true")
        (CRUDO / "api").mkdir(parents=True, exist_ok=True)
        (CRUDO / "api" / f"{repo.replace('/', '__')}.json").write_text(
            json.dumps(d))
        for s in d["siblings"]:
            lfs = s.get("lfs") or {}
            filas.append(dict(repo=repo, fichero=s["rfilename"],
                              tamano=s.get("size"),
                              huella=lfs.get("sha256") or s.get("blobId")))
        for c in api(f"models/{repo}/commits/main"):
            commits.append(dict(repo=repo, fecha=c["date"], commit=c["id"],
                                titulo=c["title"]))
    f = pd.DataFrame(filas)
    escribir(f, "ficheros.csv")
    escribir(pd.DataFrame(commits), "commits.csv")
    s = f[f.repo == DERIVADO].set_index("fichero")
    b = f[f.repo == BASE].set_index("fichero")
    comunes = s.index.intersection(b.index)
    iguales = [x for x in comunes if s.huella[x] == b.huella[x]]
    st = [x for x in comunes if x.endswith(".safetensors")]
    dif_tam = (s.tamano[st] - b.tamano[st])
    pesos = s.tamano[[x for x in s.index if x.endswith(".safetensors")]].sum()
    resumen_actualizar(ficheros=dict(
        comunes=len(comunes), identicos=len(iguales),
        safetensors=len(st),
        safetensors_identicos=sum(x in iguales for x in st),
        diferencia_tamano_bytes=sorted(set(int(v) for v in dif_tam)),
        bytes_pesos_derivado=int(pesos)))


# --- 2. código ---------------------------------------------------------------

CODIGO = ["modeling_nemotron_h_omni.py", "configuration_nemotron_h_omni.py",
          "configuration_radio.py", "modeling_radio.py",
          "image_processing_nemotron_h_omni.py",
          "processing_nemotron_h_omni.py", "ultra_v3_reasoning_parser.py",
          "__init__.py", "config.json", "preprocessor_config.json",
          "processor_config.json", "chat_template.jinja",
          "generation_config.json", "tokenizer_config.json"]


def etapa_codigo() -> None:
    """Compara el código remoto del derivado con dos revisiones de la base."""
    filas = []
    for nombre in CODIGO:
        s = fichero(DERIVADO, REV[DERIVADO], nombre)
        b = fichero(BASE, REV[BASE], nombre)
        p = fichero(BASE, BASE_PREVIA, nombre)
        filas.append(dict(
            fichero=nombre, python=nombre.endswith(".py"),
            sha256_derivado=hashlib.sha256(s).hexdigest(),
            igual_base_vigente=s == b, igual_base_previa=s == p,
            lineas_derivado=s.count(b"\n"), lineas_base=b.count(b"\n")))
    escribir(pd.DataFrame(filas), "codigo.csv")


# --- 3. fichas ---------------------------------------------------------------

def _celdas_tabla(md: str) -> dict:
    """Extrae «banco → (derivado, base)» de la tabla HTML de la ficha."""
    texto = re.sub(r"&tau;&sup2;", "τ²", md)
    salida = {}
    for fila in re.findall(r"<tr>(.*?)</tr>", texto, re.S):
        celdas = [re.sub(r"<[^>]+>", "", c).strip()
                  for c in re.findall(r"<td[^>]*>(.*?)</td>", fila, re.S)]
        if len(celdas) < 3:
            continue
        nums = [re.sub(r"[^\d.\-−]", "", c).replace("−", "-") for c in celdas[1:3]]
        try:
            salida[celdas[0]] = (float(nums[0]), float(nums[1]))
        except ValueError:
            continue
    return salida


def etapa_fichas() -> None:
    """Cifras de cada versión de la ficha del derivado y de la base."""
    com = pd.read_csv(AQUI / "commits.csv")
    filas = []
    for _, c in com[com.repo == DERIVADO].iterrows():
        try:
            md = fichero(DERIVADO, c.commit, "README.md").decode()
        except urllib.error.HTTPError:
            # el commit inicial no lleva ficha
            continue
        for banco, (s, b) in _celdas_tabla(md).items():
            filas.append(dict(fecha=c.fecha, commit=c.commit[:10],
                              titulo=c.titulo, banco=banco, derivado=s,
                              base=b, diferencia=round(s - b, 2)))
    v = pd.DataFrame(filas).sort_values(["fecha", "banco"])
    escribir(v, "ficha_versiones.csv")
    filas = []
    for _, c in com[com.repo == BASE].iterrows():
        try:
            md = fichero(BASE, c.commit, "README.md").decode()
        except urllib.error.HTTPError:
            continue
        m = re.search(r"\|\s*Terminal-Bench 2\.1\s*\|\s*([\d.]+)", md)
        filas.append(dict(fecha=c.fecha, commit=c.commit[:10],
                          titulo=c.titulo,
                          terminal_bench_base=float(m.group(1)) if m else None))
    escribir(pd.DataFrame(filas).sort_values("fecha"), "ficha_base_terminal.csv")
    versiones = v.commit.nunique()
    primera = v[v.fecha == v.fecha.min()].set_index("banco")
    ultima = v[v.fecha == v.fecha.max()].set_index("banco")
    retirados = sorted(set(v.banco) - set(ultima.index))
    resumen_actualizar(fichas=dict(
        versiones_con_tabla=int(versiones),
        commits_derivado=int((com.repo == DERIVADO).sum()),
        retirados=retirados,
        tb_primera=primera.loc["Terminal-Bench 2.1"].to_dict(),
        tb_ultima=ultima.loc["Terminal-Bench 2.1"].to_dict()))


# --- 4. cabeceras ------------------------------------------------------------

def _cabecera(clave: str, shard: str) -> dict:
    destino = CRUDO / "cabeceras" / f"{clave}_{shard}.json"
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        n = struct.unpack("<Q", rango(clave, shard, 0, 8))[0]
        h = json.loads(rango(clave, shard, 8, n))
        destino.write_text(json.dumps({"n": n, "h": h}))
    return json.loads(destino.read_text())


def tensores(claves: tuple = tuple(CORTOS),
             shards: list = SHARDS) -> dict:
    """Devuelve, por modelo, cada tensor con su shard y su posición.

    Args:
        claves: claves cortas de los modelos (``REPOS``).
        shards: ficheros ``safetensors`` del par.

    Returns:
        Un diccionario por clave con la posición de cada tensor.
    """
    salida = {}
    for clave in claves:
        t = {}
        for shard in shards:
            d = _cabecera(clave, shard)
            for nombre, v in d["h"].items():
                if nombre == "__metadata__":
                    continue
                t[nombre] = dict(shard=shard, dtype=v["dtype"],
                                 shape=v["shape"], ini=8 + d["n"]
                                 + v["data_offsets"][0],
                                 bytes=v["data_offsets"][1]
                                 - v["data_offsets"][0])
        salida[clave] = t
    return salida


def componente(nombre: str) -> str:
    """Asigna cada tensor a un bloque funcional del modelo."""
    if nombre.startswith("vision_model"):
        return "codificador de visión"
    if nombre.startswith(("mlp1", "vision_projector")):
        return "conector visión-lenguaje"
    if nombre.startswith("language_model.mtp"):
        return "cabeza MTP"
    if "embeddings" in nombre or "lm_head" in nombre:
        return "embeddings y salida"
    if ".experts." in nombre:
        return "expertos enrutados"
    if "shared_experts" in nombre:
        return "experto compartido"
    if ".gate." in nombre:
        return "router"
    if re.search(r"mixer\.(q|k|v|o)_proj", nombre):
        return "atención"
    if "mixer.in_proj" in nombre:
        return "Mamba-2, proyección de entrada"
    if re.search(r"mixer\.(out_proj|conv1d|A_log|D$|dt_bias|norm)", nombre):
        return "Mamba-2, resto"
    if "latent" in nombre:
        return "proyección latente"
    return "normalizaciones"


def etapa_cabeceras() -> None:
    """Cabeceras de los 128 shards y comparación de la disposición."""
    for clave in CORTOS:
        for shard in SHARDS:
            firmada(clave, shard)
    t = tensores()
    s, b = t["s"], t["b"]
    filas = [dict(tensor=n, componente=componente(n), shard=v["shard"],
                  dtype=v["dtype"], forma="x".join(map(str, v["shape"])),
                  bytes=v["bytes"],
                  misma_disposicion=(n in b and b[n]["shape"] == v["shape"]
                                     and b[n]["dtype"] == v["dtype"]
                                     and b[n]["shard"] == v["shard"]
                                     and b[n]["bytes"] == v["bytes"]))
             for n, v in s.items()]
    df = pd.DataFrame(filas)
    escribir(df, "tensores.csv")
    meta = {c: _cabecera(c, SHARDS[0])["h"].get("__metadata__")
            for c in CORTOS}
    resumen_actualizar(cabeceras=dict(
        tensores=len(s), tensores_base=len(b),
        misma_disposicion=int(df.misma_disposicion.sum()),
        metadatos_derivado=meta["s"], metadatos_base=meta["b"]))


# --- 5. censo ----------------------------------------------------------------

def _censo(d: str, b: str, shards: list, comp, hilos: int = 16) -> pd.DataFrame:
    """Compara ventanas de bytes de todos los tensores de un par de modelos.

    Args:
        d: clave del derivado en ``REPOS``.
        b: clave de la base en ``REPOS``.
        shards: ficheros ``safetensors`` del par (los mismos en los dos).
        comp: función que asigna cada tensor a su bloque funcional.
        hilos: lecturas en paralelo.

    Returns:
        Una fila por tensor con los bytes leídos y cuánto cambian.
    """
    t = tensores((d, b), shards)
    s, bb = t[d], t[b]
    rng = random.Random(SEMILLA)
    plan = []
    for n in sorted(s):
        tam = s[n]["bytes"]
        k = 1 if ".experts." in n else 3
        if tam <= k * VENTANA:
            vs = [(0, tam)]
        else:
            vs = [(o - o % 2, VENTANA) for o in
                  (rng.randrange(0, tam - VENTANA) for _ in range(k))]
        plan.append((n, vs))
    for clave in (d, b):
        for shard in shards:
            firmada(clave, shard)

    def uno(item):
        n, vs = item
        x = b"".join(rango(d, s[n]["shard"], s[n]["ini"] + o, l)
                     for o, l in vs)
        y = b"".join(rango(b, bb[n]["shard"], bb[n]["ini"] + o, l)
                     for o, l in vs)
        r = dict(tensor=n, componente=comp(n), papel=papel(n),
                 dtype=s[n]["dtype"], ventanas=len(vs), bytes_leidos=len(x),
                 identico=x == y)
        if s[n]["dtype"] == "BF16":
            u, v = bf16(x), bf16(y)
            dd = u.astype(np.float64) - v
            nb = float(np.linalg.norm(v.astype(np.float64)))
            r.update(valores=int(u.size),
                     cambiados=int(np.sum(u != v)),
                     cambio_rel_l2=float(np.linalg.norm(dd) / nb) if nb else 0.0)
        else:
            u = np.frombuffer(x, np.uint8)
            v = np.frombuffer(y, np.uint8)
            r.update(valores=int(u.size), cambiados=int(np.sum(u != v)),
                     cambio_rel_l2=float("nan"))
        return r

    with ThreadPoolExecutor(hilos) as ex:
        res = list(tqdm(ex.map(uno, plan), total=len(plan),
                        desc=f"censo {d}-{b}"))
    return pd.DataFrame(res)


def papel(nombre: str) -> str:
    """Dice si una matriz del modelo de lenguaje lee o escribe en el flujo
    residual; el resto (visión, MTP, normalizaciones…) queda como «otro»."""
    if nombre.startswith(("vision", "model.visual", "mlp1", "mtp",
                          "language_model.mtp")):
        return "otro"
    if re.search(r"(o_proj|out_proj|down_proj|fc2_latent_proj)\.weight$",
                 nombre):
        return "escribe"
    if re.search(r"(q_proj|k_proj|v_proj|in_proj\w*|up_proj|gate_proj"
                 r"|fc1_latent_proj|\.gate)\.weight$", nombre):
        return "lee"
    return "otro"


def etapa_censo() -> None:
    """Censo del par principal: Smaug-Nemotron frente a su base."""
    df = _censo("s", "b", SHARDS, componente)
    df = df.drop(columns="papel")
    escribir(df, "censo.csv")
    g = (df.groupby("componente")
         .agg(tensores=("tensor", "size"), identicos=("identico", "sum"),
              valores=("valores", "sum"), cambiados=("cambiados", "sum"),
              cambio_rel_l2_mediana=("cambio_rel_l2", "median"))
         .reset_index())
    g["frac_valores_cambiados"] = g.cambiados / g.valores
    escribir(g, "censo_componentes.csv", muestra=False)
    print(g.to_string())
    tipo = df.tensor.str.replace(r"\.\d+\.", ".N.", regex=True)
    t2 = (df.assign(tipo=tipo).groupby("tipo")
          .agg(tensores=("tensor", "size"), identicos=("identico", "sum"))
          .reset_index())
    escribir(t2, "censo_tipos.csv", muestra=False)
    cambian = t2[t2.identicos < t2.tensores]
    resumen_actualizar(censo=dict(
        tensores=len(df), identicos=int(df.identico.sum()),
        bytes_leidos=int(df.bytes_leidos.sum()) * 2,
        tipos_que_cambian=cambian.tipo.tolist(),
        tensores_que_cambian=int((~df.identico).sum())))


# --- 6. rango ----------------------------------------------------------------

RANGO_TENSORES = [
    "language_model.backbone.layers.7.mixer.q_proj.weight",
    "language_model.backbone.layers.1.mixer.shared_experts.down_proj.weight",
]


def _rango(d: str, b: str, shards: list, nombres: list) -> tuple:
    """Valores singulares de la diferencia de tensores completos.

    Args:
        d: clave del derivado en ``REPOS``.
        b: clave de la base en ``REPOS``.
        shards: ficheros ``safetensors`` del par.
        nombres: tensores que se leen enteros.

    Returns:
        Las filas por valor singular y el resumen por tensor.
    """
    t = tensores((d, b), shards)
    filas, resumen = [], {}
    rng = np.random.default_rng(SEMILLA)
    for n in nombres:
        mats = {}
        for clave in (d, b):
            v = t[clave][n]
            datos = b"".join(
                rango(clave, v["shard"], v["ini"] + o,
                      min(64 << 20, v["bytes"] - o))
                for o in range(0, v["bytes"], 64 << 20))
            mats[clave] = bf16(datos).reshape(v["shape"]).astype(np.float64)
        dif = mats[d] - mats[b]
        cambiado = dif != 0
        barajada = np.zeros_like(dif)
        barajada[cambiado] = rng.permutation(dif[cambiado])
        sv = np.linalg.svd(dif, compute_uv=False)
        sb = np.linalg.svd(barajada, compute_uv=False)
        e = np.cumsum(sv ** 2) / np.sum(sv ** 2)
        eb = np.cumsum(sb ** 2) / np.sum(sb ** 2)
        for i in range(len(sv)):
            filas.append(dict(tensor=n, k=i + 1, sv=sv[i], sv_barajada=sb[i],
                              energia=e[i], energia_barajada=eb[i]))
        resumen[n] = dict(
            forma=list(dif.shape), frac_cambiados=float(cambiado.mean()),
            cambio_rel_l2=float(np.linalg.norm(dif)
                                / np.linalg.norm(mats[b])),
            **{f"energia_{r}": float(e[r - 1]) for r in (1, 2, 4, 8, 16, 32, 64)},
            rango_999=int(np.searchsorted(e, 0.999) + 1),
            **{f"energia_barajada_{r}": float(eb[r - 1])
               for r in (1, 8, 16, 32, 64)})
    return filas, resumen


def etapa_rango() -> None:
    """Rango de la diferencia en dos tensores del par principal."""
    filas, resumen = _rango("s", "b", SHARDS, RANGO_TENSORES)
    escribir(pd.DataFrame(filas), "rango.csv")
    resumen_actualizar(rango=resumen)


# --- 10. contraste -----------------------------------------------------------

def componente_qwen(nombre: str) -> str:
    """Bloque funcional de un tensor de Qwen3.8-27B."""
    if nombre.startswith("model.visual.merger"):
        return "conector visión-lenguaje"
    if nombre.startswith("model.visual"):
        return "codificador de visión"
    if nombre.startswith("mtp"):
        return "cabeza MTP"
    if "embed_tokens" in nombre or "lm_head" in nombre:
        return "embeddings y salida"
    if re.search(r"self_attn\.(q|k|v|o)_proj", nombre):
        return "atención"
    if "linear_attn.in_proj" in nombre:
        return "atención lineal, proyección de entrada"
    if "linear_attn.out_proj" in nombre:
        return "atención lineal, proyección de salida"
    if "linear_attn" in nombre:
        return "atención lineal, resto"
    if re.search(r"mlp\.(gate|up)_proj", nombre):
        return "MLP, entrada"
    if "mlp.down_proj" in nombre:
        return "MLP, salida"
    return "normalizaciones"


# pareja: (derivado, base, shards, bloques, técnica que declara su ficha)
PAREJAS = {
    "Smaug-Nemotron": ("s", "b", SHARDS, componente,
                       "ajuste fino agéntico (SFT)"),
    "Heretic": ("h", "b", SHARDS, componente,
                "ablación de la dirección de rechazo (Heretic)"),
    "Smaug-Uncensored": ("u", "q", SHARDS_QWEN, componente_qwen,
                         "LoRA de rango 16 fusionado"),
}


def etapa_contraste() -> None:
    """Censo y rango de dos derivados más, con el mismo procedimiento.

    Heretic sale de la misma base que Smaug-Nemotron y declara haber
    quitado los rechazos; Smaug-Uncensored sale de Qwen3.8-27B con un LoRA
    de rango 16. El censo de Smaug-Nemotron se toma de ``censo.csv``.
    """
    previo = AQUI / "contraste_censo.csv"
    if REUSAR and previo.exists():
        nuevos = pd.read_csv(previo)
    else:
        nuevos = pd.concat(
            [_censo(d, b, shards, comp).assign(pareja=pareja, tecnica=tecnica)
             for pareja, (d, b, shards, comp, tecnica) in PAREJAS.items()
             if pareja != "Smaug-Nemotron"], ignore_index=True)
    principal = pd.read_csv(AQUI / "censo.csv").assign(
        pareja="Smaug-Nemotron", tecnica=PAREJAS["Smaug-Nemotron"][4])
    censo = pd.concat([principal, nuevos], ignore_index=True)
    # el papel se deduce siempre del nombre, para que un cambio de criterio
    # no exija repetir la lectura
    censo["papel"] = censo.tensor.map(papel)
    escribir(censo[censo.pareja != "Smaug-Nemotron"], "contraste_censo.csv")
    g = (censo.groupby(["pareja", "componente"])
         .agg(tensores=("tensor", "size"), identicos=("identico", "sum"),
              valores=("valores", "sum"), cambiados=("cambiados", "sum"),
              cambio_rel_l2_mediana=("cambio_rel_l2", "median"))
         .reset_index())
    escribir(g, "contraste_componentes.csv", muestra=False)
    print(g.to_string())
    pa = (censo.groupby(["pareja", "papel"])
          .agg(tensores=("tensor", "size"), identicos=("identico", "sum"))
          .reset_index())
    pa["cambian"] = pa.tensores - pa.identicos
    escribir(pa, "contraste_papel.csv", muestra=False)
    print(pa.to_string())
    # rango: el tensor que más cambia de cada papel, en cada pareja nueva
    filas, resumen = [], {}
    for pareja, (d, b, shards, comp, tecnica) in PAREJAS.items():
        c = censo[(censo.pareja == pareja) & ~censo.identico
                  & censo.papel.isin(["lee", "escribe"])]
        if pareja == "Smaug-Nemotron":
            nombres = RANGO_TENSORES
        else:
            nombres = (c.sort_values("cambio_rel_l2", ascending=False)
                       .groupby("papel").head(1).tensor.tolist())
        f, r = _rango(d, b, shards, nombres)
        filas += [{**x, "pareja": pareja} for x in f]
        resumen[pareja] = dict(
            tecnica=tecnica,
            tensores=int((censo.pareja == pareja).sum()),
            cambian=int(((censo.pareja == pareja) & ~censo.identico).sum()),
            rango={n: {**v, "papel": papel(n)} for n, v in r.items()})
    escribir(pd.DataFrame(filas), "contraste_rango.csv")
    resumen_actualizar(contraste=resumen)


# --- 7. ruido ----------------------------------------------------------------

# tareas y ejecuciones según las notas de la ficha del derivado (revisión
# fijada); las cifras de la base, de la ficha de NVIDIA, salvo NL2RepoBench
BANCOS = [
    # banco, tareas, ejecuciones del derivado, procedencia de la base
    ("SWE-bench Verified", 500, 3, "ficha de NVIDIA"),
    ("SWE-bench Multilingual", 300, 6, "ficha de NVIDIA"),
    ("Terminal-Bench 2.1", 89, 4, "ficha de NVIDIA"),
    ("DeepSWE [offline]", 113, 1, "ficha de NVIDIA"),
    ("LiveCodeBench v6", 454, 4, "ficha de NVIDIA"),
    ("SciCode (subtask)", 288, 3, "ficha de NVIDIA"),
    ("GPQA Diamond", 198, 8, "ficha de NVIDIA"),
    ("IFBench", 300, 8, "ficha de NVIDIA"),
    ("AA-LCR v1.1", 100, 5, "ficha de NVIDIA"),
    ("V*", 191, 4, "ficha de NVIDIA"),
]


def etapa_ruido() -> None:
    """Error típico de cada diferencia debido al muestreo de tareas.

    Se trata cada banco como una muestra de tareas de una población mayor
    (Miller, 2024). Sin resultados por tarea, el error típico de la
    diferencia se acota: sin emparejar (correlación cero entre modelos) y
    con una correlación de 0,8 entre los aciertos de los dos modelos en la
    misma tarea, plausible para un ajuste fino de su propia base.
    """
    v = pd.read_csv(AQUI / "ficha_versiones.csv")
    ultima = v[v.fecha == v.fecha.max()].set_index("banco")
    filas = []
    for banco, n, ejec, proc in BANCOS:
        s, b = ultima.loc[banco, "derivado"] / 100, ultima.loc[banco, "base"] / 100
        var_s, var_b = s * (1 - s) / n, b * (1 - b) / n
        for rho in (0.0, 0.8):
            ee = np.sqrt(var_s + var_b - 2 * rho * np.sqrt(var_s * var_b))
            filas.append(dict(banco=banco, tareas=n, ejecuciones=ejec,
                              base_de=proc, derivado=100 * s, base=100 * b,
                              diferencia=100 * (s - b), correlacion=rho,
                              error_tipico=100 * ee,
                              z=(s - b) / ee if ee else float("nan")))
    df = pd.DataFrame(filas)
    escribir(df, "ruido.csv")
    alta = df[df.correlacion == 0.8]
    resumen_actualizar(ruido=dict(
        bancos=len(BANCOS),
        z_mayor_2_rho08=alta[alta.z > 2].banco.tolist(),
        z_mayor_2_rho0=df[(df.correlacion == 0) & (df.z > 2)].banco.tolist()))


# --- 8. derivados ------------------------------------------------------------

def _todos(params: dict) -> list:
    """Recorre todas las páginas de un listado de modelos."""
    url = f"{HF}/api/models?" + urllib.parse.urlencode(params)
    salida = []
    while url:
        datos, r = pedir(url, bruto=True)
        salida += json.loads(datos)
        m = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link") or "")
        url = m.group(1) if m else None
    return salida


def _sin_rechazos(texto: str) -> bool:
    return bool(re.search(r"abliterat|uncensor|heretic|decensor", texto, re.I))


def etapa_derivados() -> None:
    """Árbol de derivados de la base y modelos anunciados sin rechazos."""
    filas = []
    for rel in ("finetune", "adapter", "quantized", "merge"):
        for m in _todos({"filter": f"base_model:{rel}:{BASE}", "limit": 1000}):
            filas.append(dict(relacion=rel, modelo=m["id"],
                              creado=m.get("createdAt"),
                              descargas=m.get("downloads"),
                              sin_rechazos=_sin_rechazos(
                                  m["id"] + " " + " ".join(m.get("tags", [])))))
    arbol = pd.DataFrame(filas).sort_values(["relacion", "creado"])
    escribir(arbol, "derivados_base.csv")
    vistos = {}
    for termino in TERMINOS_SIN_RECHAZOS:
        for m in _todos({"search": termino, "limit": 1000}):
            vistos.setdefault(m["id"], dict(
                modelo=m["id"], creado=m.get("createdAt"),
                descargas=m.get("downloads"), terminos=set()))
            vistos[m["id"]]["terminos"].add(termino)
    hub = pd.DataFrame([{**v, "terminos": "+".join(sorted(v["terminos"]))}
                        for v in vistos.values()])
    hub["mes"] = hub.creado.str[:7]
    escribir(hub[["modelo", "creado", "descargas", "terminos"]],
             "hub_sin_rechazos.csv.gz")
    mes = hub.groupby("mes").agg(modelos=("modelo", "size"),
                                 descargas=("descargas", "sum")).reset_index()
    escribir(mes, "hub_sin_rechazos_mes.csv", muestra=False)
    h = arbol[arbol.sin_rechazos]
    resumen_actualizar(derivados=dict(
        total=len(arbol),
        por_relacion=arbol.relacion.value_counts().to_dict(),
        sin_rechazos=h.modelo.tolist(),
        sin_rechazos_creado=h.creado.tolist(),
        base_creada=api(f"models/{BASE}")["createdAt"]),
        hub=dict(modelos=len(hub), descargas=int(hub.descargas.sum()),
                 por_termino={t: int(hub.terminos.str.contains(t).sum())
                              for t in TERMINOS_SIN_RECHAZOS}))


# --- 9. rechazos -------------------------------------------------------------

def etapa_rechazos() -> None:
    """Tasas de rechazo declaradas por dos derivados sin rechazos.

    Son cifras ajenas: se transcriben de las fichas a revisión fijada y se
    comprueba que el texto que las contiene sigue en esa revisión.
    """
    filas = []
    md = fichero(*HERETIC, "README.md").decode()
    m = re.search(r"\*\*Refusals\*\*\s*\|\s*(\d+)/(\d+)\s*\|\s*(\d+)/(\d+)", md)
    k = re.search(r"\*\*KL divergence\*\*\s*\|\s*([\d.]+)", md)
    filas.append(dict(modelo=HERETIC[0], revision=HERETIC[1][:10],
                      prueba="regla de palabras clave de Heretic, 100 "
                             "peticiones de mlabonne/harmful_behaviors",
                      rechazos_derivado=int(m.group(1)),
                      total_derivado=int(m.group(2)),
                      rechazos_base=int(m.group(3)), total_base=int(m.group(4)),
                      nota=f"divergencia KL de primer token {k.group(1)}"))
    md = fichero(*UNCENSORED, "README.md").decode()
    plano = re.sub(r"<[^>]+>", "|", md)
    for rotulo, prueba in (("XSTest unsafe split", "XSTest, parte insegura"),
                           ("XSTest safe split", "XSTest, parte segura"),
                           ("OR-Bench-Hard-1K", "OR-Bench-Hard-1K")):
        tramo = plano[plano.index(rotulo):]
        p = re.findall(r"(\d+)/(\d+)", tramo)[:2]
        filas.append(dict(modelo=UNCENSORED[0], revision=UNCENSORED[1][:10],
                          prueba=prueba,
                          rechazos_derivado=int(p[0][0]),
                          total_derivado=int(p[0][1]),
                          rechazos_base=int(p[1][0]), total_base=int(p[1][1]),
                          nota="base Qwen/Qwen3.8-27B; LoRA de rango 16 "
                               "fusionado, según la ficha"))
    escribir(pd.DataFrame(filas), "rechazos_declarados.csv")


# --- 11. inventario ---------------------------------------------------------

EXCLUIR_INVENTARIO = re.compile(
    r"gguf|exl\d|awq|gptq|mlx|mxfp4|nvfp4|fp8|int4|int8|-bnb|image|lora", re.I)


def _info(repo: str) -> dict | None:
    """Información de un modelo del Hub, o ``None`` si no es legible."""
    try:
        return api(f"models/{repo}?blobs=false")
    except (urllib.error.HTTPError, RuntimeError):
        return None


def _claves_indice(repo: str, rev: str) -> set | None:
    """Nombres de tensor del índice de ``safetensors`` o, si el modelo va en
    un solo fichero, de la cabecera de ``model.safetensors``."""
    try:
        return set(json.loads(fichero(repo, rev,
                                      "model.safetensors.index.json"))
                   ["weight_map"])
    except (urllib.error.HTTPError, RuntimeError, KeyError):
        pass
    try:
        url = f"{HF}/{repo}/resolve/{rev}/model.safetensors"
        n = struct.unpack("<Q", pedir(url, {"Range": "bytes=0-7"}))[0]
        h = json.loads(pedir(url, {"Range": f"bytes=8-{7 + n}"}))
        return set(h) - {"__metadata__"}
    except (urllib.error.HTTPError, RuntimeError, struct.error, ValueError):
        return None


def _estructura(repo: str, rev: str, info: dict) -> dict | None:
    """Tipo y forma de cada tensor, leídos de las cabeceras de todos los
    ``safetensors`` del repositorio (una o dos lecturas por fichero).

    Returns:
        Un diccionario nombre → (tipo, forma), o ``None`` si no es legible.
    """
    destino = CRUDO / "estructura" / f"{repo.replace('/', '__')}_{rev}.json"
    if destino.exists():
        return {k: tuple(v) for k, v in json.loads(destino.read_text()).items()}
    salida = {}
    shards = [x["rfilename"] for x in info.get("siblings", [])
              if x["rfilename"].endswith(".safetensors")]
    try:
        for sh in shards:
            url = f"{HF}/{repo}/resolve/{rev}/{sh}"
            ini = pedir(url, {"Range": "bytes=0-262143"})
            n = struct.unpack("<Q", ini[:8])[0]
            cab = ini[8:8 + n]
            if len(cab) < n:
                cab += pedir(url, {"Range": f"bytes={8 + len(cab)}-{7 + n}"})
            for k, v in json.loads(cab).items():
                if k != "__metadata__":
                    salida[k] = (v["dtype"], "x".join(map(str, v["shape"])))
    except (urllib.error.HTTPError, RuntimeError, struct.error, ValueError):
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(salida))
    return salida


def _licencia(info: dict) -> str:
    c = info.get("cardData") or {}
    lic = c.get("license") or "sin declarar"
    return c.get("license_name") or lic if lic == "other" else lic


def etapa_inventario(n: int = 15) -> None:
    """Inventario de pares base-derivado sin rechazos, declarado y comprobado.

    Toma los derivados más descargados de ``hub_sin_rechazos.csv.gz`` que
    publican pesos completos y declaran su base, más los dos de la
    investigación. De cada par se comprueba, sin ejecutar nada, la licencia,
    la disposición de los tensores y si la ficha publica cifras de rechazo.
    """
    hub = pd.read_csv(AQUI / "hub_sin_rechazos.csv.gz")
    hub = hub[~hub.modelo.str.contains(EXCLUIR_INVENTARIO)]
    candidatos = [HERETIC[0], UNCENSORED[0]] + hub.sort_values(
        "descargas", ascending=False).modelo.tolist()
    filas, vistos = [], set()
    for repo in tqdm(candidatos, desc="inventario"):
        if len(filas) >= n + 2:
            break
        info = _info(repo)
        if info:
            info = api(f"models/{repo}/revision/{info['sha']}?blobs=false")
        if not info or not info.get("safetensors"):
            continue
        base = (info.get("cardData") or {}).get("base_model")
        base = base[0] if isinstance(base, list) and len(base) == 1 else base
        if not isinstance(base, str) or base in vistos:
            continue
        ib = _info(base)
        if not ib:
            continue
        ib = api(f"models/{base}/revision/{ib['sha']}?blobs=false")
        vistos.add(base)
        rev, revb = info["sha"], ib["sha"]
        try:
            md = fichero(repo, rev, "README.md").decode(errors="replace")
        except urllib.error.HTTPError:
            md = ""
        texto = repo + " " + md
        tecnica = ("Heretic" if re.search(r"heretic", texto, re.I) else
                   "ablación" if re.search(r"abliterat", texto, re.I) else
                   "LoRA" if re.search(r"\blora\b", md, re.I) else
                   "ajuste fino" if re.search(r"fine-?tun|SFT|DPO", md, re.I)
                   else "sin declarar")
        cifra = re.search(r"refus\w*[^\n]{0,160}?(\d+\s*/\s*\d+|\d+(\.\d+)?"
                          r"\s*%)", md, re.I | re.S)
        cd, cb = _claves_indice(repo, rev), _claves_indice(base, revb)
        ed, eb = _estructura(repo, rev, info), _estructura(base, revb, ib)
        comunes = set(ed or {}) & set(eb or {})
        pd_, pb = (info["safetensors"].get("total"),
                   ib.get("safetensors", {}).get("total"))
        filas.append(dict(
            derivado=repo, revision=rev, base=base, revision_base=revb,
            creado=info.get("createdAt"), descargas=info.get("downloads"),
            licencia=_licencia(info), licencia_base=_licencia(ib),
            misma_licencia=_licencia(info) == _licencia(ib),
            tecnica_declarada=tecnica, declara_cifra_rechazos=bool(cifra),
            fragmento_cifra=(re.sub(r"\s+", " ", cifra.group(0))[:200]
                             if cifra else ""),
            parametros=pd_, parametros_base=pb,
            mismos_tensores=(None if cd is None or cb is None else cd == cb),
            misma_forma_y_tipo=(None if not ed or not eb or set(ed) != set(eb)
                                else all(ed[k] == eb[k] for k in comunes)),
            tensores_distinta_forma_o_tipo=(None if not ed or not eb else sum(
                ed[k] != eb[k] for k in comunes)),
            tipos_derivado="+".join(sorted({v[0] for v in (ed or {}).values()})),
            solo_derivado=(None if cd is None or cb is None
                           else len(cd - cb)),
            solo_base=None if cd is None or cb is None else len(cb - cd),
            bloques_solo_base=("" if cd is None or cb is None else " ".join(
                sorted({re.split(r"\.\d+\.|\.weight|\.bias", x)[0]
                        for x in cb - cd})[:3])),
            conducta="no medida"))
    df = pd.DataFrame(filas)
    escribir(df, "inventario.csv")
    resumen_actualizar(inventario=dict(
        pares=len(df), misma_licencia=int(df.misma_licencia.sum()),
        declaran_cifra=int(df.declara_cifra_rechazos.sum()),
        mismos_tensores=int((df.mismos_tensores == True).sum()),  # noqa: E712
        misma_forma_y_tipo=int((df.misma_forma_y_tipo == True).sum()),  # noqa: E712
        fecha_consulta=date.today().isoformat(),
        tecnicas=df.tecnica_declarada.value_counts().to_dict(),
        licencias=df.licencia.value_counts().to_dict()))


# con --reusar, la etapa contraste toma el censo ya escrito en vez de leerlo
REUSAR = False

ETAPAS = {"metadatos": etapa_metadatos, "codigo": etapa_codigo,
          "fichas": etapa_fichas, "cabeceras": etapa_cabeceras,
          "censo": etapa_censo, "rango": etapa_rango, "ruido": etapa_ruido,
          "derivados": etapa_derivados, "rechazos": etapa_rechazos,
          "contraste": etapa_contraste, "inventario": etapa_inventario}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--etapa", choices=ETAPAS, action="append")
    ap.add_argument("--reusar", action="store_true",
                    help="contraste: reutiliza contraste_censo.csv")
    args = ap.parse_args()
    REUSAR = args.reusar
    CRUDO.mkdir(exist_ok=True)
    for nombre in args.etapa or ETAPAS:
        t0 = time.time()
        print(f"\n=== {nombre}")
        ETAPAS[nombre]()
        print(f"--- {nombre}: {time.time() - t0:.0f} s")
