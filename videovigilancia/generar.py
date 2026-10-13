"""Licitaciones de videovigilancia que piden capacidades de IA.

Se mide, sobre los datos abiertos de sindicación de la Plataforma de
Contratación del Sector Público (PLACSP), cuántas licitaciones españolas
de videovigilancia piden reconocimiento facial o biometría, búsqueda por
apariencia, analítica de vídeo o IA genérica y lectura de matrículas.

Etapas, todas reejecutables y con caché en disco junto a este fichero:

1. ``zips``: descarga de los ficheros mensuales y anuales de los
   conjuntos 643 (perfiles alojados en PLACSP) y 1044 (plataformas
   autonómicas agregadas, sin menores).
2. ``parseo``: lectura de cada entrada CODICE/ATOM, deduplicación por
   expediente y órgano (se conserva la entrada con ``updated`` mayor) y
   preselección de videovigilancia por CPV o por palabras del título.
3. ``pliegos``: descarga cortés (una petición por segundo como máximo)
   del pliego de prescripciones técnicas y extracción con pdftotext.
4. ``salidas``: clasificación por capacidad a dos niveles (A: título y
   resumen; B: texto completo del pliego técnico) y escritura de CSV.

Requisitos: Python 3.10 o posterior, ``tqdm`` (``requirements.txt``) y
la orden ``pdftotext`` de poppler-utils. Si están instaladas, se usan
además ``mutool`` (mupdf-tools) para leer PDF con la tabla de
referencias dañada y ``soffice`` (LibreOffice) para los .doc y .rtf.

Uso::

    python generar.py                 # todas las etapas
    python generar.py --etapa parseo  # una sola etapa
"""

import argparse
import csv
import gzip
import hashlib
import http.client
import json
import logging
import random
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

# rutas: todo se escribe junto a este fichero
DIR = Path(__file__).resolve().parent
DIR_ZIPS = DIR / "zips"
DIR_CACHE = DIR / "cache"
DIR_PLIEGOS = DIR / "pliegos"
DIR_SALIDAS = DIR / "salidas"

UA = (
    "ManPlaNet-medicion/1.0 (+https://manpla.net; "
    "investigacion contratacion publica)"
)
BASE = "https://contrataciondelsectorpublico.gob.es/sindicacion"
SEMILLA = 20261006
FECHA_INI = "2024-01-01"
FECHA_FIN = "2026-10-12"
# por debajo de este número de expedientes se leen todos los pliegos
LIMITE_CENSO = 4000

# ficheros de sindicación que cubren enero de 2024 a octubre de 2026;
# del 643 se usan los mensuales (los de 2024 se sirven aunque la página
# solo enlace el anual) y del 1044, los tres anuales
F643 = "licitacionesPerfilesContratanteCompleto3"
F1044 = "PlataformasAgregadasSinMenores"
MESES = ([f"{a}{m:02d}" for a in (2024, 2025) for m in range(1, 13)]
         + [f"2026{m:02d}" for m in range(1, 11)])
ZIPS: list[tuple[str, str]] = (
    [("643", f"{F643}_{p}.zip") for p in MESES]
    + [("1044", f"{F1044}_{a}.zip") for a in ("2024", "2025", "2026")]
)

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "cbc": "urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:dgpe:names:draft:codice:schema:xsd:"
    "CommonAggregateComponents-2",
    "cace": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:"
    "CommonAggregateComponents-2",
    "cbce": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:"
    "CommonBasicComponents-2",
    "at": "http://purl.org/atompub/tombstones/1.0",
}
T_ENTRY = "{%s}entry" % NS["atom"]
T_DELETED = "{%s}deleted-entry" % NS["at"]

# lista ContractingAuthorityCode-2.10.gc de CODICE (DGPE)
TIPOS_ORGANO = {
    "1": "Autoridad estatal",
    "2": "Autoridad regional",
    "3": "Autoridad local",
    "4": "Organismo de Derecho público",
    "5": "Otras Entidades del Sector Público",
    "6": "Organismo de Derecho público bajo el control de una "
    "autoridad estatal",
    "7": "Organismo de Derecho público bajo el control de una "
    "autoridad regional",
    "8": "Organismo de Derecho público bajo el control de una "
    "autoridad local",
    "9": "Empresa pública bajo el control de una autoridad estatal",
    "10": "Empresa pública bajo el control de una autoridad regional",
    "11": "Empresa pública bajo el control de una autoridad local",
    "12": "Entidad con derechos especiales o exclusivos",
}
# lista SyndicationContractFolderStatusCode-2.04.gc
ESTADOS = {
    "PRE": "Anuncio Previo",
    "PUB": "En plazo",
    "EV": "Pendiente de adjudicación",
    "ADJ": "Adjudicada",
    "RES": "Resuelta",
    "ANUL": "Anulada",
}

# cpv de videovigilancia, descripción oficial de CPV2008-2.04.gc
CPV_VV = {
    "32323500": "Sistema de vigilancia por vídeo.",
    "35125300": "Cámaras de seguridad.",
    "32234000": "Cámaras de televisión en circuito cerrado.",
    "32235000": "Sistema de vigilancia en circuito cerrado.",
    "32231000": "Aparatos de televisión en circuito cerrado.",
    "92222000": "Servicios de televisión en circuito cerrado.",
}

# palabras de selección sobre el título normalizado; además del
# castellano se recogen las formas catalana (ca), gallega (gl) y vasca
# (eu) que aparecen en las plataformas autonómicas del conjunto 1044
RE_SELECCION = re.compile(
    r"video\s*-?\s*vi(?:gil|xil)ancia"  # es, ca, gl
    r"|bideozain"  # eu
    r"|\bcam(?:aras?|eres?|era)\b[^.;]{0,40}\bvi(?:gil|xil)ancia"
    r"|\bcam(?:aras?|eres?|era) de segur(?:idad|etat)"
    r"|\bcctv\b|\bc\.c\.t\.v\b"
    r"|circuit(?:o)? (?:cerrado|tancat|pechado) de (?:televisio|tv|camar"
    r"|camer|video)"
    r"|lectura de matricul|lector(?:es|s)? de matricul"
    r"|recono(?:cimiento|ixement) de matricul|\blpr\b|\banpr\b"
    r"|video\s*-?\s*analitica|analitica de video"
    r"|reconocimiento facial|reconeixement facial|reconecemento facial"
)

# falsos positivos evidentes del título: vigilancia sanitaria, cámaras
# frigoríficas o hiperbáricas, cámaras de inspección de redes de
# saneamiento y la sigla ANPR de las instalaciones de agua no potable
RE_EXCLUSION = re.compile(
    r"vigilancia de la salud|vigilancia epidemiologica"
    r"|camaras? frigorific|camaras? de (?:frio|congelacion|conservacion)"
    r"|camaras? hiperbaric"
    r"|saneamiento|alcantarillad|clavegueram|desatasc|legionel"
    r"|camaras? de inspeccion|inspeccion (?:de )?(?:redes|tuberias"
    r"|colectores|conducciones)"
)
# lotes de inspección de redes con cámara y tractor cctv
RE_EXCLUSION_LOTES = re.compile(
    r"tractor cctv|inspeccion (?:de )?(?:redes|tuberias|colectores)"
)
# en la vía solo cpv, títulos cuyo objeto no es la videovigilancia
RE_EXCLUSION_CPV = re.compile(
    r"camaras? web|cameres? web|webcam|fauna|lidar|uniformi|vestuari"
    r"|mobiliari|material deportivo|votacion|per a l.exposicio|robotitzad"
    r"|inspeccion telescopica|gesell|suministro de agua y electricidad"
    r"|centro cultural|\btscm\b|grabacion eng"
)
# indicios débiles en el título que sostienen la vía solo cpv cuando el
# cpv de videovigilancia no es el principal del expediente
RE_INDICIO = re.compile(
    r"camar|camer|video|cctv|vigilan|vixilan|grabacio|gravacio"
    r"|vision artificial|visualizacio|seguridad(?! social)|seguretat"
    r"|segurtasun"
    r"|trafico|transit|matricul|smart|intrus|control de acceso"
    r"|control d.acces|\bzbe\b|bajas emisiones|baixes emissions"
)
# palabras de seguridad que impiden aplicar ``RE_EXCLUSION_CPV``
RE_SEGURIDAD = re.compile(
    r"seguridad|seguretat|segurtasun|vigilan|vixilan|cctv"
)
# palabras que, si están en el título, impiden la exclusión
RE_FUERTE = re.compile(
    r"video\s*-?\s*vi(?:gil|xil)ancia|bideozain|seguridad ciudadana"
    r"|seguretat ciutadana|\bcam(?:aras?|eres?|era) de vi(?:gil|xil)ancia"
)


def rx(patron: str) -> re.Pattern:
    """Compila un patrón en el que cada espacio admite saltos de línea.

    Args:
        patron: Expresión regular escrita con espacios simples.

    Returns:
        Patrón compilado con ``\\s+`` en lugar de cada espacio.
    """
    return re.compile(patron.replace(" ", r"\s+"))


# familias de capacidad (texto en minúscula y sin tildes), en castellano
# con sus equivalentes catalanes y gallegos. «facial» y «apariencia» son
# las familias amplias del encargo; sus variantes estrictas prescinden
# de términos que en los pliegos aparecen también fuera de la
# videovigilancia (biometría de control de accesos, «rostro» en equipos
# de protección, «atributos» y «vestimenta» sueltos)
FAMILIAS: dict[str, re.Pattern] = {
    "facial": rx(
        r"reconocimiento facial|identificacion facial|deteccion facial"
        r"|reconeixement facial|identificacio facial|deteccio facial"
        r"|reconecemento facial|biometri\w*|\brostros?\b|\brostres?\b"
    ),
    "facial_estricto": rx(
        r"reconocimiento facial|identificacion facial"
        r"|reconeixement facial|identificacio facial|reconecemento facial"
        r"|reconocimiento de (?:caras|rostros)|reconeixement de (?:cares"
        r"|rostres)|face recognition|facial recognition|face matching"
        r"|comparacion facial"
    ),
    "apariencia": rx(
        r"busqueda por (?:apariencia|atributos)|\batributos\b"
        r"|cerca per (?:aparenca|atributs)|busca por aparencia"
        r"|\batributs\b|vestimenta|colou?r de (?:la )?(?:ropa|roba)"
    ),
    "apariencia_estricta": rx(
        r"busqueda por (?:apariencia|atributos)|cerca per (?:aparenca"
        r"|atributs)|busca por aparencia|appearance search"
        r"|(?:busqueda|buscar|busca|cerca|cercar)\b[^.]{0,60}\batribut"
        r"|atribut(?:os|s) (?:fisic|de (?:la |las |les )?persona"
        r"|de (?:los |els )?rostr|facial)"
        r"|(?:rostros?|rostres?|facial) (?:con|amb) atribut"
        r"|colou?r de (?:la )?(?:ropa|roba)|tipo de ropa"
    ),
    "analitica_ia": rx(
        r"analitica de video|video\s*-?\s*analitica|analitica de imagen"
        r"|inteligencia artificial|intel.?ligencia artificial"
        r"|intelixencia artificial|\bia\b|aprendizaje profundo"
        r"|aprenentatge profund|deep learning"
        r"|deteccion de (?:objetos|personas)"
        r"|deteccio d.(?:objectes|persones)|\bconteo\b|\bcomptatge\b"
    ),
    "lpr": rx(
        r"lectura de matricul\w*|lector(?:es|s)? de matricul\w*"
        r"|recono(?:cimiento|ixement) de matricul\w*|\blpr\b|\banpr\b"
        r"|ocr de matricul\w*|\bocr\b[^.]{0,30}matricul"
    ),
}

# cláusulas que excluyen la capacidad mencionada (frase completa)
RE_NEGACION_FUERTE = re.compile(
    r"excluid|excluye|exclou|exclos|en ningun caso|en cap cas|prohib"
    r"|deshabilitad|desactivad|no forman? parte|no seran? objeto"
    r"|no se admitir|no s.admetr|sin que|sense que|quedan? fuera"
    r"|\bno (?:se )?(?:incluir|utilizar|configurar|instalar|activar"
    r"|habilitar|permitir|contemplar)\w*"
)
# negación simple justo antes de la mención
RE_NEGACION_DEBIL = re.compile(
    r"\bno\b(?!\s+(?:menos|inferior|superior|mayor|menor|solo))|\bni\b"
)
# frontera de frase para recortar la cita literal
RE_FRONTERA = re.compile(r"[.;]\s|\n\s*\n")

RE_PPT_NOMBRE = re.compile(
    r"\bppt\b|prescripciones? tecnicas?|pliego tecnico|pliego de "
    r"condiciones tecnicas|prescripcions? tecniques?"
)

log = logging.getLogger("videovigilancia")

# tabla de normalización 1:1 que conserva las posiciones
_ACENTOS = str.maketrans(
    "áéíóúàèìòùäëïöüâêîôûñçÁÉÍÓÚÀÈÌÒÙÄËÏÖÜÂÊÎÔÛÑÇ",
    "aeiouaeiouaeiouaeiouncAEIOUAEIOUAEIOUAEIOUNC",
)


def normalizar(texto: str) -> str:
    """Pasa a minúscula y quita tildes sin cambiar la longitud.

    Args:
        texto: Texto original.

    Returns:
        Texto normalizado de la misma longitud que el original cuando es
        posible; si no, la forma NFKD sin marcas.
    """
    s = texto.translate(_ACENTOS).lower()
    if len(s) == len(texto):
        return s
    s = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def configurar_log() -> None:
    """Configura el registro en consola y en fichero."""
    DIR_SALIDAS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(DIR_SALIDAS / "generar.log"),
        ],
    )


def mostrar_muestra(ruta: Path, n: int = 15) -> None:
    """Imprime n filas aleatorias de un CSV recién escrito.

    Args:
        ruta: Ruta del CSV.
        n: Número de filas a mostrar.
    """
    with ruta.open(encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    rng = random.Random(SEMILLA)
    muestra = rng.sample(filas, min(n, len(filas)))
    print(f"\n== {ruta.name}: {len(filas)} filas; {len(muestra)} al azar ==")
    for fila in muestra:
        corto = {k: (v[:60] if isinstance(v, str) else v)
                 for k, v in fila.items()}
        print(corto)


def escribir_csv(ruta: Path, filas: list[dict], campos: list[str]) -> None:
    """Escribe un CSV y muestra 15 filas aleatorias.

    Args:
        ruta: Ruta de salida.
        filas: Filas como diccionarios.
        campos: Orden de columnas.
    """
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    log.info("se guarda %s (%d filas)", ruta.name, len(filas))
    mostrar_muestra(ruta)


# --------------------------------------------------------------------
# etapa 1: descarga de los zips
# --------------------------------------------------------------------

def descargar(url: str, destino: Path, intentos: int = 4) -> str:
    """Descarga una URL a disco con reintentos.

    Args:
        url: Dirección de origen.
        destino: Fichero de destino.
        intentos: Número máximo de intentos.

    Returns:
        Código HTTP final como texto, o la clase de error.
    """
    estado = "sin_intento"
    for i in range(intentos):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        tmp = destino.with_suffix(destino.suffix + ".part")
        try:
            with urllib.request.urlopen(req, timeout=120) as r, \
                    tmp.open("wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
                estado = str(r.status)
            tmp.replace(destino)
            return estado
        except urllib.error.HTTPError as e:
            estado = str(e.code)
            if e.code in (403, 404, 410):
                return estado
        except (urllib.error.URLError, TimeoutError, OSError,
                http.client.HTTPException) as e:
            estado = type(e).__name__
        log.warning("intento %d fallido %s: %s", i + 1, url, estado)
        time.sleep(10)
    return estado


def etapa_zips() -> None:
    """Descarga los zips de sindicación que falten o estén dañados."""
    for feed, nombre in tqdm(ZIPS, desc="zips"):
        destino = DIR_ZIPS / feed / nombre
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists() and zipfile.is_zipfile(destino):
            continue
        url = f"{BASE}/sindicacion_{feed}/{nombre}"
        estado = descargar(url, destino)
        log.info("zip %s -> HTTP %s", nombre, estado)
        time.sleep(1)


# --------------------------------------------------------------------
# etapa 2: parseo de las entradas CODICE
# --------------------------------------------------------------------

def _txt(e: ET.Element | None, ruta: str) -> str:
    """Devuelve el texto del primer nodo que cumple la ruta, o ''."""
    if e is None:
        return ""
    n = e.find(ruta, NS)
    return (n.text or "").strip() if n is not None else ""


def _todos(e: ET.Element, ruta: str) -> list[str]:
    """Devuelve el texto de todos los nodos que cumplen la ruta."""
    return [(n.text or "").strip() for n in e.findall(ruta, NS)]


def _utc(marca: str) -> str:
    """Convierte una marca ISO con zona horaria a UTC ISO."""
    try:
        d = datetime.fromisoformat(marca)
    except ValueError:
        return marca
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")


def _documentos(cfs: ET.Element, etiqueta: str) -> list[tuple[str, str]]:
    """Extrae (nombre, url) de las referencias documentales indicadas."""
    salida = []
    for d in cfs.findall(etiqueta, NS):
        nombre = _txt(d, "cbc:ID")
        url = _txt(d, "cac:Attachment/cac:ExternalReference/cbc:URI")
        salida.append((nombre, url))
    return salida


def _generales(cfs: ET.Element) -> list[tuple[str, str]]:
    """Extrae (nombre, url) de los documentos generales del expediente."""
    salida = []
    ruta = "cace:GeneralDocument/cace:GeneralDocumentDocumentReference"
    for d in cfs.findall(ruta, NS):
        ext = "cac:Attachment/cac:ExternalReference/"
        nombre = _txt(d, ext + "cbc:FileName") or _txt(d, "cbc:ID")
        salida.append((nombre, _txt(d, ext + "cbc:URI")))
    return salida


def registro_completo(entry: ET.Element, feed: str, zipname: str) -> dict:
    """Extrae todos los campos de interés de una entrada.

    Args:
        entry: Nodo ``atom:entry``.
        feed: Conjunto de sindicación (643 o 1044).
        zipname: Fichero zip de procedencia.

    Returns:
        Diccionario plano con los campos del expediente.
    """
    cfs = entry.find("cace:ContractFolderStatus", NS)
    lcp = cfs.find("cace:LocatedContractingParty", NS)
    party = lcp.find("cac:Party", NS) if lcp is not None else None
    ids = {}
    if party is not None:
        for pid in party.findall("cac:PartyIdentification/cbc:ID", NS):
            ids[pid.get("schemeName", "")] = (pid.text or "").strip()
    cadena = []
    if lcp is not None:
        nodo = lcp.find("cace:ParentLocatedParty", NS)
        while nodo is not None:
            cadena.append(_txt(nodo, "cac:PartyName/cbc:Name"))
            nodo = nodo.find("cace:ParentLocatedParty", NS)
    pp = cfs.find("cac:ProcurementProject", NS)
    lotes = cfs.findall("cac:ProcurementProjectLot", NS)
    cpv = _todos(pp, "cac:RequiredCommodityClassification/"
                 "cbc:ItemClassificationCode") if pp is not None else []
    cpv_lotes, nombres_lotes, nuts, zonas = [], [], [], []
    if pp is not None:
        nuts += _todos(pp, "cac:RealizedLocation/cbc:CountrySubentityCode")
        zonas += _todos(pp, "cac:RealizedLocation/cbc:CountrySubentity")
    for lote in lotes:
        lp = lote.find("cac:ProcurementProject", NS)
        if lp is None:
            continue
        nombres_lotes.append(_txt(lp, "cbc:Name"))
        cpv_lotes += _todos(lp, "cac:RequiredCommodityClassification/"
                            "cbc:ItemClassificationCode")
        nuts += _todos(lp, "cac:RealizedLocation/cbc:CountrySubentityCode")
        zonas += _todos(lp, "cac:RealizedLocation/cbc:CountrySubentity")
    avisos = []
    for vni in cfs.findall("cace:ValidNoticeInfo", NS):
        tipo = _txt(vni, "cbce:NoticeTypeCode")
        for f in _todos(vni, "cace:AdditionalPublicationStatus/"
                        "cace:AdditionalPublicationDocumentReference/"
                        "cbc:IssueDate"):
            avisos.append((tipo, f))
    f_cn = sorted(f for t, f in avisos if t == "DOC_CN" and f)
    f_todas = sorted(f for _, f in avisos if f)
    pub = f_cn[0] if f_cn else (f_todas[0] if f_todas else "")
    tipo = _txt(lcp, "cbc:ContractingPartyTypeCode")
    ppt = _documentos(cfs, "cac:TechnicalDocumentReference")
    pcap = _documentos(cfs, "cac:LegalDocumentReference")
    adic = _documentos(cfs, "cac:AdditionalDocumentReference")
    gen = _generales(cfs)
    budget = "cac:BudgetAmount/cbc:"
    link = entry.find("atom:link", NS)
    return {
        "feed": feed,
        "zip": zipname,
        "entry_id": _txt(entry, "atom:id"),
        "url_licitacion": link.get("href", "") if link is not None else "",
        "updated_utc": _utc(_txt(entry, "atom:updated")),
        "folder_id": _txt(cfs, "cbc:ContractFolderID"),
        "estado": _txt(cfs, "cbce:ContractFolderStatusCode"),
        "estado_nombre": ESTADOS.get(
            _txt(cfs, "cbce:ContractFolderStatusCode"), ""),
        "fecha_publicacion": pub,
        "fecha_publicacion_origen": "DOC_CN" if f_cn else (
            "primer_aviso" if f_todas else ""),
        "avisos": ";".join(f"{t}:{f}" for t, f in avisos),
        "tipo_organo": tipo,
        "tipo_organo_nombre": TIPOS_ORGANO.get(tipo, ""),
        "actividad_organo": _txt(lcp, "cbc:ActivityCode"),
        "organo": _txt(party, "cac:PartyName/cbc:Name"),
        "dir3": ids.get("DIR3", ""),
        "nif": ids.get("NIF", ""),
        "id_plataforma": ids.get("ID_PLATAFORMA", ""),
        "ciudad": _txt(party, "cac:PostalAddress/cbc:CityName"),
        "cp": _txt(party, "cac:PostalAddress/cbc:PostalZone"),
        "jerarquia": " > ".join(cadena),
        "nuts": ";".join(dict.fromkeys(nuts)),
        "lugar": ";".join(dict.fromkeys(zonas)),
        "titulo": _txt(entry, "atom:title"),
        "resumen": _txt(entry, "atom:summary"),
        "objeto": _txt(pp, "cbc:Name"),
        "lotes": " | ".join(nombres_lotes),
        "tipo_contrato": _txt(pp, "cbc:TypeCode"),
        "subtipo_contrato": _txt(pp, "cbc:SubTypeCode"),
        "importe_estimado": _txt(pp, budget + "EstimatedOverallContractAmount"),
        "importe_total": _txt(pp, budget + "TotalAmount"),
        "importe_sin_iva": _txt(pp, budget + "TaxExclusiveAmount"),
        "cpv": ";".join(dict.fromkeys(cpv)),
        "cpv_lotes": ";".join(dict.fromkeys(cpv_lotes)),
        "procedimiento": _txt(cfs, "cac:TenderingProcess/cbc:ProcedureCode"),
        "ppt_nombre": ppt[0][0] if ppt else "",
        "ppt_url": ppt[0][1] if ppt else "",
        "pcap_nombre": pcap[0][0] if pcap else "",
        "pcap_url": pcap[0][1] if pcap else "",
        "docs_adicionales": " || ".join(f"{n} <{u}>" for n, u in adic),
        "docs_generales": " || ".join(f"{n} <{u}>" for n, u in gen),
    }


def clave_organo(entry: ET.Element) -> str:
    """Identifica el órgano: ID_PLATAFORMA, DIR3, NIF o nombre."""
    base = ("cace:ContractFolderStatus/cace:LocatedContractingParty/"
            "cac:Party/")
    ids = {}
    for pid in entry.findall(base + "cac:PartyIdentification/cbc:ID", NS):
        ids[pid.get("schemeName", "")] = (pid.text or "").strip()
    for esquema in ("ID_PLATAFORMA", "DIR3", "NIF"):
        if ids.get(esquema):
            return f"{esquema}:{ids[esquema]}"
    nombre = _txt(entry, base + "cac:PartyName/cbc:Name")
    return "NOMBRE:" + normalizar(nombre)


def preseleccion(entry: ET.Element) -> tuple[bool, bool]:
    """Indica si una entrada entra por CPV y/o por palabras del título.

    Args:
        entry: Nodo ``atom:entry``.

    Returns:
        Tupla (por_cpv, por_titulo).
    """
    cfs = entry.find("cace:ContractFolderStatus", NS)
    if cfs is None:
        return False, False
    cpvs = {(n.text or "").strip() for n in cfs.iter(
        "{%s}ItemClassificationCode" % NS["cbc"])}
    por_cpv = bool(cpvs & CPV_VV.keys())
    textos = [_txt(entry, "atom:title"),
              _txt(cfs, "cac:ProcurementProject/cbc:Name")]
    textos += _todos(cfs, "cac:ProcurementProjectLot/cac:ProcurementProject/"
                     "cbc:Name")
    norm = re.sub(r"\s+", " ", normalizar(" ".join(textos)))
    por_titulo = bool(RE_SELECCION.search(norm))
    return por_cpv, por_titulo


def parsear_zip(feed: str, nombre: str) -> dict:
    """Recorre un zip de sindicación y deduplica sus entradas.

    Args:
        feed: Conjunto de sindicación.
        nombre: Nombre del fichero zip.

    Returns:
        Diccionario con estadísticas, la última marca por clave y el
        registro completo de las entradas preseleccionadas.
    """
    ruta = DIR_ZIPS / feed / nombre
    ultimas: dict[str, list] = {}
    stats = Counter()
    borradas: list[tuple[str, str]] = []
    entry_ids: dict[str, set] = defaultdict(set)
    candidatas: set[str] = set()
    with zipfile.ZipFile(ruta) as z:
        miembros = [m for m in z.namelist() if m.endswith(".atom")]
        stats["ficheros_atom"] = len(miembros)
        for m in miembros:
            with z.open(m) as fh:
                for _, el in ET.iterparse(fh, events=("end",)):
                    if el.tag == T_DELETED:
                        borradas.append((el.get("ref", ""),
                                         el.get("when", "")))
                        stats["borradas"] += 1
                        el.clear()
                        continue
                    if el.tag != T_ENTRY:
                        continue
                    stats["entradas"] += 1
                    folder = _txt(el, "cace:ContractFolderStatus/"
                                  "cbc:ContractFolderID")
                    clave = f"{folder}||{clave_organo(el)}"
                    upd = _utc(_txt(el, "atom:updated"))
                    eid = _txt(el, "atom:id")
                    entry_ids[clave].add(eid)
                    previo = ultimas.get(clave)
                    if previo is None or upd > previo[0]:
                        por_cpv, por_tit = preseleccion(el)
                        reg = None
                        if por_cpv or por_tit:
                            candidatas.add(clave)
                            reg = registro_completo(el, feed, nombre)
                            reg["sel_cpv"] = por_cpv
                            reg["sel_titulo"] = por_tit
                        ultimas[clave] = [upd, reg]
                    el.clear()
    return {
        "feed": feed,
        "zip": nombre,
        "stats": dict(stats),
        "ultimas": ultimas,
        "borradas": borradas,
        "n_claves_varios_ids": sum(len(v) > 1 for v in entry_ids.values()),
        # entry ids de las claves preseleccionadas en alguna versión
        "ids_preseleccion": {k: sorted(entry_ids[k]) for k in candidatas},
        "n_claves": len(ultimas),
    }


def _parsear_y_guardar(args: tuple[str, str]) -> str:
    """Envoltorio para el pool: parsea un zip y guarda su caché."""
    feed, nombre = args
    destino = DIR_CACHE / "parseo" / f"{feed}_{nombre}.json.gz"
    if destino.exists():
        return f"{nombre}: en caché"
    res = parsear_zip(feed, nombre)
    tmp = destino.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    tmp.replace(destino)
    return f"{nombre}: {res['stats']}"


def etapa_parseo(procesos: int = 8) -> None:
    """Parsea en paralelo todos los zips disponibles."""
    (DIR_CACHE / "parseo").mkdir(parents=True, exist_ok=True)
    tareas = [(f, n) for f, n in ZIPS
              if (DIR_ZIPS / f / n).exists()]
    faltan = [n for f, n in ZIPS if not (DIR_ZIPS / f / n).exists()]
    if faltan:
        log.warning("faltan %d zips: %s", len(faltan), faltan)
    with ProcessPoolExecutor(procesos) as pool:
        for msg in tqdm(pool.map(_parsear_y_guardar, tareas),
                        total=len(tareas), desc="parseo"):
            log.info("parseo %s", msg)


def consolidar() -> tuple[list[dict], dict]:
    """Une las cachés de parseo y aplica la deduplicación global.

    Regla: por cada clave (ContractFolderID, órgano) se conserva la
    entrada con ``updated`` mayor en todos los ficheros; un expediente
    queda seleccionado solo si esa última versión entra por CPV o por
    título.

    Returns:
        Lista de registros seleccionados y estadísticas de volumen.
    """
    ultimas: dict[str, list] = {}
    stats = {"zips": 0, "ficheros_atom": 0, "entradas": 0, "borradas": 0}
    por_feed = Counter()
    claves_feed: dict[str, set] = defaultdict(set)
    multi_id = 0
    ids_sel: dict[str, set] = defaultdict(set)
    borradas = {}
    cachés = sorted((DIR_CACHE / "parseo").glob("*.json.gz"))
    for ruta in tqdm(cachés, desc="consolidar"):
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            res = json.load(f)
        stats["zips"] += 1
        for k in ("ficheros_atom", "entradas", "borradas"):
            stats[k] += res["stats"].get(k, 0)
        por_feed[res["feed"]] += res["stats"].get("entradas", 0)
        multi_id += res.get("n_claves_varios_ids", 0)
        for clave, ids in res.get("ids_preseleccion", {}).items():
            ids_sel[clave].update(ids)
        for ref, when in res["borradas"]:
            borradas[ref] = max(borradas.get(ref, ""), _utc(when))
        for clave, (upd, reg) in res["ultimas"].items():
            claves_feed[res["feed"]].add(clave)
            previo = ultimas.get(clave)
            if previo is None or upd > previo[0]:
                ultimas[clave] = [upd, reg]
    stats["entradas_por_feed"] = dict(por_feed)
    stats["expedientes_unicos"] = len(ultimas)
    stats["expedientes_por_feed"] = {k: len(v)
                                     for k, v in claves_feed.items()}
    stats["claves_en_ambos_feeds"] = len(
        claves_feed.get("643", set()) & claves_feed.get("1044", set()))
    stats["claves_con_varios_entry_id_en_un_zip"] = multi_id
    seleccion = []
    for clave, (upd, reg) in ultimas.items():
        if reg is None:
            continue
        reg = dict(reg)
        reg["clave"] = clave
        reg["n_entry_ids"] = len(ids_sel.get(clave, {reg["entry_id"]}))
        when = borradas.get(reg["entry_id"], "")
        reg["borrada_despues"] = bool(when and when > upd)
        seleccion.append(reg)
    return seleccion, stats


# --------------------------------------------------------------------
# selección y nivel A
# --------------------------------------------------------------------

def texto_nivel_a(reg: dict) -> str:
    """Texto del nivel A: título, objeto, lotes y resumen."""
    return " ".join([reg["titulo"], reg["objeto"], reg["lotes"],
                     reg["resumen"]])


def es_negada(frase: str, norm_previo: str) -> bool:
    """Indica si una mención aparece en una cláusula que la excluye.

    Args:
        frase: Frase literal que contiene la coincidencia.
        norm_previo: Texto normalizado de los 15 caracteres anteriores a
            la coincidencia.

    Returns:
        True si la frase contiene una exclusión explícita
        (``RE_NEGACION_FUERTE``) o si una negación simple precede a la
        coincidencia (``RE_NEGACION_DEBIL``).
    """
    return bool(RE_NEGACION_FUERTE.search(normalizar(frase))
                or RE_NEGACION_DEBIL.search(norm_previo))


def clasificar(texto: str) -> dict[str, dict]:
    """Aplica las familias de capacidad a un texto.

    Args:
        texto: Texto original (sin normalizar).

    Returns:
        Por familia: ``hay`` (alguna mención), ``afirmativa`` (alguna
        mención fuera de una cláusula de exclusión), ``frase`` (primera
        mención afirmativa que no está en un índice con puntos guía),
        ``frase_negada`` (primera mención excluida) y ``terminos``.
    """
    norm = normalizar(texto)
    salida = {}
    for fam, patron in FAMILIAS.items():
        validas = []
        for cand in patron.finditer(norm):
            if cand.group(0) == "ia":
                # «ia» solo vale si en el original va en mayúsculas
                orig = texto[cand.start():cand.end()] \
                    if len(norm) == len(texto) else ""
                if orig != "IA":
                    continue
            validas.append(cand)
        res = {"hay": bool(validas), "afirmativa": False, "frase": "",
               "frase_negada": "",
               "terminos": ";".join(sorted({re.sub(r"\s+", " ", v.group(0))
                                            for v in validas}))}
        indice = ""
        for v in validas:
            frase = frase_literal(texto, norm, v)
            if es_negada(frase, norm[max(0, v.start() - 15):v.start()]):
                res["frase_negada"] = res["frase_negada"] or frase
                continue
            res["afirmativa"] = True
            if re.search(r"\.{5,}", frase):
                indice = indice or frase
            elif not res["frase"]:
                res["frase"] = frase
            if res["frase"] and res["frase_negada"]:
                break
        res["frase"] = res["frase"] or indice
        salida[fam] = res
    return salida


def frase_literal(texto: str, norm: str, m: re.Match) -> str:
    """Recorta la frase original que contiene una coincidencia.

    Args:
        texto: Texto original.
        norm: Texto normalizado.
        m: Coincidencia sobre el texto normalizado.

    Returns:
        Frase literal, con espacios colapsados, de 400 caracteres como
        máximo.
    """
    fuente = texto if len(norm) == len(texto) else norm
    # se toma como frontera un punto o punto y coma seguido de espacio,
    # o una línea en blanco, a 250 caracteres como mucho
    ini = max(0, m.start() - 250)
    antes = list(RE_FRONTERA.finditer(fuente, ini, m.start()))
    if antes:
        ini = antes[-1].end()
    despues = RE_FRONTERA.search(fuente, m.end(), m.end() + 250)
    fin = despues.start() + 1 if despues else m.end() + 250
    return re.sub(r"\s+", " ", fuente[ini:fin]).strip()[:500]


# nombres de autoridad local para el conjunto 1044, que no trae
# ContractingPartyTypeCode; calibrado contra el código 3 del 643
RE_LOCAL_NOMBRE = re.compile(
    r"\b(?:ayuntamiento|ajuntament|concello|udala|udaletxea|diputacio"
    r"|diputacion|consell comarcal|consell insular|consejo insular"
    r"|cabildo|mancomunidad|mancomunitat|comarca|concejo|junta vecinal"
    r"|entidad local menor|entitat municipal|alcaldia|alcalde|alcaldesa"
    r"|pleno|junta de gobierno local|concejal|regidor"
    r"|area metropolitana|batzar)"
)
RE_NO_LOCAL_NOMBRE = re.compile(
    r"\b(?:s\.?a\.?u?\.?|s\.?l\.?u?\.?|sociedad|societat|empresa"
    r"|fundacion|fundacio|consorcio|consorci|organismo autonomo"
    r"|organisme autonom|patronato|patronat|instituto municipal"
    r"|institut municipal|gerencia|agencia|entidad publica empresarial)\b"
)


def tipo_organo_efectivo(reg: dict) -> tuple[str, str]:
    """Da el tipo de órgano: el código si existe y, si no, el inferido.

    El conjunto 1044 no publica ContractingPartyTypeCode. Se infiere
    «autoridad local» si el código DIR3 empieza por L0, L1 o LO
    (entidades locales; LA0 son dependientes) o si el nombre del órgano
    cumple ``RE_LOCAL_NOMBRE`` sin cumplir ``RE_NO_LOCAL_NOMBRE``. Sobre
    las 19.940 entradas del zip 643 de octubre de 2026, la regla de
    nombre reproduce el código 3 con precisión 0,996 (8.236 de 8.266) y
    exhaustividad 0,929 (8.236 de 8.870).

    Args:
        reg: Registro del expediente.

    Returns:
        Tupla (tipo, origen); tipo es el código CODICE, «3» inferido o
        «sin_codigo»; origen indica de dónde sale.
    """
    if reg["tipo_organo"]:
        return reg["tipo_organo"], "codigo"
    dir3 = reg["dir3"].upper()
    if re.match(r"L(?:0|1|O)", dir3):
        return "3", "inferido_dir3"
    nombre = normalizar(reg["organo"])
    if RE_LOCAL_NOMBRE.search(nombre) and not \
            RE_NO_LOCAL_NOMBRE.search(nombre):
        return "3", "inferido_nombre"
    return "sin_codigo", "sin_codigo"


def es_falso_positivo(reg: dict) -> str:
    """Devuelve el motivo de exclusión de un expediente, o ''.

    Se excluye si el título cumple ``RE_EXCLUSION`` o, en la vía solo
    CPV, ``RE_EXCLUSION_CPV`` sin palabra de seguridad
    (``RE_SEGURIDAD``), salvo que el título nombre la
    videovigilancia de forma explícita (``RE_FUERTE``). En la vía solo
    CPV se excluye además el expediente cuyo CPV principal (el primero)
    no es de videovigilancia y cuyo título no da ningún indicio
    (``RE_INDICIO``): son, sobre todo, contratos basados en acuerdos
    marco de catálogo que enumeran quince o más CPV.

    Args:
        reg: Registro del expediente.

    Returns:
        Motivo de exclusión documentado, o cadena vacía.
    """
    norm = re.sub(r"\s+", " ",
                  normalizar(" ".join([reg["titulo"], reg["objeto"]])))
    if RE_FUERTE.search(norm):
        return ""
    m = RE_EXCLUSION.search(norm)
    if m:
        return f"titulo_excluido:{m.group(0)}"
    m = RE_EXCLUSION_LOTES.search(normalizar(reg["lotes"]))
    if m and not RE_SELECCION.search(norm):
        return f"lote_excluido:{m.group(0)}"
    if not reg["sel_titulo"]:
        m = RE_EXCLUSION_CPV.search(norm)
        if m and not RE_SEGURIDAD.search(norm):
            return f"solo_cpv_excluido:{m.group(0)}"
        cpvs = (reg["cpv"] or reg["cpv_lotes"]).split(";")
        if cpvs[0] not in CPV_VV and not RE_INDICIO.search(norm):
            return "solo_cpv_secundario_sin_indicio"
    return ""


# --------------------------------------------------------------------
# etapa 3: pliegos técnicos
# --------------------------------------------------------------------

class Limitador:
    """Garantiza como mucho una petición por intervalo, entre hilos."""

    def __init__(self, intervalo: float = 1.0) -> None:
        self.intervalo = intervalo
        self.cerrojo = threading.Lock()
        self.ultimo = 0.0

    def esperar(self) -> None:
        """Bloquea hasta que se puede lanzar la siguiente petición."""
        with self.cerrojo:
            espera = self.ultimo + self.intervalo - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            self.ultimo = time.monotonic()


LIMITADOR = Limitador(1.0)
CERROJO_SOFFICE = threading.Lock()


def reparar_url(url: str) -> str:
    """Corrige defectos de origen en las URL de documentos.

    Algunas URL de la plataforma vasca traen incrustado el resto de una
    concatenación SQL (``' || '``); se elimina, y los espacios se
    codifican.

    Args:
        url: URL tal como viene en la sindicación.

    Returns:
        URL corregida.
    """
    return url.replace("' || '", "").strip().replace(" ", "%20")


def elegir_pliego(reg: dict) -> tuple[str, str, str]:
    """Elige el documento del pliego técnico de un expediente.

    Se usa la referencia técnica (TechnicalDocumentReference); si falta,
    el primer documento adicional o general cuyo nombre indica pliego
    de prescripciones técnicas.

    Returns:
        Tupla (origen, nombre, url).
    """
    if reg["ppt_url"]:
        return "TechnicalDocumentReference", reg["ppt_nombre"], \
            reparar_url(reg["ppt_url"])
    for campo in ("docs_adicionales", "docs_generales"):
        for m in re.finditer(r"(?:^| \|\| )(.*?) <([^>]*)>", reg[campo]):
            if RE_PPT_NOMBRE.search(normalizar(m.group(1))):
                return campo, m.group(1), reparar_url(m.group(2))
    return "", "", ""


def _texto_pdf(ruta: Path) -> tuple[str, str]:
    """Extrae el texto de un PDF con pdftotext y, si falla, con mutool.

    Args:
        ruta: Fichero PDF.

    Returns:
        Tupla (estado, texto).
    """
    try:
        r = subprocess.run(["pdftotext", "-q", str(ruta), "-"],
                           capture_output=True, timeout=300)
        texto = r.stdout.decode("utf-8", "replace")
        codigo = r.returncode
    except subprocess.TimeoutExpired:
        texto, codigo = "", "timeout"
    estado = "ok_pdf"
    if codigo != 0 and not texto.strip():
        # se intenta reparar la tabla de referencias con mutool
        try:
            r = subprocess.run(["mutool", "draw", "-q", "-F", "txt", "-o",
                                "-", str(ruta)], capture_output=True,
                               timeout=300)
            texto = r.stdout.decode("utf-8", "replace")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            texto = ""
        estado = "ok_pdf_reparado"
        if not texto.strip():
            return f"pdf_danado_{codigo}", ""
    if len(re.sub(r"\s", "", texto)) < 200:
        return "pdf_sin_texto", texto
    return estado, texto


def _texto_soffice(ruta: Path, ext: str) -> tuple[str, str]:
    """Convierte un .doc o .rtf a texto con LibreOffice sin interfaz.

    Args:
        ruta: Fichero de origen.
        ext: Extensión con la que se presenta a LibreOffice.

    Returns:
        Tupla (estado, texto).
    """
    tmp = DIR_PLIEGOS / "_conv"
    tmp.mkdir(exist_ok=True)
    copia = tmp / f"{ruta.stem}.{ext}"
    shutil.copy(ruta, copia)
    try:
        # libreoffice no admite conversiones simultáneas con un perfil
        with CERROJO_SOFFICE:
            subprocess.run(["soffice", "--headless", "--convert-to",
                            "txt:Text", "--outdir", str(tmp), str(copia)],
                           capture_output=True, timeout=300)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return f"{ext}_sin_convertir", ""
    salida = tmp / f"{ruta.stem}.txt"
    if not salida.exists():
        return f"{ext}_sin_convertir", ""
    texto = salida.read_text(encoding="utf-8", errors="replace")
    return f"ok_{ext}", texto


def texto_de_fichero(ruta: Path) -> tuple[str, str]:
    """Extrae texto de un PDF, DOC, DOCX, ODT, RTF o ZIP descargado.

    Args:
        ruta: Fichero descargado.

    Returns:
        Tupla (estado, texto).
    """
    datos = ruta.read_bytes()
    cabecera = datos[:8]
    if cabecera.startswith(b"%PDF"):
        estado, texto = _texto_pdf(ruta)
        if estado.startswith("ok") and b"%%EOF" not in datos[-4096:]:
            estado += "_truncado"
        return estado, texto
    if cabecera.startswith(b"\xd0\xcf\x11\xe0"):
        return _texto_soffice(ruta, "doc")
    if cabecera.startswith(b"{\\rtf"):
        return _texto_soffice(ruta, "rtf")
    if cabecera.startswith(b"PK"):
        try:
            with zipfile.ZipFile(ruta) as z:
                nombres = z.namelist()
                for interno in ("word/document.xml", "content.xml"):
                    if interno in nombres:
                        xml = z.read(interno).decode("utf-8", "replace")
                        xml = re.sub(r"</w:p>|</text:p>", "\n", xml)
                        return "ok_ofimatica", re.sub(r"<[^>]+>", "", xml)
                # zip de documentos: se concatenan los pdf que contiene
                textos = []
                for i, interno in enumerate(nombres):
                    if interno.lower().endswith(".pdf"):
                        # nombre único: varios hilos extraen a la vez
                        tmp = DIR_PLIEGOS / "_conv" / f"{ruta.stem}_{i}.pdf"
                        tmp.parent.mkdir(exist_ok=True)
                        tmp.write_bytes(z.read(interno))
                        est, txt = _texto_pdf(tmp)
                        if est.startswith("ok"):
                            textos.append(txt)
                if textos:
                    return "ok_zip_pdf", "\n\n".join(textos)
                return "zip_sin_texto", ""
        except zipfile.BadZipFile:
            return "zip_danado", ""
    if b"<html" in datos[:2000].lower():
        return "html_no_documento", ""
    return "formato_desconocido", ""


def bajar_pliego(url: str, intentos: int = 3) -> tuple[str, str]:
    """Descarga (con caché) un pliego y devuelve su estado y ruta.

    Un PDF sin marca final ``%%EOF`` se considera truncado y se vuelve a
    pedir, igual que un error de red o un 5xx, hasta ``intentos`` veces
    en total.

    Args:
        url: URL del documento.
        intentos: Número máximo de descargas del mismo documento.

    Returns:
        Tupla (estado_http, ruta_local).
    """
    h = hashlib.sha1(url.encode()).hexdigest()
    destino = DIR_PLIEGOS / f"{h}.bin"
    meta = DIR_PLIEGOS / f"{h}.json"
    previos = 0
    if meta.exists():
        info = json.loads(meta.read_text())
        previos = info[3] if len(info) > 3 else 1
        completo = not (destino.exists() and destino.read_bytes()[:4]
                        == b"%PDF" and b"%%EOF"
                        not in destino.read_bytes()[-4096:])
        # se reintenta un pdf truncado, un error de red o un 5xx
        reintentar = (info[0] == "200" and not completo) or \
            info[0].startswith(("error_", "http_5"))
        if not reintentar or previos >= intentos:
            return info[0], info[1]
    LIMITADOR.esperar()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=180) as r, \
                destino.open("wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
            estado = str(r.status)
    except urllib.error.HTTPError as e:
        estado = f"http_{e.code}"
    except (urllib.error.URLError, TimeoutError, OSError,
            http.client.HTTPException) as e:
        estado = f"error_{type(e).__name__}"
    ruta = str(destino) if estado == "200" else ""
    meta.write_text(json.dumps([estado, ruta, url, previos + 1]))
    return estado, ruta


def procesar_pliego(reg: dict) -> dict:
    """Envoltorio que registra cualquier excepción como estado.

    Args:
        reg: Registro seleccionado.

    Returns:
        Campos del nivel B para el registro.
    """
    try:
        return _procesar_pliego(reg)
    except Exception as e:  # noqa: BLE001
        log.exception("pliego %s", reg.get("clave"))
        return {"estado_pliego": f"excepcion_{type(e).__name__}"}


def _procesar_pliego(reg: dict) -> dict:
    """Descarga y lee el pliego técnico de un expediente.

    Args:
        reg: Registro seleccionado.

    Returns:
        Campos del nivel B para el registro.
    """
    origen, nombre, url = elegir_pliego(reg)
    salida = {"pliego_origen": origen, "pliego_nombre": nombre,
              "pliego_url": url}
    if not url:
        salida["estado_pliego"] = "sin_url_pliego"
        return salida
    estado, ruta = bajar_pliego(url)
    if estado != "200":
        salida["estado_pliego"] = estado
        return salida
    est, texto = texto_de_fichero(Path(ruta))
    salida["estado_pliego"] = est
    salida["pliego_sha1"] = hashlib.sha1(Path(ruta).read_bytes()).hexdigest()
    salida["pliego_caracteres"] = len(texto)
    if est.startswith("ok"):
        txt = Path(ruta).with_suffix(".txt")
        txt.write_text(texto, encoding="utf-8")
        salida["pliego_txt"] = txt.name
    return salida


def muestra_nivel_b(seleccion: list[dict]) -> list[dict]:
    """Elige los expedientes cuyo pliego se descarga.

    Si la selección no supera ``LIMITE_CENSO``, se descargan todos. Si
    lo supera, todos los de autoridades locales (código 3) publicados
    en 2025 y 2026, y una muestra aleatoria con semilla fija del resto
    (un tercio, con un mínimo de 300).

    Args:
        seleccion: Expedientes seleccionados en el periodo.

    Returns:
        Lista de registros con la marca ``muestra_b``.
    """
    if len(seleccion) <= LIMITE_CENSO:
        for reg in seleccion:
            reg["muestra_b"] = "censo"
        return seleccion
    obligatorios, resto = [], []
    for reg in seleccion:
        if reg["tipo_efectivo"] == "3" and reg["fecha_publicacion"] >= \
                "2025-01-01":
            reg["muestra_b"] = "local_2025_2026"
            obligatorios.append(reg)
        else:
            resto.append(reg)
    rng = random.Random(SEMILLA)
    resto.sort(key=lambda r: r["clave"])
    n = min(len(resto), max(300, len(resto) // 3))
    elegidos = rng.sample(resto, n)
    for reg in elegidos:
        reg["muestra_b"] = "aleatoria_resto"
    return obligatorios + elegidos


def etapa_pliegos(seleccion: list[dict], hilos: int = 4) -> None:
    """Descarga y extrae los pliegos de la muestra del nivel B."""
    DIR_PLIEGOS.mkdir(parents=True, exist_ok=True)
    muestra = [r for r in seleccion if r.get("muestra_b")]
    with ThreadPoolExecutor(hilos) as pool:
        resultados = list(tqdm(pool.map(procesar_pliego, muestra),
                               total=len(muestra), desc="pliegos"))
    for reg, res in zip(muestra, resultados):
        reg.update(res)
    estados = Counter(r["estado_pliego"] for r in muestra)
    log.info("estados de los pliegos: %s", dict(estados))


# --------------------------------------------------------------------
# etapa 4: clasificación y salidas
# --------------------------------------------------------------------

FAMS = ["facial", "facial_estricto", "apariencia", "apariencia_estricta",
        "analitica_ia", "lpr"]
# indicadores agregados en las tablas: mención y mención afirmativa
INDICADORES = ([x for f in FAMS for x in (f, f"{f}_afirm")]
               + ["facial_estricto_solo_negada",
                  "facial_estricto_clausula_exclusion", "ia_alguna",
                  "cualquiera"])


def marcar_niveles(reg: dict) -> None:
    """Añade al registro las banderas de los niveles A y B.

    Para cada familia se guardan dos banderas: la mención (``a_x``,
    ``b_x``) y la mención afirmativa (``a_x_afirm``, ``b_x_afirm``), que
    descarta las cláusulas de exclusión. Los agregados ``ia_alguna`` y
    ``cualquiera`` se calculan sobre las menciones afirmativas de las
    familias estrictas.

    Args:
        reg: Registro seleccionado; se modifica en el sitio.
    """
    for nivel in ("a", "b"):
        if nivel == "a":
            texto = texto_nivel_a(reg)
        elif reg.get("pliego_txt"):
            texto = (DIR_PLIEGOS / reg["pliego_txt"]).read_text(
                encoding="utf-8")
        else:
            for ind in INDICADORES:
                reg[f"b_{ind}"] = ""
            return
        res = clasificar(texto)
        for fam in FAMS:
            reg[f"{nivel}_{fam}"] = int(res[fam]["hay"])
            reg[f"{nivel}_{fam}_afirm"] = int(res[fam]["afirmativa"])
            reg[f"{nivel}_terminos_{fam}"] = res[fam]["terminos"]
            if nivel == "b":
                reg[f"b_frase_{fam}"] = res[fam]["frase"]
                reg[f"b_frase_negada_{fam}"] = res[fam]["frase_negada"]
        reg[f"{nivel}_ia_alguna"] = int(
            res["facial_estricto"]["afirmativa"]
            or res["apariencia_estricta"]["afirmativa"]
            or res["analitica_ia"]["afirmativa"])
        reg[f"{nivel}_cualquiera"] = int(reg[f"{nivel}_ia_alguna"]
                                         or res["lpr"]["afirmativa"])
        reg[f"{nivel}_facial_estricto_solo_negada"] = int(
            res["facial_estricto"]["hay"]
            and not res["facial_estricto"]["afirmativa"])
        reg[f"{nivel}_facial_estricto_clausula_exclusion"] = int(
            bool(res["facial_estricto"]["frase_negada"]))


def _pct(n: int, d: int) -> str:
    """Porcentaje con un decimal, o vacío si no hay denominador."""
    return f"{100 * n / d:.1f}" if d else ""


def conteos(filas: list[dict], clave) -> list[dict]:
    """Agrega recuentos por una clave con ambos niveles.

    Args:
        filas: Registros seleccionados del periodo.
        clave: Función que da el grupo de cada registro.

    Returns:
        Filas de recuento con denominadores explícitos.
    """
    grupos: dict[str, list[dict]] = defaultdict(list)
    for r in filas:
        grupos[clave(r)].append(r)
    salida = []
    for g in sorted(grupos):
        rs = grupos[g]
        con_b = [r for r in rs if r.get("b_facial", "") != ""]
        fila = {"grupo": g, "n_licitaciones": len(rs),
                "n_locales": sum(r["tipo_efectivo"] == "3" for r in rs),
                "n_muestra_b": sum(bool(r.get("muestra_b")) for r in rs),
                "n_con_texto_b": len(con_b)}
        for fam in INDICADORES:
            na = sum(int(r[f"a_{fam}"]) for r in rs)
            nb = sum(int(r[f"b_{fam}"]) for r in con_b)
            fila[f"a_{fam}"] = na
            fila[f"a_{fam}_pct"] = _pct(na, len(rs))
            fila[f"b_{fam}"] = nb
            fila[f"b_{fam}_pct"] = _pct(nb, len(con_b))
        salida.append(fila)
    return salida


def conteo_capacidades(filas: list[dict]) -> list[dict]:
    """Tabla larga: capacidad x nivel x universo, con denominador.

    Args:
        filas: Registros seleccionados del periodo.

    Returns:
        Filas (universo, capacidad, nivel, n, denominador, pct).
    """
    universos = {
        "todas": filas,
        "autoridad_local": [r for r in filas if r["tipo_efectivo"] == "3"],
        "autoridad_local_2025_2026": [
            r for r in filas if r["tipo_efectivo"] == "3"
            and r["fecha_publicacion"] >= "2025-01-01"],
        "resto_muestra_aleatoria": [
            r for r in filas if r.get("muestra_b") == "aleatoria_resto"],
    }
    # documentos distintos: cada pliego cuenta una vez (el nivel B se
    # mide sobre documentos, no sobre expedientes)
    vistos, distintos = set(), []
    for r in filas:
        h = r.get("pliego_sha1")
        if h and h not in vistos:
            vistos.add(h)
            distintos.append(r)
    universos["documentos_distintos"] = distintos
    salida = []
    for nombre, rs in universos.items():
        if not rs:
            continue
        con_b = [r for r in rs if r.get("b_facial", "") != ""]
        for fam in INDICADORES:
            na = sum(int(r[f"a_{fam}"]) for r in rs)
            nb = sum(int(r[f"b_{fam}"]) for r in con_b)
            salida.append({"universo": nombre, "capacidad": fam,
                           "nivel": "A", "n": na, "denominador": len(rs),
                           "pct": _pct(na, len(rs))})
            salida.append({"universo": nombre, "capacidad": fam,
                           "nivel": "B", "n": nb,
                           "denominador": len(con_b),
                           "pct": _pct(nb, len(con_b))})
    return salida


CAMPOS_BASE = [
    "clave", "feed", "folder_id", "entry_id", "url_licitacion",
    "updated_utc", "fecha_publicacion", "fecha_publicacion_origen",
    "estado", "estado_nombre", "tipo_organo", "tipo_organo_nombre",
    "tipo_efectivo", "tipo_origen",
    "organo", "dir3", "nif", "ciudad", "cp", "jerarquia", "nuts", "lugar",
    "titulo", "lotes", "tipo_contrato", "importe_estimado",
    "importe_sin_iva", "importe_total", "cpv", "cpv_lotes",
    "procedimiento", "sel_cpv", "sel_titulo", "via_seleccion",
    "borrada_despues", "en_ambos_feeds", "n_entry_ids", "ppt_nombre",
    "ppt_url",
    "pcap_nombre", "pcap_url",
    "zip",
]


def etapa_salidas(seleccion: list[dict], stats: dict,
                  excluidas: list[dict]) -> None:
    """Escribe los CSV de detalle y de recuento.

    Args:
        seleccion: Expedientes seleccionados del periodo.
        stats: Estadísticas de volumen.
        excluidas: Expedientes descartados como falsos positivos.
    """
    DIR_SALIDAS.mkdir(parents=True, exist_ok=True)
    for reg in tqdm(seleccion, desc="clasificar"):
        marcar_niveles(reg)
    a_cols = [f"a_{f}" for f in INDICADORES]
    b_cols = [f"b_{f}" for f in INDICADORES]
    a_terminos = [f"a_terminos_{f}" for f in FAMS]
    b_terminos = [f"b_terminos_{f}" for f in FAMS]
    frases = [f"b_frase{n}_{f}" for f in FAMS for n in ("", "_negada")]
    # se cuenta cuántos expedientes comparten el mismo documento
    usos = Counter(r.get("pliego_sha1") for r in seleccion
                   if r.get("pliego_sha1"))
    for r in seleccion:
        r["n_mismo_pliego"] = usos.get(r.get("pliego_sha1"), "")
    pliego = ["muestra_b", "pliego_origen", "pliego_nombre", "pliego_url",
              "estado_pliego", "pliego_caracteres", "pliego_txt",
              "pliego_sha1", "n_mismo_pliego"]
    campos = (CAMPOS_BASE + a_cols + a_terminos + pliego + b_cols
              + b_terminos + frases)
    seleccion.sort(key=lambda r: (r["fecha_publicacion"], r["clave"]))
    escribir_csv(DIR_SALIDAS / "licitaciones_videovigilancia.csv",
                 seleccion, campos)
    escribir_csv(DIR_SALIDAS / "excluidas.csv", excluidas,
                 CAMPOS_BASE + ["motivo_exclusion"])
    filas_mes = conteos(seleccion, lambda r: r["fecha_publicacion"][:7])
    escribir_csv(DIR_SALIDAS / "conteos_mensuales.csv", filas_mes,
                 list(filas_mes[0]))
    filas_tipo = conteos(seleccion, etiqueta_tipo)
    escribir_csv(DIR_SALIDAS / "conteos_tipo_organo.csv", filas_tipo,
                 list(filas_tipo[0]))
    filas_anio = conteos(seleccion, lambda r: r["fecha_publicacion"][:4])
    escribir_csv(DIR_SALIDAS / "conteos_anuales.csv", filas_anio,
                 list(filas_anio[0]))
    escribir_csv(DIR_SALIDAS / "conteos_capacidad_nivel.csv",
                 conteo_capacidades(seleccion),
                 ["universo", "capacidad", "nivel", "n", "denominador",
                  "pct"])
    ejemplos = [r for r in seleccion
                if r.get("b_facial_estricto") == 1
                or r.get("b_apariencia_estricta") == 1]
    escribir_csv(DIR_SALIDAS / "ejemplos_facial_apariencia.csv", ejemplos,
                 ["fecha_publicacion", "organo", "tipo_efectivo",
                  "tipo_origen", "folder_id", "url_licitacion", "pliego_url",
                  "b_facial_estricto", "b_facial_estricto_afirm",
                  "b_terminos_facial_estricto", "b_frase_facial_estricto",
                  "b_frase_negada_facial_estricto",
                  "b_apariencia_estricta", "b_apariencia_estricta_afirm",
                  "b_terminos_apariencia_estricta",
                  "b_frase_apariencia_estricta",
                  "b_frase_negada_apariencia_estricta"])
    pliegos = [r for r in seleccion if r.get("muestra_b")]
    escribir_csv(DIR_SALIDAS / "estado_pliegos.csv", pliegos,
                 ["clave", "folder_id", "organo", "muestra_b",
                  "pliego_origen", "pliego_nombre", "pliego_url",
                  "estado_pliego", "pliego_caracteres"])
    with (DIR_SALIDAS / "volumenes.json").open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    log.info("se guarda volumenes.json")


def etiqueta_tipo(reg: dict) -> str:
    """Etiqueta de grupo para el recuento por tipo de órgano."""
    tipo, origen = reg["tipo_efectivo"], reg["tipo_origen"]
    if tipo == "sin_codigo":
        return "99 sin código (1044, no inferido local)"
    nombre = TIPOS_ORGANO.get(tipo, tipo)
    sufijo = "" if origen == "codigo" else f" (1044, {origen})"
    return f"{int(tipo):02d} {nombre}{sufijo}"


def preparar_seleccion(seleccion: list[dict]) -> tuple[list, list, dict]:
    """Filtra por periodo y separa los falsos positivos evidentes.

    Args:
        seleccion: Expedientes preseleccionados tras deduplicar.

    Returns:
        Seleccionados del periodo, excluidos y recuentos de la regla.
    """
    en_periodo, excluidas = [], []
    cuentas = Counter()
    for reg in seleccion:
        fecha = reg["fecha_publicacion"] or reg["updated_utc"][:10]
        if not reg["fecha_publicacion"]:
            reg["fecha_publicacion"] = fecha
            reg["fecha_publicacion_origen"] = "updated"
        if not FECHA_INI <= fecha <= FECHA_FIN:
            cuentas["fuera_de_periodo"] += 1
            continue
        reg["tipo_efectivo"], reg["tipo_origen"] = \
            tipo_organo_efectivo(reg)
        reg["via_seleccion"] = ("ambos" if reg["sel_cpv"] and
                                reg["sel_titulo"] else
                                "cpv" if reg["sel_cpv"] else "titulo")
        motivo = es_falso_positivo(reg)
        if motivo:
            reg["motivo_exclusion"] = motivo
            excluidas.append(reg)
            cuentas["excluidas_" + motivo] += 1
            continue
        cuentas["via_" + reg["via_seleccion"]] += 1
        en_periodo.append(reg)
    # se marcan los expedientes cuyo identificador aparece en ambos feeds
    feeds_por_id: dict[str, set] = defaultdict(set)
    for reg in en_periodo:
        feeds_por_id[normalizar(reg["folder_id"]).strip()].add(reg["feed"])
    for reg in en_periodo:
        ident = normalizar(reg["folder_id"]).strip()
        reg["en_ambos_feeds"] = int(len(feeds_por_id[ident]) > 1)
    cuentas["folder_id_en_ambos_feeds"] = sum(
        len(v) > 1 for v in feeds_por_id.values())
    cuentas["seleccionadas"] = len(en_periodo)
    return en_periodo, excluidas, dict(cuentas)


def main() -> None:
    """Ejecuta las etapas pedidas en orden."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--etapa", default="todo",
                   choices=["todo", "zips", "parseo", "pliegos",
                            "salidas"])
    p.add_argument("--procesos", type=int, default=8)
    p.add_argument("--hilos", type=int, default=4)
    args = p.parse_args()
    configurar_log()
    if args.etapa in ("todo", "zips"):
        etapa_zips()
    if args.etapa in ("todo", "parseo"):
        etapa_parseo(args.procesos)
    if args.etapa in ("todo", "pliegos", "salidas"):
        seleccion, stats = consolidar()
        sel, excl, reglas = preparar_seleccion(seleccion)
        stats["regla_seleccion"] = reglas
        log.info("selección: %s", reglas)
        muestra_nivel_b(sel)
        etapa_pliegos(sel, args.hilos)
        etapa_salidas(sel, stats, excl)


if __name__ == "__main__":
    main()
