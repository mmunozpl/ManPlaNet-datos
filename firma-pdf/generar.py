"""Mide la herramienta de firma de PDF de herramienta/ sobre un documento real.

Qué hace, en orden:

1. descarga el PDF del NIST Cybersecurity Framework 2.0 (dominio público en
   EE. UU., sin firma previa), comprueba su huella y toma sus tres primeras
   páginas;
2. crea una autoridad de certificación de pruebas y un certificado de
   firmante ficticio con la forma de los de la FNMT (el CN lleva un número
   de documento inventado); es la única pieza sintética, porque un
   certificado real no se puede publicar;
3. firma el documento sin sello de tiempo y con el sello cualificado de
   Sectigo (Europe) SL, mide tiempo y bytes, y valida cada firma: contra la
   CA de pruebas, y el sello contra la CA de sellado de la lista de
   confianza española; repite la validación con un byte alterado;
4. mide la legibilidad del QR del pie con ZXing según su contenido y la
   resolución de la imagen;
5. lee la lista de confianza española (TSL) y extrae sus servicios de
   sellado de tiempo cualificado;
6. guarda una imagen del pie de la última página.

Escribe en datos/ junto a este guion. Ningún dato de ninguna persona
interviene: el firmante es ficticio.

Uso:
    python generar.py [--sin-red-sello]
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DATOS = AQUI / "datos"
# el registro de la herramienta va a una carpeta temporal, no a la del usuario
_TMP = Path(tempfile.mkdtemp(prefix="firma-pdf-"))
os.environ["XDG_DATA_HOME"] = str(_TMP)
os.environ["APPDATA"] = str(_TMP)
sys.path.insert(0, str(AQUI / "herramienta"))

import firmar  # noqa: E402
from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.hazmat.primitives.serialization import pkcs12  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402
from PIL import Image  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402
from reportlab.graphics.barcode.qr import QrCodeWidget  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402
from tqdm import tqdm  # noqa: E402

UA = "Mozilla/5.0"
CSF_URL = "https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf"
CSF_SHA256 = ("3c31f46fee98cac0c4323453e5109291a213b4de7fef8c058af9bf67f717433c")
TSL_URL = "https://tsl.digital.gob.es/TSL.xml"
# el ENS en el BOE: un PDF firmado por el propio boletín
BOE_URL = ("https://www.boe.es/boe/dias/2022/05/04/pdfs/"
           "BOE-A-2022-7191.pdf")
QTST = "http://uri.etsi.org/TrstSvc/Svctype/TSA/QTST"
NS = {"t": "http://uri.etsi.org/02231/v2#"}
RESOLUCIONES = [60, 72, 90, 100, 120, 150, 200, 300]
REPETICIONES = 5
# pausa entre peticiones al servicio de sellado, por cortesía con él
PAUSA_SELLO = 16


def descargar(url: str) -> bytes:
    """Descarga una URL con la identificación del repositorio de datos."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def sha256(datos: bytes) -> str:
    """Huella SHA-256 en hexadecimal."""
    return hashlib.sha256(datos).hexdigest()


# 1. documento -----------------------------------------------------------------

def documento() -> tuple[Path, dict]:
    """Descarga el CSF 2.0, comprueba su huella y guarda tres páginas."""
    pdf = descargar(CSF_URL)
    if sha256(pdf) != CSF_SHA256:
        sys.exit("el PDF del NIST ha cambiado: revisar la huella fijada")
    lector = PdfReader(io.BytesIO(pdf))
    escritor = PdfWriter()
    for pagina in lector.pages[:3]:
        escritor.add_page(pagina)
    # sin metadatos de origen en el extracto
    escritor.add_metadata({"/Title": "NIST CSF 2.0, páginas 1 a 3"})
    destino = DATOS / "documento.pdf"
    with destino.open("wb") as fh:
        escritor.write(fh)
    return destino, {"url": CSF_URL, "sha256": CSF_SHA256,
                     "paginas_original": len(lector.pages),
                     "paginas_extracto": 3,
                     "bytes_extracto": destino.stat().st_size}


# 2. certificados de prueba -------------------------------------------------------

def certificados() -> tuple[bytes, bytes, x509.Certificate]:
    """Crea una CA de pruebas y un certificado de firmante ficticio.

    Returns:
        El PKCS#12 del firmante, su contraseña y el certificado de la CA.
    """
    ahora = dt.datetime.now(dt.timezone.utc)
    clave_ca = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    nombre_ca = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "ES"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME,
                           "Autoridad de pruebas (sin validez)"),
        x509.NameAttribute(NameOID.COMMON_NAME, "AC DE PRUEBAS"),
    ])
    ca = (x509.CertificateBuilder()
          .subject_name(nombre_ca).issuer_name(nombre_ca)
          .public_key(clave_ca.public_key())
          .serial_number(x509.random_serial_number())
          .not_valid_before(ahora - dt.timedelta(minutes=5))
          .not_valid_after(ahora + dt.timedelta(days=365))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
          .add_extension(x509.KeyUsage(False, False, False, False, False,
                                       True, True, False, False), True)
          .sign(clave_ca, hashes.SHA256()))
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sujeto = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "ES"),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, "IDCES-00000000T"),
        x509.NameAttribute(NameOID.SURNAME, "DE PRUEBA"),
        x509.NameAttribute(NameOID.GIVEN_NAME, "FIRMANTE"),
        x509.NameAttribute(NameOID.COMMON_NAME,
                           "DE PRUEBA FIRMANTE - 00000000T"),
    ])
    hoja = (x509.CertificateBuilder()
            .subject_name(sujeto).issuer_name(nombre_ca)
            .public_key(clave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(ahora - dt.timedelta(minutes=5))
            .not_valid_after(ahora + dt.timedelta(days=365))
            .add_extension(x509.KeyUsage(True, True, False, False, False,
                                         False, False, False, False), True)
            .sign(clave_ca, hashes.SHA256()))
    clave_p12 = b"prueba"
    p12 = pkcs12.serialize_key_and_certificates(
        b"firmante-prueba", clave, hoja, [ca],
        serialization.BestAvailableEncryption(clave_p12))
    (DATOS / "ac-pruebas.pem").write_bytes(
        ca.public_bytes(serialization.Encoding.PEM))
    (DATOS / "firmante-prueba.p12").write_bytes(p12)
    return p12, clave_p12, ca


# 3. firma y validación ---------------------------------------------------------

def validar(pdf: bytes, ca: x509.Certificate) -> dict:
    """Valida la firma contra la CA de pruebas y el sello contra la TSL.

    La CA de pruebas no publica revocación, así que se consulta solo si
    puede (soft-fail); con un certificado real la herramienta la exige.
    """
    import logging

    from pyhanko.keys import load_cert_from_pemder
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    for n in ("pyhanko", "pyhanko_certvalidator", "asyncio"):
        logging.getLogger(n).setLevel(logging.CRITICAL)
    raiz = DATOS / "ac-pruebas.pem"
    ctx = ValidationContext(trust_roots=[load_cert_from_pemder(str(raiz))],
                            allow_fetching=False, revocation_mode="soft-fail")
    ctx_ts = ValidationContext(
        trust_roots=[load_cert_from_pemder(str(p))
                     for p in firmar.CONFIANZA_TSA],
        allow_fetching=True, revocation_mode="soft-fail")
    firma = PdfFileReader(io.BytesIO(pdf)).embedded_signatures[0]
    est = validate_pdf_signature(firma, ctx, ts_validation_context=ctx_ts)
    sello = est.timestamp_validity
    return {"intacta": bool(est.intact), "criptografia": bool(est.valid),
            "cadena": bool(est.trusted),
            "cubre": est.coverage.name,
            "sello": None if sello is None else bool(sello.valid
                                                     and sello.trusted),
            "subfiltro": firma.sig_object["/SubFilter"][1:]}


def alterar(pdf: bytes) -> bytes:
    """Cambia un byte del contenido firmado (fuera de la firma misma)."""
    datos = bytearray(pdf)
    i = datos.find(b"stream") + 20
    datos[i] = (datos[i] + 1) % 256
    return bytes(datos)


def firmas(doc: Path, p12: bytes, clave: bytes, ca, con_sello: bool) -> dict:
    """Firma con y sin sello, mide y valida."""
    resultados = {}
    variantes = [("sin_sello", None)]
    if con_sello:
        variantes.append(("sello_cualificado", firmar.TSA_DEFECTO))
    for nombre, tsa in variantes:
        tiempos, ultimo = [], None
        n = REPETICIONES if tsa is None else 3
        for k in tqdm(range(n), desc=f"firma {nombre}", leave=False):
            if tsa and k:
                time.sleep(PAUSA_SELLO)
            salida = _TMP / f"{nombre}.pdf"
            t0 = time.perf_counter()
            firmar.firmar_documento(
                doc, salida, p12, clave,
                motivo="Conformidad con el documento", lugar="Sevilla, España",
                tsa=tsa, referencia="PRO-2026-014")
            tiempos.append(time.perf_counter() - t0)
            ultimo = salida.read_bytes()
        destino = DATOS / f"firmado-{nombre.replace('_', '-')}.pdf"
        destino.write_bytes(ultimo)
        v = validar(ultimo, ca)
        v_alterado = validar(alterar(ultimo), ca)
        resultados[nombre] = {
            "repeticiones": n,
            "segundos_mediana": round(statistics.median(tiempos), 3),
            "segundos": [round(t, 3) for t in tiempos],
            "bytes": len(ultimo),
            "validacion": v,
            "validacion_con_un_byte_alterado": v_alterado,
        }
    return resultados


def geometria(doc: Path) -> dict:
    """Banda del pie, factor de reducción y bytes que añade el pie."""
    from unittest import mock

    from pypdf import PageObject

    con_pie = _TMP / "con_pie.pdf"
    sin_recomprimir = _TMP / "sin_recomprimir.pdf"
    argumentos = dict(motivo="Conformidad con el documento",
                      lugar="Sevilla, España", referencia="PRO-2026-014")
    firmar.poner_pie(doc, con_pie, "Firmante De Prueba", **argumentos)
    # como antes de la corrección: la fusión dejaba el contenido sin comprimir
    with mock.patch.object(PageObject, "compress_content_streams",
                           lambda *a, **k: None):
        firmar.poner_pie(doc, sin_recomprimir, "Firmante De Prueba",
                         **argumentos)
    pag = PdfReader(str(doc)).pages[0]
    alto = float(pag.mediabox.height)
    ancho = float(pag.mediabox.width)
    factor = (alto - firmar.BANDA) / alto
    return {"pagina_pt": [ancho, alto], "banda_pt": firmar.BANDA,
            "banda_mm": round(firmar.BANDA * 25.4 / 72, 1),
            "lado_qr_pt": firmar.LADO_QR,
            "lado_qr_mm": round(firmar.LADO_QR * 25.4 / 72, 1),
            "factor_contenido": round(factor, 4),
            "reduccion_pct": round(100 * (1 - factor), 1),
            "factor_a4": round((841.89 - firmar.BANDA) / 841.89, 4),
            "bytes_documento": doc.stat().st_size,
            "bytes_con_pie_sin_firma": con_pie.stat().st_size,
            "bytes_con_pie_sin_recomprimir": sin_recomprimir.stat().st_size}


def boe() -> dict:
    """Formato de la firma del PDF del ENS en el BOE y si pyHanko la lee."""
    from pyhanko.pdf_utils.reader import PdfFileReader

    pdf = descargar(BOE_URL)
    subfiltros = sorted({m.decode() for m in __import__("re").findall(
        rb"/SubFilter\s*/([A-Za-z0-9.]+)", pdf)})
    leidas = len(PdfFileReader(io.BytesIO(pdf), strict=False)
                 .embedded_signatures)
    return {"url": BOE_URL, "sha256": sha256(pdf), "subfiltros": subfiltros,
            "firmas_que_lee_pyhanko": leidas}


def aplicacion(dist: Path) -> dict:
    """Tamaño de una construcción de la aplicación y de sus piezas."""
    def tam(p: Path) -> int:
        # los enlaces simbólicos no ocupan: se cuentan solo los ficheros
        if not p.is_dir():
            return 0 if p.is_symlink() else p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*")
                   if f.is_file() and not f.is_symlink())

    carpeta = dist / "FirmaManPla"
    internas = carpeta / "_internal"
    piezas = sorted(((p.name, tam(p)) for p in internas.iterdir()),
                    key=lambda x: -x[1])
    zips = list(dist.glob("FirmaManPla-*.zip"))
    return {"sistema": platform.system(), "arquitectura": platform.machine(),
            "bytes_carpeta": tam(carpeta),
            "bytes_zip": zips[0].stat().st_size if zips else None,
            "piezas_mayores": [{"pieza": n, "bytes": b}
                               for n, b in piezas[:8]]}


# 4. legibilidad del qr -----------------------------------------------------------

def qr_legibilidad() -> list[dict]:
    """Lee con ZXing el QR del pie según su contenido y la resolución.

    El QR se dibuja con la función de la herramienta, a su tamaño real, se
    rasteriza a 600 ppp con pdftoppm y se reduce por áreas a cada
    resolución, como haría un escáner o una foto de menor detalle.
    """
    import zxingcpp

    fecha, ident = "16/11/2026 21:15 UTC+01:00", "CD5E-47D6-8575"
    obligatorios = {"nombre": "Firmante De Prueba",
                    "formato": "PAdES-B-B",
                    "emisor_cn": "AC FNMT Usuarios",
                    "serie": "6A0F3C9E21B47D58A0C4E1F29B3D7E15",
                    "certificado": "AC FNMT Usuarios · nº "
                                   "6A0F3C9E21B47D58A0C4E1F29B3D7E15",
                    "huella_original": "3C31 F46F EE98 CAC0"}
    completos = dict(obligatorios, lugar="Sevilla, España",
                     motivo="Conformidad con la propuesta de servicios de "
                     "consultoría y su anexo técnico",
                     referencia="PRO-2026-014",
                     sello="Cualificado, Sectigo (Europe) SL",
                     formato="PAdES-B-T")
    variantes = {
        "enlace a VALIDe": f"{firmar.VALIDE}#ManPla.net-firmado-{ident}",
        "cuatro datos": ("Firmado digitalmente\nId. " + ident
                         + "\nFirmante: Firmante De Prueba\nFecha: " + fecha),
        "datos obligatorios": firmar.texto_qr(obligatorios, fecha, ident),
        "todos los datos, motivo de 60": firmar.texto_qr(completos, fecha,
                                                         ident),
    }
    filas = []
    for nombre, texto in tqdm(variantes.items(), desc="qr", leave=False):
        w = QrCodeWidget(texto, barLevel="L", barBorder=2)
        w.draw()  # el código se construye al dibujar
        modulos = w.qr.getModuleCount()
        pdf = _TMP / "qr.pdf"
        c = canvas.Canvas(str(pdf), pagesize=(firmar.LADO_QR + 40,
                                              firmar.LADO_QR + 40))
        firmar._qr(c, texto, 20, 20, firmar.LADO_QR)
        c.save()
        subprocess.run(["pdftoppm", "-r", "600", "-png", "-singlefile",
                        str(pdf), str(_TMP / "qr")], check=True)
        img = Image.open(_TMP / "qr.png").convert("L")
        for ppp in RESOLUCIONES:
            reducida = img.resize((round(img.width * ppp / 600),
                                   round(img.height * ppp / 600)), Image.BOX)
            leido = zxingcpp.read_barcodes(reducida)
            filas.append({
                "contenido": nombre, "bytes": len(texto.encode()),
                "modulos": modulos,
                "mm_por_modulo": round(firmar.LADO_QR * 25.4 / 72
                                       / (modulos + 4), 3),
                "ppp": ppp, "leido": int(bool(leido)
                                         and leido[0].text == texto),
            })
    return filas


# 5. lista de confianza -----------------------------------------------------------

def tsl() -> tuple[list[dict], dict]:
    """Servicios de sellado de tiempo cualificado de la TSL española."""
    xml = descargar(TSL_URL)
    raiz = ET.fromstring(xml)
    emision = raiz.findtext(".//t:ListIssueDateTime", namespaces=NS)
    filas = []
    for tsp in raiz.iterfind(".//t:TrustServiceProvider", NS):
        prestador = tsp.findtext(
            "t:TSPInformation/t:TSPName/t:Name", namespaces=NS)
        for srv in tsp.iterfind(".//t:TSPService", NS):
            info = srv.find("t:ServiceInformation", NS)
            if info.findtext("t:ServiceTypeIdentifier", namespaces=NS) != QTST:
                continue
            filas.append({
                "prestador": prestador,
                "servicio": info.findtext("t:ServiceName/t:Name",
                                          namespaces=NS),
                "estado": info.findtext("t:ServiceStatus",
                                        namespaces=NS).rsplit("/", 1)[-1],
                "desde": info.findtext("t:StatusStartingTime",
                                       namespaces=NS),
            })
    texto = xml.decode("utf-8", errors="replace").lower()
    meta = {"url": TSL_URL, "sha256": sha256(xml), "emision": emision,
            "bytes": len(xml),
            "servicios_qtst": len(filas),
            "servicios_qtst_concedidos": sum(f["estado"] == "granted"
                                             for f in filas),
            "prestadores_con_qtst_concedido": len({
                f["prestador"] for f in filas if f["estado"] == "granted"}),
            "menciones_freetsa": texto.count("freetsa"),
            "sectigo_qtst": [f for f in filas
                             if "sectigo" in (f["prestador"] or "").lower()]}
    return filas, meta


# 6. imagen del pie ---------------------------------------------------------------

def imagen_pie(pdf: Path) -> None:
    """Rasteriza el pie de la última página, sin metadatos."""
    n = len(PdfReader(str(pdf)).pages)
    base = _TMP / "pie"
    subprocess.run(["pdftoppm", "-r", "200", "-f", str(n), "-l", str(n),
                    "-png", "-singlefile", str(pdf), str(base)], check=True)
    img = Image.open(f"{base}.png").convert("RGB")
    alto_banda = round((firmar.BANDA + 6) * 200 / 72)
    recorte = img.crop((0, img.height - alto_banda, img.width, img.height))
    recorte.save(DATOS / "pie.png", optimize=True)


def guardar_csv(nombre: str, filas: list[dict]) -> None:
    """Escribe un CSV con cabecera y muestra unas filas."""
    with (DATOS / nombre).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    print(f"\n{nombre}: {len(filas)} filas")
    for f in filas[:15]:
        print("  ", f)


def versiones() -> dict:
    """Versiones del software que interviene en la medición."""
    from importlib.metadata import version

    paquetes = ["pyhanko", "pyhanko-certvalidator", "pypdf", "reportlab",
                "cryptography", "zxing-cpp", "pillow"]
    v = {p: version(p) for p in paquetes}
    v["python"] = platform.python_version()
    v["pdftoppm"] = subprocess.run(["pdftoppm", "-v"], capture_output=True,
                                   text=True).stderr.split("\n")[0]
    return v


def main() -> None:
    """Ejecuta las seis partes y escribe el resumen."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sin-red-sello", action="store_true",
                    help="no pide sellos de tiempo al servicio cualificado")
    ap.add_argument("--app", type=Path,
                    help="carpeta dist/ de una construcción, para medirla")
    a = ap.parse_args()
    DATOS.mkdir(exist_ok=True)
    doc, meta_doc = documento()
    p12, clave, ca = certificados()
    resumen = {
        "fecha": dt.datetime.now(firmar.ZONA).isoformat(timespec="seconds"),
        # carga del sistema al empezar: los tiempos con carga > 2 no valen
        "carga_1_5_15": [round(x, 2) for x in os.getloadavg()],
        "documento": meta_doc,
        "geometria": geometria(doc),
        "firmas": firmas(doc, p12, clave, ca, not a.sin_red_sello),
        "versiones": versiones(),
        "boe": boe(),
    }
    if a.app:
        resumen["aplicacion"] = aplicacion(a.app)
    qr = qr_legibilidad()
    guardar_csv("qr_legibilidad.csv", qr)
    filas_tsl, meta_tsl = tsl()
    guardar_csv("tsl_sellado_cualificado.csv", filas_tsl)
    resumen["tsl"] = meta_tsl
    imagen_pie(DATOS / ("firmado-sello-cualificado.pdf"
                        if not a.sin_red_sello else "firmado-sin-sello.pdf"))
    (DATOS / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nresumen.json:")
    print(json.dumps({k: resumen[k] for k in ("geometria", "firmas")},
                     ensure_ascii=False, indent=1)[:3000])
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
