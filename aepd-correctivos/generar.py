"""Cómo terminan los procedimientos de la AEPD: multa, reducción o aviso.

Se mide, sobre las resoluciones que publica la Agencia Española de
Protección de Datos (AEPD) en aepd.es, qué poder correctivo usa en la
práctica: multa, multa reducida por pago voluntario o reconocimiento de
responsabilidad, apercibimiento, declaración de infracción a una
administración (artículo 77 de la LOPDGDD) o archivo.

Etapas, todas reejecutables:

1. ``serie``: número de resoluciones por año de firma y tipo de
   procedimiento, leído de los recuentos del propio buscador (2008-2026).
2. ``listado``: relación de resoluciones de los procedimientos
   sancionadores (PS) y de apercibimiento (PA y A) del buscador, página a
   página, con su fecha de firma y de publicación. El 15-10-2026 el
   buscador dejó de responder en su página 55.
2 bis. ``enumerar``: recorrido de los números de expediente PS y PA desde
   ANIO_INI en sus direcciones públicas de documento, que es la vía que
   completó la medición.
3. ``pdfs``: descarga cortés (una petición por segundo como máximo) de
   cada resolución y extracción del texto con pdftotext. Los PDF y los
   textos se guardan en una caché FUERA de este árbol (por defecto
   ``~/.cache/manplanet-datos/aepd-correctivos``; se cambia con la
   variable ``MANPLANET_CACHE``), porque contienen datos de terceros.
4. ``clasificar``: lectura de la parte dispositiva de cada resolución y
   escritura de los CSV de ``salidas/``.

Los CSV no guardan nombres ni NIF: de cada responsable solo se conserva
la clase que indica la letra de su NIF (administración, sociedad,
persona física…). El número de expediente permite volver a la fuente.

Requisitos: Python 3.10 o posterior, ``tqdm`` (``requirements.txt``) y
la orden ``pdftotext`` de poppler-utils.

Uso::

    python generar.py                     # todas las etapas
    python generar.py --etapa clasificar  # una sola etapa
"""

import argparse
import csv
import json
import logging
import os
import random
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

# rutas: las salidas junto a este fichero; la caché, fuera del árbol
DIR = Path(__file__).resolve().parent
DIR_SALIDAS = DIR / "salidas"
DIR_CACHE = Path(os.environ.get(
    "MANPLANET_CACHE", Path.home() / ".cache" / "manplanet-datos")
) / "aepd-correctivos"

UA = (
    "ManPlaNet-medicion/1.0 (+https://manpla.net; "
    "investigacion resoluciones publicas)"
)
BASE = "https://www.aepd.es"
LISTADO = BASE + "/informes-y-resoluciones/resoluciones"
SEMILLA = 20261015
ANIO_SERIE_INI = 2008
ANIO_INI = 2024
FECHA_CORTE = "2026-10-15"
PAUSA = 2.0
# entre páginas del listado, por debajo del umbral del cortafuegos
PAUSA_LISTADO = 5.0

# clase del responsable según la primera letra del NIF (Orden
# EHA/451/2008); las personas físicas llevan DNI o NIE, o aparecen
# seudonimizadas por la propia Agencia
CLASE_NIF = {
    "A": "sociedad", "B": "sociedad", "C": "sociedad", "D": "sociedad",
    "F": "sociedad", "G": "asociacion_fundacion", "H": "comunidad_propietarios",
    "E": "otra_entidad", "J": "otra_entidad", "U": "otra_entidad",
    "V": "otra_entidad", "N": "entidad_extranjera", "W": "entidad_extranjera",
    "R": "entidad_religiosa", "P": "administracion_local",
    "Q": "organismo_publico", "S": "administracion_estado_ccaa",
}
PUBLICAS = {"administracion_local", "organismo_publico",
            "administracion_estado_ccaa"}


def configurar_log() -> None:
    """Configura el registro en pantalla y en un fichero de la caché."""
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(DIR_CACHE / "generar.log")])


def pedir(url: str, intentos: int = 6, espera: int = 60) -> bytes:
    """Descarga una URL con reintentos y pausa cortés.

    Args:
        url: dirección completa.
        intentos: número máximo de intentos.
        espera: segundos de espera tras un fallo, multiplicados por el
            número de intento.

    Returns:
        El cuerpo de la respuesta.
    """
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                cuerpo = r.read()
            time.sleep(PAUSA)
            return cuerpo
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            logging.warning("fallo %s (%s), intento %d", url, e, i + 1)
            if i + 1 < intentos:
                time.sleep(espera * (i + 1))
    raise RuntimeError(f"no se pudo descargar {url}")


def url_listado(tipo: str | None, desde: str, hasta: str,
                pagina: int = 0) -> str:
    """Compone la URL del buscador de resoluciones con sus filtros."""
    # sin parámetro de orden: el buscador devuelve 500 o 503 con él
    q = [("fecha_firma_desde", desde), ("fecha_firma_hasta", hasta)]
    if tipo:
        q.append((f"tipo_procedimiento[{tipo}]", tipo))
    if pagina:
        q.append(("page", str(pagina)))
    return LISTADO + "?" + urllib.parse.urlencode(q)


def limpiar(html: str) -> str:
    """Quita etiquetas y normaliza espacios."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def escribir_csv(ruta: Path, filas: list[dict], campos: list[str]) -> None:
    """Escribe un CSV en UTF-8 con las columnas indicadas."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    logging.info("escrito %s (%d filas)", ruta.name, len(filas))


def mostrar_muestra(ruta: Path, n: int = 15) -> None:
    """Muestra n filas al azar de un CSV recién escrito."""
    with open(ruta, encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    random.seed(SEMILLA)
    for fila in random.sample(filas, min(n, len(filas))):
        print({k: v for k, v in fila.items() if v not in ("", None)})


# --- 1. serie por tipo de procedimiento ------------------------------------
RX_FACETA = re.compile(
    r'name="tipo_procedimiento\[[^\]]*\]" value="([^"]+)" '
    r'class="form-checkbox[^>]*>\s*<label[^>]*>(.*?)</label>', re.S)


def etapa_serie() -> None:
    """Recuenta las resoluciones por año de firma y tipo de procedimiento."""
    filas = []
    anio_fin = int(FECHA_CORTE[:4])
    for anio in tqdm(range(ANIO_SERIE_INI, anio_fin + 1), desc="serie"):
        hasta = f"{anio}-12-31"
        html = pedir(url_listado(None, f"{anio}-01-01", hasta)).decode()
        for tipo, etiqueta in RX_FACETA.findall(html):
            n = re.search(r"\(([\d\.]+)\)\s*$", limpiar(etiqueta))
            if n:
                filas.append({"anio": anio, "tipo": tipo,
                              "resoluciones": int(n.group(1).replace(".", ""))})
    escribir_csv(DIR_SALIDAS / "serie_tipos.csv", filas,
                 ["anio", "tipo", "resoluciones"])


# --- 2. listado de resoluciones --------------------------------------------
RX_ITEM = re.compile(
    r'<h2>([^<]+)</h2>.*?href="(/documento/[^"]+\.pdf)".*?'
    r'Fecha de publicación:.*?datetime="([^"]+)".*?'
    r'Fecha de firma:.*?datetime="([^"]+)"', re.S)
# prefijo del expediente de cada tipo de procedimiento que se estudia
PREFIJOS = {"PS": "Procedimiento Sancionador (PS)",
            "PA": "Procedimiento de Apercibimiento (PA)",
            "A": "Procedimiento de apercibimiento (A)"}


PAGINAS_FALLIDAS: list[int] = []


def es_reto(cuerpo: bytes) -> bool:
    """Reconoce la página de comprobación de navegador del cortafuegos."""
    return b"eval(function(p,a,c,k,e,d)" in cuerpo[:4000]


def pagina_cacheada(pagina: int) -> str:
    """Devuelve una página del listado completo, de la caché si ya se leyó.

    Solo se guarda una página que contiene resoluciones. Si el cortafuegos
    de la Agencia responde con su comprobación de navegador, no se intenta
    sortearla: se espera cinco minutos y se vuelve a pedir, hasta tres veces.
    """
    destino = DIR_CACHE / "listado" / f"pagina_{pagina:04d}.html"
    if destino.exists() and RX_ITEM.search(destino.read_text("utf-8")):
        return destino.read_text(encoding="utf-8")
    url = LISTADO + (f"?page={pagina}" if pagina else "")
    for intento in range(3):
        try:
            cuerpo = pedir(url, intentos=2, espera=20)
        except RuntimeError:
            # alguna página devuelve 503 de forma persistente; se anota
            logging.warning("página %d sin leer", pagina)
            PAGINAS_FALLIDAS.append(pagina)
            return ""
        if not es_reto(cuerpo):
            break
        logging.warning("comprobación de navegador en la página %d; "
                        "pausa de cinco minutos", pagina)
        time.sleep(300)
    else:
        PAGINAS_FALLIDAS.append(pagina)
        return ""
    time.sleep(PAUSA_LISTADO)
    html = cuerpo.decode()
    if RX_ITEM.search(html):
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(html, encoding="utf-8")
    return html


def etapa_listado() -> None:
    """Enumera las resoluciones PS, PA y A firmadas desde ANIO_INI.

    Los filtros del buscador (fecha y tipo) devolvían errores 500 y 503 el
    15-10-2026, y el listado sin filtros no: va ordenado por fecha de firma
    descendente, así que se recorre página a página hasta pasar de
    ANIO_INI. El tipo se toma del prefijo del expediente, y el recuento por
    año y prefijo se guarda para contrastarlo con ``serie_tipos.csv``.
    """
    filas, vistas, todas = [], set(), Counter()
    pagina, antiguas = 0, 0
    with tqdm(desc="páginas") as barra:
        while antiguas < 3:
            html = pagina_cacheada(pagina)
            items = RX_ITEM.findall(html)
            if not items:
                if pagina in PAGINAS_FALLIDAS and len(PAGINAS_FALLIDAS) < 20:
                    pagina += 1
                    continue
                break
            for titulo, pdf, publ, firma in items:
                if pdf in vistas:
                    continue
                vistas.add(pdf)
                pref = re.match(r"\s*([A-Z]+)[-/]", titulo)
                pref = pref.group(1) if pref else "?"
                todas[(firma[:4], pref)] += 1
                if pref in PREFIJOS and int(firma[:4]) >= ANIO_INI:
                    filas.append({
                        "expediente": titulo.strip(), "tipo": PREFIJOS[pref],
                        "anio_firma": int(firma[:4]),
                        "fecha_firma": firma[:10],
                        "fecha_publicacion": publ[:10], "pdf": pdf})
            # se para tras tres páginas seguidas firmadas antes de ANIO_INI
            antiguas = antiguas + 1 if max(int(f[:4]) for *_, f in items) \
                < ANIO_INI else 0
            pagina += 1
            barra.update(1)
    escribir_csv(DIR_SALIDAS / "listado.csv", filas,
                 ["expediente", "tipo", "anio_firma", "fecha_firma",
                  "fecha_publicacion", "pdf"])
    escribir_csv(DIR_SALIDAS / "cuadre_listado.csv",
                 [{"anio_firma": a, "prefijo": p, "n": n}
                  for (a, p), n in sorted(todas.items())],
                 ["anio_firma", "prefijo", "n"])
    (DIR_SALIDAS / "paginas_sin_leer.json").write_text(
        json.dumps(PAGINAS_FALLIDAS), encoding="utf-8")
    logging.info("páginas sin leer: %s", PAGINAS_FALLIDAS)
    mostrar_muestra(DIR_SALIDAS / "listado.csv")


# --- 2 bis. recorrido por número de expediente ------------------------------
def etapa_enumerar() -> None:
    """Pide las resoluciones PS y PA por su número de expediente.

    El 15-10-2026 el buscador de resoluciones devolvía errores 500 y 503 o
    una comprobación de navegador a partir de su página 55, y no se intentó
    sortearla. Los documentos se publican en direcciones predecibles
    (``/documento/ps-NNNNN-AAAA.pdf``), servidas con normalidad, así que se
    recorren los números de cada año de expediente desde ANIO_INI hasta 60
    números seguidos sin documento por encima del mayor ya visto. Un número
    sin documento responde 503 con una página breve: se cuenta como no
    publicado. Una petición cada PAUSA segundos.
    """
    (DIR_CACHE / "pdf").mkdir(parents=True, exist_ok=True)
    try:
        with open(DIR_SALIDAS / "listado.csv", encoding="utf-8") as f:
            vistos = list(csv.DictReader(f))
    except FileNotFoundError:
        vistos = []
    maximo = defaultdict(int)
    for v in vistos:
        m = re.match(r"(PS|PA)-(\d+)-(\d{4})", v["expediente"])
        if m:
            clave = (m.group(1).lower(), int(m.group(3)))
            maximo[clave] = max(maximo[clave], int(m.group(2)))
    filas = []
    anio_fin = int(FECHA_CORTE[:4])
    for pref in ("ps", "pa"):
        for anio in range(ANIO_INI, anio_fin + 1):
            n, fallos_seguidos = 0, 0
            barra = tqdm(desc=f"{pref} {anio}")
            while fallos_seguidos < 60 or n <= maximo[(pref, anio)]:
                n += 1
                nombre = f"{pref}-{n:05d}-{anio}.pdf"
                destino = DIR_CACHE / "pdf" / nombre
                if not destino.exists():
                    try:
                        req = urllib.request.Request(
                            f"{BASE}/documento/{nombre}",
                            headers={"User-Agent": UA})
                        with urllib.request.urlopen(req, timeout=60) as r:
                            cuerpo = r.read()
                    except urllib.error.HTTPError:
                        cuerpo = b""
                    except (urllib.error.URLError, TimeoutError,
                            ConnectionError) as e:
                        logging.warning("fallo de red en %s: %s", nombre, e)
                        time.sleep(30)
                        cuerpo = b""
                    time.sleep(PAUSA)
                    if cuerpo.startswith(b"%PDF"):
                        destino.write_bytes(cuerpo)
                if destino.exists():
                    fallos_seguidos = 0
                    filas.append({
                        "expediente": f"{pref.upper()}-{n:05d}-{anio}",
                        "tipo": PREFIJOS[pref.upper()],
                        "anio_expediente": anio,
                        "pdf": f"/documento/{nombre}"})
                else:
                    fallos_seguidos += 1
                barra.update(1)
            barra.close()
            logging.info("%s %d: %d resoluciones hasta el número %d", pref,
                         anio, sum(1 for f in filas if f["expediente"]
                                   .startswith(pref.upper())
                                   and f["anio_expediente"] == anio), n)
    escribir_csv(DIR_SALIDAS / "enumeracion.csv", filas,
                 ["expediente", "tipo", "anio_expediente", "pdf"])


# --- 3. descarga y texto ----------------------------------------------------
def resoluciones_conocidas() -> list[dict]:
    """Une el listado del buscador y el recorrido por número, sin repetir.

    Cada fila lleva el año del expediente, tomado de su número; la fecha de
    firma solo consta para las que salieron del buscador.
    """
    filas, vistas = [], set()
    for nombre in ("listado.csv", "enumeracion.csv"):
        ruta = DIR_SALIDAS / nombre
        if not ruta.exists():
            continue
        with open(ruta, encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                if fila["pdf"] in vistas:
                    continue
                vistas.add(fila["pdf"])
                m = re.search(r"-(\d{4})(?:-|$)", fila["expediente"])
                fila["anio_expediente"] = int(m.group(1)) if m else ""
                fila.setdefault("anio_firma", "")
                fila.setdefault("fecha_firma", "")
                fila.setdefault("fecha_publicacion", "")
                filas.append(fila)
    return filas


def etapa_pdfs() -> None:
    """Descarga cada resolución conocida y extrae su texto."""
    filas = resoluciones_conocidas()
    (DIR_CACHE / "pdf").mkdir(parents=True, exist_ok=True)
    (DIR_CACHE / "txt").mkdir(parents=True, exist_ok=True)
    fallos = 0
    for fila in tqdm(filas, desc="pdfs"):
        nombre = Path(fila["pdf"]).name
        pdf = DIR_CACHE / "pdf" / nombre
        txt = DIR_CACHE / "txt" / (nombre[:-4] + ".txt")
        if txt.exists() and txt.stat().st_size > 0:
            continue
        try:
            if not pdf.exists():
                cuerpo = pedir(BASE + fila["pdf"])
                if not cuerpo.startswith(b"%PDF"):
                    logging.warning("respuesta que no es PDF en %s; pausa",
                                    nombre)
                    time.sleep(300)
                    fallos += 1
                    continue
                pdf.write_bytes(cuerpo)
            subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)],
                           check=True, capture_output=True)
        except (RuntimeError, subprocess.CalledProcessError) as e:
            fallos += 1
            logging.warning("sin texto %s: %s", nombre, e)
    logging.info("pdfs: %d filas, %d fallos", len(filas), fallos)


# --- 4. clasificación de la parte dispositiva ------------------------------
RX_CIFRA = r"(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)"
# el importe puede ir en letra y repetido en cifra entre paréntesis
RX_MULTA = re.compile(r"(?:multa|sanci[óo]n)(?: administrativa)?"
                      r"(?: por un importe)? de(?=[\s\d])"
                      r"[^.;€]{0,80}?" + RX_CIFRA + r"\s*(?:€|euros|EUR)",
                      re.I)
RX_TOTAL_IMP = re.compile(r"Total:?\s*" + RX_CIFRA + r"\s*(?:€|euros)", re.I)
RX_DEFINITIVA = re.compile(r"(?:cantidad definitiva de|sanci[óo]n final de|"
                           r"importe asciende a|(?:realizado|efectuado) el "
                           r"pago voluntario de)\s*" + RX_CIFRA, re.I)
RX_TOTAL = re.compile(r"(?:cantidad total(?: de)?|arroja un total(?: de)?|"
                      r"presente procedimiento sancionador por la comisión "
                      r"de la citada infracción:)\s*" + RX_CIFRA, re.I)
RX_PCT = re.compile(r"reducci[óo]n (?:de un|del) (20|40)\s*%", re.I)
RX_PAGADO = re.compile(r"cuant[íi]a de " + RX_CIFRA
                       + r"\s*(?:€|euros)\s*haciendo uso de (las dos|"
                       r"ambas|una de las|la)\s*reducci", re.I)
# admite «Artículo 6.1. del RGPD» (punto tras el número), «artículo 13 RGPD»
# (sin «del») y las listas «─ Artículo 5.1.c) del RGPD»
RX_ARTICULO = re.compile(
    r"art[íi]culos?\s+(\d+(?:\.\d+)*(?:\.?\s?[a-z]\))?)\.?\s+(?:(?:del?|de la)\s+)?"
    r"(RGPD|LOPDGDD|LSSI|LGT(?:el)?(?: 11/2022)?|LOPD|LO 7/2021)", re.I)
RX_NIF = re.compile(r"(?:NIF|N\.I\.F\.|CIF|DNI|NIE)\s*(?:n\.?º)?[\.:]*\s*"
                    r"([A-Z0-9\*][A-Z0-9\*\-]{6,11})", re.I)
RX_PUBLICA = re.compile(
    r"AYUNTAMIENTO|CONSEJER[IÍ]A|MINISTERIO|DIRECCI[OÓ]N GENERAL|"
    r"UNIVERSIDAD|DIPUTACI[OÓ]N|JUNTA DE|GOBIERNO DE|SERVICIO \w+ DE SALUD|"
    r"CONCELLO|AJUNTAMENT|CABILDO|MANCOMUNIDAD|CONSORCIO|POLIC[IÍ]A|"
    r"GUARDIA CIVIL|DEPARTAMENTO DE", re.I)
RX_SOCIEDAD = re.compile(r"\bS\.?\s?[LA]\.?(?:U\.?)?(?:\b|$)|SOCIEDAD|"
                         r"LIMITED|LTD|GMBH|\bINC\b|\bB\.?V\.?\b", re.I)


def importe(cifra: str) -> float:
    """Convierte «6.000,00» en 6000.0."""
    return float(cifra.replace(".", "").replace(",", "."))


def normalizar(texto: str) -> str:
    """Une líneas, quita espacios repetidos y pies de página de la AEPD."""
    texto = re.sub(r"C/ Jorge Juan, 6.*?\d+/\d+", " ", texto, flags=re.S)
    texto = re.sub(r"\s+", " ", texto)
    # «5. 000 euros»: el salto de línea parte algunas cifras
    return re.sub(r"(\d)\.\s(\d{3})\b", r"\1.\2", texto)


def dispositiva(texto: str) -> str:
    """Devuelve la parte dispositiva: de RESUELVE a los recursos."""
    i = texto.rfind("RESUELVE")
    if i < 0:
        i = texto.rfind("ACUERDA")
    if i < 0:
        return ""
    fin = len(texto)
    for marca in ("De conformidad con lo establecido en el artículo 50",
                  "Contra esta resolución", "contra esta resolución"):
        j = texto.find(marca, i)
        if j > 0:
            fin = min(fin, j)
    return texto[i:fin]


def clase_nif(nif: str) -> str:
    """Clase del titular según la forma de su NIF."""
    nif = nif.strip(".,;:()-").upper()
    if "*" in nif or re.fullmatch(r"\d{8}[A-Z]", nif) or nif[:1] in "XYZ":
        return "persona_fisica"
    return CLASE_NIF.get(nif[:1], "otra_entidad")


def destinatario(parte: str) -> str:
    """Nombre del destinatario tal como figura en «NOTIFICAR … a X»."""
    m = re.search(r"NOTIFICAR la presente resolución a(?:l| la| los)? "
                  r"(.{2,160}?)(?:, con |\.\s*(?:[A-ZÁÉÍÓÚ]{4,}|$)|$)",
                  parte)
    return m.group(1) if m else ""


def clase_responsable(texto: str, parte: str) -> str:
    """Clasifica al responsable sin guardar su nombre ni su NIF.

    Se usa primero el NIF que acompaña al destinatario en la parte
    dispositiva; si no lo hay, el NIF no enmascarado más repetido del
    texto; y si tampoco, la forma del nombre del destinatario.
    """
    m = RX_NIF.search(parte)
    if m:
        return clase_nif(m.group(1))
    nombre = destinatario(parte)
    if nombre:
        if re.search(r"\b[A-Z]\.[A-Z]\.[A-Z]\.", nombre):
            return "persona_fisica"
        if RX_PUBLICA.search(nombre):
            return "publica_por_nombre"
        if RX_SOCIEDAD.search(nombre):
            return "sociedad"
        k = texto.find(nombre.split(",")[0][:40])
        if k >= 0:
            m = RX_NIF.search(texto[k:k + 300])
            if m:
                return clase_nif(m.group(1))
    nifs = Counter(n.upper() for n in RX_NIF.findall(texto) if "*" not in n)
    if nifs:
        return clase_nif(nifs.most_common(1)[0][0])
    return "sin_dato"


def infringidos(parte: str) -> list[str]:
    """Artículos que la resolución da por infringidos (no los de tipificar)."""
    arts = set()
    for m in RX_ARTICULO.finditer(parte):
        # 300 caracteres atrás: en las listas «por una infracción de: ─
        # Artículo … ─ Artículo …», el «infracción» queda lejos del segundo
        previo = parte[max(0, m.start() - 300):m.start()].lower()
        if "tipificad" in previo[-25:] or "virtud" in previo[-25:]:
            continue
        if re.search(r"infrac|infringi|vulnera", previo):
            ley = m.group(2).upper()
            ley = "LGT" if ley.startswith("LGT") else ley
            art = re.sub(r"\s", "", m.group(1)).rstrip(".")
            # «5.1 c)» y «5.1.c)» son el mismo apartado
            art = re.sub(r"(\d)([a-z]\))$", r"\1.\2", art)
            num = int(re.match(r"\d+", art).group())
            if (ley == "RGPD" and num == 83) or (ley == "LOPDGDD" and
                    71 <= num <= 78) or (ley == "LSSI" and 38 <= num <= 40):
                continue
            # 58.1.a), 58.2.d)…: poderes de la Agencia que cita al ordenar,
            # no infracciones (la infracción es «58.1» o «58.2» a secas)
            if ley == "RGPD" and re.match(r"58\.\d\.[a-z]\)", art):
                continue
            arts.add(f"{art} {ley}")
    return sorted(arts)


def clasificar_texto(crudo: str) -> dict:
    """Lee una resolución y devuelve su desenlace y sus importes.

    Args:
        crudo: texto completo extraído del PDF.

    Returns:
        Diccionario con la cabecera, el desenlace, los importes, la
        reducción aplicada, si se ordenan medidas, la clase del
        responsable y los artículos infringidos.
    """
    t = normalizar(crudo)
    cab = t[:1500].upper()
    parte = dispositiva(t)
    up = parte.upper()
    r = {"cabecera": "", "desenlace": "otro", "multa_inicial": "",
         "importe_final": "", "reduccion_pct": "",
         # «ORDENAR el ARCHIVO» no es una medida correctora
         "ordena_medidas": int(bool(re.search(r"ORDENAR\b(?!\s+EL\s+ARCHIVO)",
                                              up))),
         "clase_responsable": clase_responsable(t, parte),
         # régimen del artículo 77: la resolución se comunica al Defensor del
         # Pueblo (artículo 77.5) y no impone multa
         "regimen_art77": int(bool(re.search(r"Defensor del Pueblo|77\.5",
                                             parte))),
         "articulos": "", "leyes": ""}
    if "REVOCACI" in cab:
        r["cabecera"] = "revocacion"
        r["desenlace"] = "revocacion"
        return r
    if ("TERMINACI" in cab or "RECONOCIMIENTO DE LA RESPONSABILIDAD" in cab) \
            and ("PAGO" in cab or "RECONOCIMIENTO" in cab):
        r["cabecera"] = "terminacion_art85"
    elif "APERCIBIMIENTO" in cab:
        r["cabecera"] = "apercibimiento"
    elif "ARCHIVO" in cab or "CADUCIDAD" in cab:
        r["cabecera"] = "archivo"
    elif "PROCEDIMIENTO SANCIONADOR" in cab:
        r["cabecera"] = "sancionador"
    multas = [importe(c) for c in RX_MULTA.findall(parte)]
    if not multas and "IMPONER" in up:
        # desglose por infracción con un «Total: X euros» al final
        total_imp = RX_TOTAL_IMP.search(parte)
        if total_imp:
            multas = [importe(total_imp.group(1))]
    definitiva = RX_DEFINITIVA.search(parte)
    pagado = RX_PAGADO.search(t)
    sin_importe = not (multas or definitiva or pagado)
    if r["regimen_art77"] and sin_importe:
        # una administración no recibe multa: la terminación por
        # reconocimiento declara la infracción
        r["desenlace"] = "declaracion_infraccion"
    elif r["cabecera"] == "terminacion_art85" or definitiva \
            or ("TERMINACIÓN DEL PROCEDIMIENTO" in up and "85" in up):
        r["desenlace"] = "terminacion_reducida"
        pct = RX_PCT.search(parte)
        if definitiva:
            r["importe_final"] = importe(definitiva.group(1))
        elif pagado:
            r["importe_final"] = importe(pagado.group(1))
        if pct:
            r["reduccion_pct"] = int(pct.group(1))
        elif pagado:
            r["reduccion_pct"] = (40 if pagado.group(2).lower()
                                  in ("las dos", "ambas") else 20)
        total = RX_TOTAL.search(parte)
        if total:
            r["multa_inicial"] = importe(total.group(1))
        elif r["importe_final"] != "" and r["reduccion_pct"]:
            r["multa_inicial"] = round(
                r["importe_final"] / (1 - r["reduccion_pct"] / 100), 2)
    elif multas and "IMPONER" in up:
        r["desenlace"] = "multa"
        r["multa_inicial"] = r["importe_final"] = sum(multas)
        r["reduccion_pct"] = 0
    elif re.search(r"DECLARAR\b.{0,400}?HA INFRINGIDO", up):
        r["desenlace"] = "declaracion_infraccion"
    elif re.search(r"PRIMERO:?\s*(?:ORDENAR EL |PROCEDER AL )?ARCHIV", up):
        # «ARCHIVAR el procedimiento de apercibimiento» es un archivo
        r["desenlace"] = "archivo"
    elif "APERCIBI" in up:
        r["desenlace"] = "apercibimiento"
    elif re.search(r"ARCHIV|CADUCIDAD", up):
        r["desenlace"] = "archivo"
    arts = infringidos(parte)
    if not arts:
        # en las terminaciones, los artículos están en el acuerdo de inicio
        # o en la propuesta transcritos dentro de la resolución
        arts = infringidos(t)
    r["articulos"] = ";".join(arts)
    r["leyes"] = ";".join(sorted({a.split()[-1] for a in arts}))
    return r


def etapa_clasificar() -> None:
    """Clasifica todas las resoluciones descargadas y escribe los CSV."""
    filas = resoluciones_conocidas()
    salida, sin_texto = [], 0
    for fila in tqdm(filas, desc="clasificar"):
        txt = DIR_CACHE / "txt" / (Path(fila["pdf"]).name[:-4] + ".txt")
        if not txt.exists():
            sin_texto += 1
            continue
        r = clasificar_texto(txt.read_text(encoding="utf-8", errors="ignore"))
        salida.append({**{k: fila[k] for k in ("expediente", "tipo",
                                               "anio_expediente",
                                               "anio_firma", "fecha_firma",
                                               "fecha_publicacion")}, **r})
    campos = ["expediente", "tipo", "anio_expediente", "anio_firma",
              "fecha_firma",
              "fecha_publicacion", "cabecera", "desenlace", "multa_inicial",
              "importe_final", "reduccion_pct", "ordena_medidas",
              "clase_responsable", "regimen_art77", "articulos", "leyes"]
    escribir_csv(DIR_SALIDAS / "resoluciones.csv", salida, campos)
    logging.info("sin texto: %d", sin_texto)
    # recuento por año y desenlace, con el sector del responsable
    cuenta = Counter()
    for s in salida:
        sector = "art77" if s["regimen_art77"] else "resto"
        cuenta[(s["anio_expediente"], s["desenlace"], sector)] += 1
    escribir_csv(DIR_SALIDAS / "desenlaces_anuales.csv",
                 [{"anio": a, "desenlace": d, "sector": sct, "n": n}
                  for (a, d, sct), n in sorted(cuenta.items())],
                 ["anio", "desenlace", "sector", "n"])
    # importes por año (solo multas y terminaciones con importe leído)
    por_anio = defaultdict(list)
    for s in salida:
        if s["importe_final"] != "":
            por_anio[s["anio_expediente"]].append(s)
    filas_imp = []
    for anio, lista in sorted(por_anio.items()):
        finales = sorted(float(s["importe_final"]) for s in lista)
        n = len(finales)
        filas_imp.append({
            "anio": anio, "n": n, "suma_final": round(sum(finales), 2),
            "mediana_final": finales[n // 2] if n % 2 else
            (finales[n // 2 - 1] + finales[n // 2]) / 2,
            "reduccion_0": sum(s["reduccion_pct"] == 0 for s in lista),
            "reduccion_20": sum(s["reduccion_pct"] == 20 for s in lista),
            "reduccion_40": sum(s["reduccion_pct"] == 40 for s in lista)})
    escribir_csv(DIR_SALIDAS / "importes_anuales.csv", filas_imp,
                 list(filas_imp[0]))
    meta = {"fecha_corte": FECHA_CORTE, "generado":
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "resoluciones": len(salida), "sin_texto": sin_texto}
    (DIR_SALIDAS / "volumenes.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    mostrar_muestra(DIR_SALIDAS / "resoluciones.csv")


ETAPAS = {"serie": etapa_serie, "listado": etapa_listado,
          "enumerar": etapa_enumerar, "pdfs": etapa_pdfs,
          "clasificar": etapa_clasificar}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--etapa", choices=list(ETAPAS))
    args = ap.parse_args()
    configurar_log()
    for nombre, funcion in ETAPAS.items():
        if args.etapa in (None, nombre):
            logging.info("etapa %s", nombre)
            funcion()
