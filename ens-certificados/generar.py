"""Quién se certifica en el Esquema Nacional de Seguridad.

Se mide, sobre el registro público de certificaciones de conformidad con
el Esquema Nacional de Seguridad (ENS) que mantiene el Centro
Criptológico Nacional (CCN), cuántos sistemas están certificados, de
qué categoría, de qué tipo de entidad, con qué certificadora y cuándo
vencen sus certificados.

El registro se lee de los cuatro listados que sirve el propio portal de
gobernanza del CCN (categorías BÁSICA, MEDIA y ALTA, y perfiles de
cumplimiento específico), que devuelven una página con los datos en
JSON. Una petición por listado, con pausa entre ellas.

Los CSV no guardan nombre, NIF, dirección ni web de las entidades: de
cada una se conserva un número interno, su tipo según el CCN y la clase
que indica la letra de su NIF. El alcance certificado se reduce a
indicadores temáticos.

Requisitos: Python 3.10 o posterior y ``tqdm`` (``requirements.txt``).

Uso::

    python generar.py
"""

import csv
import html
import json
import logging
import random
import re
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from tqdm import tqdm

# rutas: todo se escribe junto a este fichero
DIR = Path(__file__).resolve().parent
DIR_SALIDAS = DIR / "salidas"

UA = (
    "ManPlaNet-medicion/1.0 (+https://manpla.net; "
    "investigacion registro publico ENS)"
)
BASE = ("https://gobernanza.ccn-cert.cni.es/amparo/API/public/"
        "certificaciones/empresas/")
LISTADOS = {
    "sistemascertificadosbasica": "categoria",
    "sistemascertificadosmedia": "categoria",
    "sistemascertificadosalta": "categoria",
    "requisitosesenciales": "perfil_especifico",
}
SEMILLA = 20261015
PAUSA = 2.0

# clase del titular según la primera letra del NIF (Orden EHA/451/2008)
CLASE_NIF = {
    "A": "sociedad", "B": "sociedad", "C": "sociedad", "D": "sociedad",
    "F": "sociedad", "G": "asociacion_fundacion", "E": "otra_entidad",
    "J": "otra_entidad", "U": "otra_entidad", "V": "otra_entidad",
    "H": "otra_entidad", "N": "entidad_extranjera",
    "W": "entidad_extranjera", "R": "entidad_religiosa",
    "P": "administracion_local", "Q": "organismo_publico",
    "S": "administracion_estado_ccaa",
}

# indicadores del alcance certificado (texto libre de cada certificado)
TEMAS = {
    "nube": r"\bnube\b|cloud|\bsaas\b|\biaas\b|\bpaas\b|hosting|alojamiento",
    "centro_datos": r"centros? de (?:proceso de )?datos|\bcpd\b|data ?center",
    "software": r"desarrollo|software|aplicaci[oó]n(?:es)?\b|mantenimiento "
                r"evolutivo|plataforma",
    "consultoria": r"consultor[ií]a|asesor[ií]a|auditor[ií]a",
    "ciberseguridad": r"ciberseguridad|\bsoc\b|\bsiem\b|centro de "
                      r"operaciones de seguridad|monitorizaci[oó]n de "
                      r"seguridad|respuesta a incidentes",
    "comunicaciones": r"telecomunicaci|comunicaciones|\bred(?:es)?\b|"
                      r"conectividad|telefon[ií]a",
    "documental": r"digitalizaci|gesti[oó]n documental|archivo|"
                  r"custodia|impresi[oó]n",
    "sanidad": r"sanitari|salud|hospital|cl[ií]nic",
    "formacion": r"(?<!in)formaci[oó]n|educaci|e-?learning",
    "administracion_electronica": r"sede electr[oó]nica|administraci[oó]n "
                                  r"electr[oó]nica|registro electr|"
                                  r"tramitaci[oó]n",
}


def configurar_log() -> None:
    """Configura el registro en pantalla."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")


def pedir(url: str, intentos: int = 4) -> str:
    """Descarga una URL con reintentos y devuelve el texto."""
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                cuerpo = r.read().decode("utf-8", errors="replace")
            time.sleep(PAUSA)
            return cuerpo
        except OSError as e:
            logging.warning("fallo %s (%s), intento %d", url, e, i + 1)
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"no se pudo descargar {url}")


def leer_listado(nombre: str) -> list[dict]:
    """Extrae la lista ``rowData`` de una página del registro."""
    pagina = pedir(BASE + nombre)
    m = re.search(r"var rowData\s*=\s*(\[.*?\]);", pagina, re.S)
    if not m:
        raise RuntimeError(f"sin datos en {nombre}")
    return json.loads(m.group(1))


def fecha(texto: str | None) -> str:
    """Convierte «dd/mm/aaaa» en ISO; vacío si no hay fecha."""
    if not texto:
        return ""
    return datetime.strptime(texto.strip(), "%d/%m/%Y").date().isoformat()


def clase_nif(nif: str) -> str:
    """Clase del titular según la forma de su NIF."""
    nif = (nif or "").strip().upper()
    if not nif or re.fullmatch(r"0+[A-Z]?", nif):
        return "sin_nif"
    if re.fullmatch(r"\d{8}[A-Z]", nif) or nif[:1] in ("X", "Y", "Z"):
        return "persona_fisica"
    return CLASE_NIF.get(nif[:1], "sin_clase")


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
        print({k: v for k, v in fila.items() if v not in ("", "0")})


def main() -> None:
    """Descarga los cuatro listados y escribe los CSV de ``salidas/``."""
    hoy = date.today().isoformat()
    crudos = []
    for nombre, listado in tqdm(LISTADOS.items(), desc="listados"):
        for fila in leer_listado(nombre):
            crudos.append((listado, nombre, fila))
    # número interno por entidad, estable dentro de la ejecución; los
    # registros llevan un NIF de relleno (00000000A) y se distinguen por
    # su nombre, que no se guarda
    def clave(f: dict) -> str:
        nif = (f.get("extraDataCifNif") or "").strip().upper()
        if clase_nif(nif) == "sin_nif":
            return "nombre:" + (f.get("extraDataEntityName") or "").strip()
        return nif

    claves = sorted({clave(f) for _, _, f in crudos})
    indice = {c: i + 1 for i, c in enumerate(claves)}
    filas = []
    for listado, nombre, f in crudos:
        alcance = html.unescape(re.sub(r"<[^>]+>", " ",
                                       f.get("description") or ""))
        alcance_min = alcance.lower()
        ruta = f.get("downloadFilePath") or ""
        m = re.search(r"/certificaciones/(\d+)/download/(\d+)", ruta)
        fila = {
            "listado": listado,
            "id_ccn": f"{m.group(1)}-{m.group(2)}" if m else "",
            "categoria": f.get("systemCategory") or "",
            "perfil": f.get("pce") or "",
            "certificador": (f.get("creditorOrgName") or "").strip(),
            "fecha_concesion": fecha(f.get("grantDate")),
            "fecha_vencimiento": fecha(f.get("dueDate")),
            "fecha_extension": fecha(f.get("extensionDate")),
            "tipo_entidad": f.get("extraDataEntityType") or "",
            "clase_nif": clase_nif(f.get("extraDataCifNif")),
            "entidad": indice[clave(f)],
            "registro": int(bool(re.match(
                r"\s*registro (?:de la propiedad|mercantil|de bienes)",
                f.get("extraDataEntityName") or "", re.I))),
            "palabras_alcance": len(alcance.split()),
        }
        for tema, patron in TEMAS.items():
            fila[f"tema_{tema}"] = int(bool(re.search(patron, alcance_min)))
        filas.append(fila)
    filas.sort(key=lambda x: (x["listado"], x["fecha_concesion"],
                              x["id_ccn"]))
    campos = list(filas[0])
    escribir_csv(DIR_SALIDAS / "certificados.csv", filas, campos)
    mostrar_muestra(DIR_SALIDAS / "certificados.csv")

    # certificadoras: cuota en los listados por categoría
    por_cert = Counter(f["certificador"] for f in filas
                       if f["listado"] == "categoria")
    total = sum(por_cert.values())
    acumulada, filas_cert = 0, []
    for cert, n in por_cert.most_common():
        acumulada += n
        filas_cert.append({"certificador": cert, "certificados": n,
                           "cuota": round(n / total, 4),
                           "cuota_acumulada": round(acumulada / total, 4)})
    escribir_csv(DIR_SALIDAS / "certificadoras.csv", filas_cert,
                 list(filas_cert[0]))

    # vencimientos por mes, por listado y tipo de entidad
    venc = Counter((f["fecha_vencimiento"][:7], f["listado"],
                    "registro" if f["registro"] else f["tipo_entidad"])
                   for f in filas if f["fecha_vencimiento"])
    escribir_csv(DIR_SALIDAS / "vencimientos_mensuales.csv",
                 [{"mes": m, "listado": lst, "tipo": t, "n": n}
                  for (m, lst, t), n in sorted(venc.items())],
                 ["mes", "listado", "tipo", "n"])

    # resumen por listado, categoría y tipo de entidad
    res = defaultdict(lambda: {"certificados": 0, "entidades": set()})
    for f in filas:
        clave = (f["listado"], f["categoria"],
                 "registro" if f["registro"] else f["tipo_entidad"])
        res[clave]["certificados"] += 1
        res[clave]["entidades"].add(f["entidad"])
    escribir_csv(DIR_SALIDAS / "resumen.csv",
                 [{"listado": a, "categoria": b, "tipo": c,
                   "certificados": v["certificados"],
                   "entidades": len(v["entidades"])}
                  for (a, b, c), v in sorted(res.items())],
                 ["listado", "categoria", "tipo", "certificados",
                  "entidades"])

    meta = {"fecha_consulta": hoy, "generado":
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "certificados": len(filas),
            "por_listado": dict(Counter(f["listado"] for f in filas)),
            "entidades": len(indice)}
    (DIR_SALIDAS / "volumenes.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    logging.info("listo: %s", meta)


if __name__ == "__main__":
    configurar_log()
    main()
