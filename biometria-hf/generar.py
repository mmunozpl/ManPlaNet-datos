"""Caras sintéticas y sus detectores en Hugging Face, leídos por su API.

Inventario de los modelos y las aplicaciones (Spaces) cuyo nombre remite a
intercambiar caras o fabricar deepfakes, frente a los que remiten a
detectarlos o a comprobar que hay una persona viva delante de la cámara. Solo
se leen metadatos públicos y fichas: no se descarga ningún modelo, no se
ejecuta ninguna aplicación y no interviene la imagen de ninguna persona.

Etapas, todas reejecutables (lo descargado va a ``crudo/``):

1. ``inventario``: búsquedas por término en modelos y Spaces, con fecha de
   creación, descargas, «me gusta», etiquetas, licencia y estado de cada
   Space; clasificación por familia, subtipo y modalidad.
2. ``fichas``: la ficha (README) de cada modelo detector y si declara
   métricas, conjunto de prueba, ataques de presentación o de inyección.
3. ``medir``: recuentos, serie trimestral, concentración y resumen, con 15
   filas al azar para revisar a mano.
"""

import argparse
import csv
import json
import random
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CRUDO = AQUI / "crudo"
UA = "ManPlaNet-datos/1.0"
SEMILLA = 2026
API = "https://huggingface.co/api"
# la búsqueda de la api casa con el identificador del repositorio
TERMINOS = ["faceswap", "face-swap", "face swap", "swapface", "swap-face",
            "inswapper", "roop", "facefusion", "deepfacelab", "deep-live-cam",
            "head-swap", "deepfake", "deep-fake", "deepfake-detection",
            "fake-face", "face-forgery", "forgery-detection",
            "anti-spoofing", "antispoofing", "anti-spoof", "face-spoof",
            "liveness", "face-morph", "morphing-attack", "morph-detection"]
EXPANDIR = {
    "models": ["createdAt", "downloads", "downloadsAllTime", "likes",
               "pipeline_tag", "tags", "gated", "lastModified"],
    "spaces": ["createdAt", "likes", "sdk", "tags", "cardData", "runtime",
               "lastModified"]}

DETECCION = re.compile(
    r"detect|detection|detector|classif|anti.?spoof|liveness|forensic|"
    r"forgery|real.?(vs|or|and).?fake|fake.?or.?real|spoof|authentic|"
    r"morph.?(attack|detect)|\bmad\b|is.?it.?(real|fake)|deepfake.?check|"
    r"fake.?(face|image|video).?(class|det|ident)|identify.?(ai|fake)")
GENERACION = re.compile(
    r"face.?swap|swap.?face|faceswap|swapper|inswapper|\broop|facefusion|"
    r"deepfacelab|deep.?live.?cam|head.?swap|face.?fusion|deep.?fake")
VIDA = re.compile(r"anti.?spoof|liveness|spoof|presentation.?attack")
MORPH = re.compile(r"morph")
VOZ = re.compile(r"audio|voice|speech|asvspoof|wav2vec|\bvoz\b|speaker|"
                 r"\btts\b|\bsvc\b|\brvc\b")


def _get(url: str) -> tuple[object, str]:
    for intento in range(5):
        try:
            pet = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(pet, timeout=120) as r:
                return json.load(r), r.headers.get("Link") or ""
        except Exception:  # se reintenta con espera creciente
            time.sleep(5 * (intento + 1))
    raise RuntimeError(f"sin respuesta: {url}")


def _buscar(tipo: str, termino: str) -> list[dict]:
    q = [("search", termino), ("limit", "1000")]
    q += [("expand[]", e) for e in EXPANDIR[tipo]]
    url = f"{API}/{tipo}?{urllib.parse.urlencode(q)}"
    salida = []
    while url:
        datos, enlace = _get(url)
        salida += datos
        url = (enlace.split(";")[0].strip("<>")
               if 'rel="next"' in enlace else None)
    return salida


def clasificar(item: dict, tipo: str) -> tuple[str, str, str]:
    """Familia, subtipo y modalidad de un repositorio por su texto.

    Se mira el nombre del repositorio sin el usuario (la búsqueda de la API
    casa también con el nombre de usuario), el título y la descripción corta
    de los Spaces y las etiquetas. Detección manda sobre generación: un
    detector nombra casi siempre la palabra «deepfake». Un repositorio que
    solo dice «deepfake» es ambiguo (en los modelos revisados resultó ser un clasificador
    sin la palabra «detect») y no cuenta en ninguna de las dos familias.
    """
    card = item.get("cardData") or {}
    nombre = item["id"].split("/", 1)[-1].lower()
    texto = " ".join([nombre, str(card.get("title", "")),
                      str(card.get("short_description", "")),
                      " ".join(item.get("tags") or [])]).lower()
    tarea = item.get("pipeline_tag") or ""
    modalidad = ("voz" if VOZ.search(texto) or tarea.startswith("audio")
                 else "imagen y vídeo")
    if (DETECCION.search(texto)
            or re.search(r"real.?fake|fake.?face(?!.?swap)", texto)
            or tarea in ("image-classification", "video-classification",
                         "audio-classification")):
        if modalidad == "voz":
            sub = "deepfake"
        elif VIDA.search(texto):
            sub = "presentación y vida"
        elif MORPH.search(texto):
            sub = "morphing"
        else:
            sub = "deepfake"
        return "detección", sub, modalidad
    if re.search(r"swap|\broop|^roop|facefusion|face.?fusion|deepfacelab|"
                 r"live.?cam|deepface.?live|reactor", texto):
        return "generación", "intercambio de caras", modalidad
    if re.search(r"face.?morph|morph.?face|facemorph", texto):
        return "generación", "morphing de caras", modalidad
    if re.search(r"deep.?fake", texto):
        return "ambiguo", "deepfake, sin precisar", modalidad
    return "otro", "", modalidad


SIN_FILTROS = re.compile(r"nsfw|uncensored|unfiltered|no.?filter|"
                         r"without.?filter|sin.?censura|sin.?filtro")


def _texto(it: dict) -> str:
    card = it.get("cardData") or {}
    return " ".join([it["id"].split("/", 1)[-1],
                     str(card.get("title", "")),
                     str(card.get("short_description", ""))]).lower()


def etapa_inventario(sin_red: bool = False) -> None:
    """Busca, une, clasifica y escribe ``repos.csv``.

    Con ``sin_red`` reclasifica las búsquedas ya guardadas en ``crudo/``.
    """
    from tqdm import tqdm
    (CRUDO / "busquedas").mkdir(parents=True, exist_ok=True)
    vistos = {}
    for tipo in ("models", "spaces"):
        for termino in tqdm(TERMINOS, desc=tipo):
            guardado = (CRUDO / "busquedas"
                        / f"{tipo}_{termino.replace(' ', '_')}.json")
            if sin_red:
                res = json.loads(guardado.read_text(encoding="utf-8"))
            else:
                res = _buscar(tipo, termino)
                guardado.write_text(json.dumps(res), encoding="utf-8")
            for it in res:
                vistos.setdefault((tipo, it["id"]), dict(it, terminos=[]))
                vistos[(tipo, it["id"])]["terminos"].append(termino)
            if not sin_red:
                time.sleep(1)
    filas = []
    for (tipo, ident), it in sorted(vistos.items()):
        familia, sub, modalidad = clasificar(it, tipo)
        tags = it.get("tags") or []
        licencia = next((t.split(":", 1)[1] for t in tags
                         if t.startswith("license:")), "")
        rt = it.get("runtime") or {}
        hw = (rt.get("hardware") or {})
        filas.append(dict(
            tipo="modelo" if tipo == "models" else "space", id=ident,
            familia=familia, subtipo=sub, modalidad=modalidad,
            creado=(it.get("createdAt") or "")[:10],
            modificado=(it.get("lastModified") or "")[:10],
            descargas_total=it.get("downloadsAllTime", ""),
            descargas_30d=it.get("downloads", ""),
            me_gusta=it.get("likes", 0), tarea=it.get("pipeline_tag") or "",
            licencia=licencia, restringido=it.get("gated", ""),
            estado=rt.get("stage", ""), hardware=hw.get("current") or "",
            hardware_pedido=hw.get("requested") or "",
            sin_filtros=bool(SIN_FILTROS.search(
                re.sub(r"\bno.?nsfw", "", _texto(it)))),
            invita_duplicar=bool(re.search(r"duplicate",
                                           _texto(it))),
            terminos="|".join(sorted(set(it["terminos"])))))
    _escribir(AQUI / "repos.csv", filas)
    c = Counter((f["tipo"], f["familia"]) for f in filas)
    print(dict(c))


def _escribir(ruta: Path, filas: list[dict]) -> None:
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def _leer(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


METRICAS = re.compile(
    r"\b(accuracy|auc|roc|eer|f1|precision|recall|apcer|bpcer|acer|hter|"
    r"false.?(negative|positive|accept|reject)|fnr|fpr|frr|far|tpr|"
    r"exactitud|precisi[oó]n)\b")
PRUEBA = re.compile(
    r"faceforensics|celeb.?df|\bdfdc\b|wild.?deepfake|deeperforensics|"
    r"asvspoof|casia|oulu|replay.?attack|msu.?mfsd|\bsiw\b|celeba.?spoof|"
    r"in.?the.?wild|test.?(set|split|data)|evaluation.?(set|data)|"
    r"held.?out|validation.?set")
INYECCION = re.compile(r"injection|virtual.?camera|camera.?emulat|"
                       r"emulator|inyecci|c[aá]mara.?virtual")
PRESENTACION = re.compile(r"presentation.?attack|print.?attack|"
                          r"replay.?attack|\bmask\b|spoof|liveness")


def etapa_fichas() -> None:
    """Lee la ficha de cada modelo detector y anota qué declara."""
    from tqdm import tqdm
    destino = CRUDO / "fichas"
    destino.mkdir(parents=True, exist_ok=True)
    repos = [r for r in _leer(AQUI / "repos.csv")
             if r["tipo"] == "modelo" and r["familia"] == "detección"]
    filas = []
    for r in tqdm(repos, desc="fichas"):
        f = destino / (r["id"].replace("/", "__") + ".md")
        if not f.exists():
            url = f"https://huggingface.co/{r['id']}/raw/main/README.md"
            try:
                pet = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(pet, timeout=60) as resp:
                    f.write_bytes(resp.read())
            except Exception:
                f.write_text("", encoding="utf-8")
            time.sleep(0.3)
        txt = f.read_text(encoding="utf-8", errors="replace")
        cuerpo = re.sub(r"\A---\n.*?\n---\n", "", txt, flags=re.S)
        bajo = txt.lower()
        palabras = len(re.findall(r"\w+", cuerpo))
        # la plantilla automática de hugging face se reconoce por su relleno
        plantilla = "more information needed" in bajo
        filas.append(dict(
            id=r["id"], subtipo=r["subtipo"], modalidad=r["modalidad"],
            descargas_total=r["descargas_total"], ficha=bool(txt.strip()),
            palabras=palabras, plantilla_vacia=plantilla,
            model_index="model-index:" in bajo,
            metricas=bool(METRICAS.search(bajo)),
            conjunto_prueba=bool(PRUEBA.search(bajo)),
            presentacion=bool(PRESENTACION.search(bajo)),
            inyeccion=bool(INYECCION.search(bajo))))
    _escribir(AQUI / "fichas_detectores.csv", filas)


def _trimestre(fecha: str) -> str:
    a, m = int(fecha[:4]), int(fecha[5:7])
    return f"{a}-T{(m - 1) // 3 + 1}"


def etapa_medir() -> None:
    """Recuentos, serie, concentración, fichas y resumen."""
    todos = _leer(AQUI / "repos.csv")
    repos = [r for r in todos if r["familia"] in ("generación", "detección")]
    for r in repos:
        r["descargas_total"] = int(r["descargas_total"] or 0)
        r["me_gusta"] = int(r["me_gusta"] or 0)
    recuentos = []
    for (tipo, fam, sub, mod), n in sorted(Counter(
            (r["tipo"], r["familia"], r["subtipo"], r["modalidad"])
            for r in repos).items()):
        g = [r for r in repos if (r["tipo"], r["familia"], r["subtipo"],
                                  r["modalidad"]) == (tipo, fam, sub, mod)]
        recuentos.append(dict(
            tipo=tipo, familia=fam, subtipo=sub, modalidad=mod, repos=n,
            descargas_total=sum(r["descargas_total"] for r in g),
            me_gusta=sum(r["me_gusta"] for r in g),
            spaces_en_marcha=sum(r["estado"] == "RUNNING" for r in g),
            sin_filtros=sum(r["sin_filtros"] == "True" for r in g),
            invita_duplicar=sum(r["invita_duplicar"] == "True" for r in g)))
    _escribir(AQUI / "recuentos.csv", recuentos)
    serie = Counter((r["tipo"], r["familia"], _trimestre(r["creado"]))
                    for r in repos if r["creado"])
    _escribir(AQUI / "serie_trimestral.csv", [
        dict(tipo=t, familia=f, trimestre=q, repos=n)
        for (t, f, q), n in sorted(serie.items())])
    # concentración: parte de las descargas que reúnen los diez primeros
    conc = {}
    for fam in ("generación", "detección"):
        d = sorted((r["descargas_total"] for r in repos
                    if r["tipo"] == "modelo" and r["familia"] == fam),
                   reverse=True)
        conc[fam] = dict(modelos=len(d), descargas=sum(d),
                         cuota_top10=sum(d[:10]) / sum(d) if sum(d) else 0)
    en_marcha = Counter((r["familia"], r["hardware"]) for r in repos
                        if r["tipo"] == "space" and r["estado"] == "RUNNING")
    fichas = _leer(AQUI / "fichas_detectores.csv")
    def cuota(col, sub=None):
        g = [f for f in fichas if sub is None or f["subtipo"] == sub]
        return dict(n=len(g), si=sum(f[col] == "True" for f in g))
    resumen = dict(
        fecha_consulta=date.today().isoformat(), terminos=TERMINOS,
        apartados={f"{t}|{f}": n for (t, f), n in Counter(
            (r["tipo"], r["familia"]) for r in todos).items()},
        recuentos=recuentos, concentracion=conc,
        spaces_en_marcha={f"{f}|{h}": n for (f, h), n in en_marcha.items()},
        fichas={col: cuota(col) for col in (
            "ficha", "plantilla_vacia", "model_index", "metricas",
            "conjunto_prueba", "presentacion", "inyeccion")},
        fichas_vida={col: cuota(col, "presentación y vida") for col in (
            "metricas", "conjunto_prueba", "inyeccion")})
    (AQUI / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in recuentos:
        print(r)
    print(json.dumps(resumen["fichas"], ensure_ascii=False))
    print(json.dumps(conc, ensure_ascii=False))
    # 15 repositorios al azar de cada familia, para revisar a mano
    rng = random.Random(SEMILLA)
    for fam in ("generación", "detección"):
        g = [r for r in repos if r["familia"] == fam]
        for r in rng.sample(g, min(15, len(g))):
            print(fam, r["tipo"], r["subtipo"], r["modalidad"], r["id"])


def etapa_instantanea() -> None:
    """Congela la toma del día en ``instantaneas/AAAA-MM-DD/``.

    Copia los CSV y el resumen, y guarda comprimidos los metadatos completos
    que devolvió la API (uno por repositorio y tipo), para que la entrada
    lea siempre la misma toma y cualquiera pueda reconstruir sus cifras.
    """
    import gzip
    import shutil
    fecha = json.loads((AQUI / "resumen.json").read_text("utf-8"))[
        "fecha_consulta"]
    dest = AQUI / "instantaneas" / fecha
    dest.mkdir(parents=True, exist_ok=True)
    for nombre in ("repos.csv", "recuentos.csv", "serie_trimestral.csv",
                   "fichas_detectores.csv", "resumen.json"):
        shutil.copy2(AQUI / nombre, dest / nombre)
    vistos = {}
    for f in sorted((CRUDO / "busquedas").glob("*.json")):
        tipo = f.name.split("_", 1)[0]
        for it in json.loads(f.read_text("utf-8")):
            vistos[(tipo, it["id"])] = dict(it, tipo_api=tipo)
    with gzip.open(dest / "metadatos.json.gz", "wt", encoding="utf-8") as g:
        json.dump([vistos[k] for k in sorted(vistos)], g, ensure_ascii=False)
    print(dest, len(vistos))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("etapa", choices=["inventario", "fichas", "medir",
                                      "instantanea", "todo"])
    ap.add_argument("--sin-red", action="store_true",
                    help="reclasifica lo guardado sin consultar la API")
    a = ap.parse_args()
    if a.etapa in ("inventario", "todo"):
        etapa_inventario(a.sin_red)
    if a.etapa in ("fichas", "todo"):
        etapa_fichas()
    if a.etapa in ("medir", "todo"):
        etapa_medir()
    if a.etapa == "instantanea":
        etapa_instantanea()
