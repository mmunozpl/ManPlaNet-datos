"""Firma un PDF con el certificado de la FNMT y le pone un pie de firma.

Cada página recibe un recuadro al pie, al modo de las referencias
electrónicas de la Seguridad Social: firmante, fecha, identificador del
documento y página, con una línea sobre cómo comprobar la firma. Después se
firma en PAdES con el certificado (.p12 o .pfx exportado del navegador), y el
campo de firma se coloca sobre el recuadro de la última página, de modo que
pulsarlo en el lector abre la validación.

El contenido original se reduce lo justo para dejar libre la banda del pie,
así que ningún texto del documento queda tapado.

Uso:
    firmar.py entrada.pdf [-o salida.pdf] --p12 certificado.p12
        [--motivo "..."] [--lugar "Sevilla"] [--tsa URL] [--sin-reducir]
    firmar.py entrada.pdf --solo-pie --nombre "Manuel Muñoz Plá"

Con --solo-pie no se firma: se pone el pie y se deja el PDF listo para
firmarlo en Okular o en AutoFirma, dibujando la firma sobre el recuadro.
La contraseña se pide por teclado, o se toma de FIRMA_P12_CLAVE si existe.

    firmar.py --listar
    firmar.py entrada.pdf --instalado N

Con --listar se enumeran los certificados con clave privada instalados en el
sistema (Firefox y Chrome en Linux, el almacén personal en Windows, el
llavero en macOS; ver almacenes.py); --instalado N firma con el número N de
esa lista, sin exportar nada a disco. En Linux la contraseña es la principal
del navegador, vacía si no tiene.

    firmar.py documento_firmado.pdf --comprobar [--valide | --valide-web]

Con --comprobar se valida en local lo mismo que valida VALIDe: integridad,
cadena hasta la raíz de la FNMT y revocación por OCSP o CRL, y se busca la
huella del fichero en el registro. Con --valide se envía el fichero a VALIDe
y se muestra su respuesta: el código de seguridad del formulario se enseña
en una imagen y lo escribe la persona, nunca el programa. Con --valide-web
solo se abre el formulario en el navegador.

Cada firma se anota en registro.csv, en la carpeta de datos del usuario
(~/.local/share/ManPla/firma-pdf, %APPDATA%\\ManPla\\firma-pdf o
~/Library/Application Support/ManPla/firma-pdf).
"""
import argparse
import csv
import datetime as dt
import getpass
import hashlib
import html
import io
import logging
import os
import re
import secrets
import subprocess
import tempfile
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.serialization import pkcs12
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers, timestamps
from pyhanko.stamp import TextStampStyle
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import ArrayObject, FloatObject, NameObject
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import Color, black
from reportlab.pdfgen import canvas

import almacenes

# versión de la aplicación (la misma que pyproject.toml)
VERSION = "0.1.0"

# recursos de la herramienta: junto al guion, o dentro del ejecutable
RECURSOS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _carpeta_datos() -> Path:
    """Carpeta de datos del usuario, la que reserva cada sistema."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME",
                                   Path.home() / ".local" / "share"))
    carpeta = base / "ManPla" / "firma-pdf"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


DATOS = _carpeta_datos()
REGISTRO = DATOS / "registro.csv"
CARPETA_CERTS = DATOS / "certificados"
ZONA = ZoneInfo("Europe/Madrid")
VALIDE_BASE = "https://valide.redsara.es/valide/"
VALIDE = VALIDE_BASE + "validarFirma/ejecutar.html"
VALIDE_ENVIO = VALIDE_BASE + "ejecutarValidarFirma/ejecutar.html"
VALIDE_MAX = 8 * 1024 * 1024  # límite del formulario
# raíz de la FNMT, incluida en la herramienta para no depender del sistema
# (sha256 ebc5570c29018c4d67b1aa127baf12f703b4611ebc17b7dab5573894179b93fa)
RAIZ_FNMT = RECURSOS / "confianza" / "fnmt-raiz.pem"
# sellado de tiempo cualificado de Sectigo (Europe) SL, en la lista de
# confianza española (TSA/QTST, concedido desde el 05-05-2021); su CA se tomó
# de esa lista y se guarda en confianza/
TSA_DEFECTO = "http://timestamp.sectigo.com/qualified"
CONFIANZA_TSA = sorted((RECURSOS / "confianza" / "tsa").glob("*.pem"))

# geometría del pie, en puntos
MARGEN = 24
ALTO_FILA = 9
ALTO_TABLA = 6 * ALTO_FILA  # tres bloques de rótulo y valor
ALTO_NOTA = 14
# el qr ocupa el alto de las seis filas de la tabla: 54 pt, unos 1,9 cm
LADO_QR = ALTO_TABLA
HUECO_QR = 5
ALTO_TITULO = 10
BANDA = MARGEN + ALTO_TABLA + ALTO_NOTA + ALTO_TITULO
# cuerpos de letra del pie, en puntos
TAM_TITULO = 7
TAM_ROTULO = 5.5
TAM_VALOR = 6
TAM_NOTA = 5.5
INTERLINEA_NOTA = 6.5
# base del texto dentro de su fila
BASE_FILA = 2.7
# turquesa de manpla.net (#14b8c9) aclarado al 40 % sobre blanco: #a1e3e9
FONDO = Color(0xA1 / 255, 0xE3 / 255, 0xE9 / 255)
NOTA = (
    "Documento firmado electrónicamente (PAdES) con {certificado}. La firma "
    "puede comprobarse en valide.redsara.es o en el panel de firmas de "
    "cualquier lector PDF. Cualquier modificación posterior del documento "
    "la invalida."
)


def _certificado_nota(emisor: str) -> str:
    """Cómo nombra la nota al certificado: «cualificado» solo si lo es.

    Los certificados de persona física de la FNMT son cualificados; de
    cualquier otro emisor la nota no lo afirma.
    """
    if "FNMT" in emisor.upper():
        return ("certificado cualificado de persona física emitido por la "
                "FNMT-RCM")
    return f"certificado emitido por {emisor}"


def _bytes(p12: Path | bytes) -> bytes:
    """Devuelve el PKCS#12 en bytes, venga de fichero o de memoria."""
    return p12 if isinstance(p12, bytes) else Path(p12).read_bytes()


def datos_certificado(p12: Path | bytes, clave: bytes) -> dict:
    """Lee del certificado el nombre del firmante, el emisor y la caducidad.

    Args:
        p12: ruta del fichero PKCS#12 o sus bytes.
        clave: contraseña del fichero.

    Returns:
        Diccionario con «nombre», «emisor», «caduca» y «huella».
    """
    _, cert, _ = pkcs12.load_key_and_certificates(_bytes(p12), clave)
    d = almacenes.datos_de_cert(cert)
    d["caduca"] = d["caduca"].astimezone(ZONA)
    return d


def descripcion_sello(tsa: str | None) -> str:
    """Texto del pie para el sello de tiempo.

    El pie se dibuja antes de pedir el sello, así que dice si lo lleva y
    quién lo emite; la hora exacta va en la firma.
    """
    if not tsa:
        return "Sin sello de tiempo"
    if tsa.rstrip("/") == TSA_DEFECTO:
        return "Cualificado, Sectigo (Europe) SL"
    from urllib.parse import urlparse

    return f"Sí, de {urlparse(tsa).hostname or tsa}"


def _ajustar(c: canvas.Canvas, texto: str, fuente: str, tam: float,
             ancho: float) -> str:
    """Recorta el texto con puntos suspensivos para que quepa en la celda."""
    if c.stringWidth(texto, fuente, tam) <= ancho:
        return texto
    while texto and c.stringWidth(texto + "…", fuente, tam) > ancho:
        texto = texto[:-1]
    return texto.rstrip() + "…"


def _bloque(c: canvas.Canvas, x0: float, x1: float, y: float,
            columnas: list[tuple[str, float, str]]) -> None:
    """Dibuja un bloque de dos filas: rótulos con fondo y valores debajo.

    Args:
        c: lienzo.
        x0: borde izquierdo.
        x1: borde derecho.
        y: base del bloque.
        columnas: (rótulo, fracción del ancho, valor) por columna.
    """
    c.setFillColor(FONDO)
    c.rect(x0, y + ALTO_FILA, x1 - x0, ALTO_FILA, stroke=0, fill=1)
    c.setFillColor(black)
    c.rect(x0, y, x1 - x0, 2 * ALTO_FILA)
    c.line(x0, y + ALTO_FILA, x1, y + ALTO_FILA)
    xa = x0
    for k, (rotulo, frac, valor) in enumerate(columnas):
        xb = x1 if k == len(columnas) - 1 else xa + (x1 - x0) * frac
        if k:
            c.line(xa, y, xa, y + 2 * ALTO_FILA)
        cx = (xa + xb) / 2
        c.setFont("Helvetica-Bold", TAM_ROTULO)
        c.drawCentredString(cx, y + ALTO_FILA + BASE_FILA, rotulo)
        valor = _ajustar(c, valor, "Helvetica", TAM_VALOR, xb - xa - 5)
        c.setFont("Helvetica", TAM_VALOR)
        c.drawCentredString(cx, y + BASE_FILA, valor)
        xa = xb


def texto_qr(datos: dict, fecha: str, ident: str) -> str:
    """Contenido del qr: los datos de la firma, en texto y sin enlace.

    Solo lleva las líneas que tienen dato. No lleva la huella del firmado,
    que no puede contenerse a sí misma, ni el DNI.
    """
    motivo = datos.get("motivo") or ""
    if len(motivo) > 60:
        # se recorta para que el qr no pierda legibilidad
        motivo = motivo[:59].rstrip() + "…"
    lineas = [
        ("", "Firmado digitalmente"),
        ("Id.", ident),
        ("Firmante:", datos.get("nombre")),
        ("Fecha:", fecha),
        ("Lugar:", datos.get("lugar")),
        ("Motivo:", motivo),
        ("Ref.:", datos.get("referencia")),
        ("Sello de tiempo:", datos.get("sello")),
        ("Formato:", datos.get("formato")),
        ("Certificado:", datos.get("certificado")),
        ("Huella del original:", datos.get("huella_original")),
    ]
    return "\n".join(f"{r} {v}".strip() for r, v in lineas if v)


def _qr(c: canvas.Canvas, texto: str, x: float, y: float,
        lado: float) -> None:
    """Dibuja un qr en el cuadrado indicado.

    Corrección L y margen de dos módulos (el pie ya deja blanco alrededor):
    módulos más grandes en el mismo sitio, legibles a 150 ppp.
    """
    w = QrCodeWidget(texto, barLevel="L", barBorder=2)
    x0, y0, x1, y1 = w.getBounds()
    d = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0,
                                       lado / (y1 - y0), 0, 0])
    d.add(w)
    renderPDF.draw(d, c, x, y)


def pie(ancho: float, datos: dict, fecha: str, ident: str, pagina: int,
        total: int) -> PdfReader:
    """Dibuja el recuadro de pie para una página.

    Args:
        ancho: ancho de la página en puntos.
        datos: «nombre» y «emisor» (de la nota), y los opcionales
            «lugar», «motivo», «referencia», «sello», «formato»,
            «emisor_cn», «serie» y «huella_original»; sin dato, la celda
            va vacía.
        fecha: fecha y hora de firma, ya formateadas.
        ident: identificador del documento.
        pagina: número de página.
        total: número total de páginas.

    Returns:
        Lector con una sola página que contiene el pie.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(ancho, BANDA))
    x_izq, x_der = MARGEN, ancho - MARGEN
    y_tabla = MARGEN + ALTO_NOTA
    # el qr a la derecha; título y tablas a su izquierda
    _qr(c, texto_qr(datos, fecha, ident), x_der - LADO_QR, y_tabla, LADO_QR)
    x0, x1 = x_izq, x_der - LADO_QR - HUECO_QR
    c.setFont("Helvetica-Bold", TAM_TITULO)
    c.drawString(x0 + 2, y_tabla + ALTO_TABLA + 3, "FIRMA ELECTRÓNICA")
    c.setLineWidth(0.6)
    def d(clave):
        return datos.get(clave) or ""

    # bloque superior: quién, cuándo, dónde y qué documento
    _bloque(c, x0, x1, y_tabla + 4 * ALTO_FILA, [
        ("Firmante", 0.25, datos["nombre"]),
        ("Fecha de firma", 0.27, fecha),
        ("Lugar", 0.19, d("lugar")),
        ("Id. documento", 0.18, ident),
        ("Página", 0.11, f"{pagina} de {total}"),
    ])
    # bloque central: para qué, con qué referencia y con qué sello
    _bloque(c, x0, x1, y_tabla + 2 * ALTO_FILA, [
        ("Motivo", 0.44, d("motivo")),
        ("Referencia", 0.22, d("referencia")),
        ("Sello de tiempo", 0.34, d("sello")),
    ])
    # bloque inferior: con qué certificado, en qué formato y sobre qué
    _bloque(c, x0, x1, y_tabla, [
        ("Emisor del certificado", 0.21, d("emisor_cn")),
        ("Nº de serie del certificado", 0.44, d("serie")),
        ("Formato", 0.12, d("formato")),
        ("Huella original (SHA-256)", 0.23, d("huella_original")),
    ])
    # nota de comprobación, en dos líneas
    c.setFont("Helvetica", TAM_NOTA)
    texto = NOTA.format(certificado=_certificado_nota(datos["emisor"]))
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        prueba = f"{actual} {p}".strip()
        if c.stringWidth(prueba, "Helvetica", TAM_NOTA) > x_der - x_izq:
            lineas.append(actual)
            actual = p
        else:
            actual = prueba
    lineas.append(actual)
    for k, linea in enumerate(lineas[:2]):
        c.drawString(x_izq, MARGEN + ALTO_NOTA - TAM_NOTA - 1
                     - k * INTERLINEA_NOTA, linea)
    c.save()
    buf.seek(0)
    return PdfReader(buf)


def _trasladar_anotaciones(pag, t: Transformation) -> None:
    """Aplica a las anotaciones la transformación aplicada al contenido.

    pypdf transforma solo lo que se dibuja: enlaces, campos de formulario y
    notas conservan sus coordenadas y quedarían desplazados respecto del
    texto reducido. Se transforman su rectángulo y, si lo tienen, sus
    cuadriláteros (los de los enlaces y los resaltados).
    """
    def punto(x, y):
        return t.apply_on((float(x), float(y)))

    for ref in pag.get("/Annots") or []:
        a = ref.get_object()
        r = a.get("/Rect")
        if r is not None and len(r) == 4:
            (xa, ya), (xb, yb) = punto(r[0], r[1]), punto(r[2], r[3])
            a[NameObject("/Rect")] = ArrayObject(
                [FloatObject(v) for v in (min(xa, xb), min(ya, yb),
                                          max(xa, xb), max(ya, yb))])
        q = a.get("/QuadPoints")
        if q is not None:
            nuevos = []
            for k in range(0, len(q) - 1, 2):
                nuevos.extend(punto(q[k], q[k + 1]))
            a[NameObject("/QuadPoints")] = ArrayObject(
                [FloatObject(v) for v in nuevos])


def preparar(entrada: Path, datos: dict, fecha: str, ident: str,
             reducir: bool) -> tuple[bytes, list]:
    """Añade el pie a cada página, reduciendo el contenido si procede.

    Args:
        entrada: PDF original.
        datos: nombre del firmante y emisor.
        fecha: fecha de firma formateada.
        ident: identificador del documento.
        reducir: si se reduce el contenido para liberar la banda del pie.

    Returns:
        Los bytes del PDF con pie y el rectángulo del recuadro en la última
        página, para colocar sobre él el campo de firma.
    """
    # se clona sobre el escritor: pypdf 7 solo transforma páginas suyas
    escritor = PdfWriter(clone_from=str(entrada))
    total = len(escritor.pages)
    caja = None
    for i, pag in enumerate(escritor.pages, start=1):
        if pag.rotation:
            pag.transfer_rotation_to_content()
        mb = pag.mediabox
        ancho, alto = float(mb.width), float(mb.height)
        x_org, y_org = float(mb.left), float(mb.bottom)
        if reducir:
            # se escala el contenido y se sube por encima de la banda
            s = (alto - BANDA) / alto
            dx = x_org + ancho * (1 - s) / 2
            t = (Transformation().translate(-x_org, -y_org).scale(s, s)
                 .translate(dx, y_org + BANDA))
            pag.add_transformation(t)
            _trasladar_anotaciones(pag, t)
        sello = pie(ancho, datos, fecha, ident, i, total).pages[0]
        pag.merge_transformed_page(
            sello, Transformation().translate(x_org, y_org)
        )
        # la fusión deja el contenido sin comprimir: el qr solo, unos 47 KB
        # por página; se vuelve a comprimir
        pag.compress_content_streams(level=9)
        y_tabla = y_org + MARGEN + ALTO_NOTA
        caja = (x_org + MARGEN, y_tabla, x_org + ancho - MARGEN,
                y_tabla + ALTO_TABLA)
    escritor.add_metadata({"/Author": datos["nombre"]})
    buf = io.BytesIO()
    escritor.write(buf)
    return buf.getvalue(), [int(v) for v in caja]


def firmar(datos_pdf: bytes, caja: list, total: int, p12: Path | bytes,
           clave: bytes,
           motivo: str, lugar: str, tsa: str | None) -> bytes:
    """Firma en PAdES con el campo visible sobre el recuadro de la última
    página.

    Args:
        datos_pdf: PDF ya con el pie.
        caja: rectángulo del recuadro en la última página.
        total: número de páginas.
        p12: fichero PKCS#12 o sus bytes.
        clave: contraseña.
        motivo: motivo de la firma.
        lugar: lugar de la firma.
        tsa: URL de una autoridad de sellado de tiempo, o None.

    Returns:
        Los bytes del PDF firmado.
    """
    firmante = signers.SimpleSigner.load_pkcs12_data(
        _bytes(p12), other_certs=[], passphrase=clave)
    if firmante is None:
        sys.exit("no se pudo abrir el certificado (¿contraseña?)")
    meta = signers.PdfSignatureMetadata(
        field_name="FirmaManPla", md_algorithm="sha256",
        subfilter=fields.SigSeedSubFilter.PADES,
        reason=motivo or None, location=lugar or None,
    )
    campo = fields.SigFieldSpec(
        "FirmaManPla", on_page=total - 1, box=tuple(caja)
    )
    # el recuadro ya está dibujado: la apariencia del campo va vacía
    estilo = TextStampStyle(stamp_text=" ", border_width=0)
    sellador = timestamps.HTTPTimeStamper(tsa) if tsa else None
    pdf_signer = signers.PdfSigner(
        meta, signer=firmante, timestamper=sellador, stamp_style=estilo,
        new_field_spec=campo,
    )
    w = IncrementalPdfFileWriter(io.BytesIO(datos_pdf))
    salida = pdf_signer.sign_pdf(w)
    return salida.getvalue()


def _cambios(est) -> str:
    """Qué se ha añadido al PDF después de esta firma, según pyHanko.

    Las revisiones añadidas detrás de la firma no rompen su integridad
    criptográfica; el nivel de modificación dice si eran de las permitidas.
    """
    nivel = getattr(est, "modification_level", None)
    if nivel is None or nivel.name == "NONE":
        return "ninguno"
    return {"LTA_UPDATES": "solo datos de validación",
            "FORM_FILLING": "firmas o campos de formulario",
            "ANNOTATIONS": "anotaciones",
            "OTHER": "otros cambios: revisar"}.get(nivel.name, nivel.name)


def comprobar(pdf: Path, revocacion: str) -> bool:
    """Valida las firmas de un PDF contra la raíz de la FNMT.

    Comprueba que el documento no ha cambiado desde la firma, que el
    certificado encadena hasta la raíz y que no está revocado (OCSP o CRL,
    descargados en el momento). Busca también la huella en el registro.

    Args:
        pdf: documento firmado.
        revocacion: «hard-fail» exige consultar la revocación;
            «soft-fail» la consulta si puede.

    Returns:
        True si todas las firmas son válidas.
    """
    from pyhanko.keys import load_cert_from_pemder
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    # se silencian los avisos internos: el resultado va en la tabla
    for nombre in ("pyhanko", "pyhanko_certvalidator", "asyncio"):
        logging.getLogger(nombre).setLevel(logging.CRITICAL)
    contexto = ValidationContext(
        trust_roots=[load_cert_from_pemder(str(RAIZ_FNMT))],
        allow_fetching=True, revocation_mode=revocacion,
    )
    # el sello se valida contra las CA de sellado de la lista de confianza
    contexto_ts = ValidationContext(
        trust_roots=[load_cert_from_pemder(str(p)) for p in CONFIANZA_TSA],
        allow_fetching=True, revocation_mode="soft-fail",
    )
    with pdf.open("rb") as fh:
        firmas = PdfFileReader(fh).embedded_signatures
        if not firmas:
            if b"/adbe.pkcs7.sha1" in pdf.read_bytes():
                print("lleva una firma en formato antiguo (adbe.pkcs7.sha1, "
                      "con SHA-1), que esta comprobación no valida: "
                      "usa --valide")
            else:
                print("el documento no lleva ninguna firma")
            return False
        todo_bien = True
        for n, firma in enumerate(firmas, start=1):
            est = validate_pdf_signature(firma, contexto,
                                         ts_validation_context=contexto_ts)
            sujeto = est.signing_cert.subject.native
            nombre = " ".join(
                x for x in (sujeto.get("given_name"), sujeto.get("surname"))
                if x
            ) or sujeto.get("common_name", "?").split(" - ")[0]
            momento = est.signer_reported_dt
            sello = est.timestamp_validity
            filas = [
                ("firmante", nombre.title()),
                ("emisor", est.signing_cert.issuer.native.get(
                    "common_name", "?")),
                ("fecha declarada", momento.astimezone(ZONA).strftime(
                    "%d/%m/%Y %H:%M") if momento else "sin fecha"),
                ("sello de tiempo", "sí, válido" if sello and sello.valid
                 else ("sí, no válido" if sello else "no")),
                ("documento intacto", "sí" if est.intact else "NO"),
                ("firma criptográfica", "válida" if est.valid else "NO"),
                ("cadena hasta la FNMT", "sí" if est.trusted else "NO"),
                ("revocado", "sí" if est.revoked else "no"),
                ("cubre", "el fichero entero" if est.coverage.name ==
                 "ENTIRE_FILE" else "su revisión; hay revisiones detrás"),
                ("cambios posteriores", _cambios(est)),
            ]
            print(f"firma {n} ({firma.field_name})")
            for k, v in filas:
                print(f"  {k:<22}{v}")
            todo_bien &= est.bottom_line
    huella = hashlib.sha256(pdf.read_bytes()).hexdigest()
    anotado = None
    if REGISTRO.exists():
        with REGISTRO.open(encoding="utf-8") as fh:
            anotado = next((r for r in csv.DictReader(fh)
                            if r["sha256_firmado"] == huella), None)
    if anotado:
        print(f"registro: id {anotado['id']}, firmado el {anotado['fecha']}")
    else:
        print("registro: esta huella no figura en el registro")
    print("resultado:", "VÁLIDO" if todo_bien else "NO VÁLIDO")
    return todo_bien


def fecha_firma(momento: dt.datetime) -> str:
    """Fecha y hora con su desfase respecto de UTC: 16/11/2026 21:15
    UTC+01:00."""
    z = momento.strftime("%z")
    return f"{momento:%d/%m/%Y %H:%M} UTC{z[:3]}:{z[3:]}"


def huella_corta(datos: bytes) -> str:
    """Los 16 primeros caracteres del SHA-256, en grupos de cuatro."""
    h = hashlib.sha256(datos).hexdigest()[:16].upper()
    return " ".join(h[i:i + 4] for i in range(0, 16, 4))


def _anotar(fila: dict) -> None:
    """Añade una fila al registro; si su cabecera es más antigua, la
    amplía conservando las filas que ya tenía."""
    campos = ["id", "fecha", "original", "sha256_original", "firmado",
              "sha256_firmado", "sello_tiempo", "formato", "referencia",
              "certificado"]
    filas = []
    if REGISTRO.exists():
        with REGISTRO.open(encoding="utf-8", newline="") as fh:
            lector = csv.DictReader(fh)
            if lector.fieldnames != campos:
                filas = list(lector)
    if filas or not REGISTRO.exists():
        with REGISTRO.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=campos, restval="")
            w.writeheader()
            w.writerows(filas)
    with REGISTRO.open("a", encoding="utf-8", newline="") as fh:
        csv.DictWriter(fh, fieldnames=campos, restval="").writerow(fila)


def _ident() -> str:
    """Identificador corto del documento, de tres grupos hexadecimales."""
    return "-".join(secrets.token_hex(2).upper() for _ in range(3))


def ya_firmado(pdf: Path) -> bool:
    """Si el PDF lleva alguna firma, de cualquier formato o aplicación.

    Toda firma de PDF declara los bytes que cubre en un «/ByteRange».
    """
    return b"/ByteRange" in pdf.read_bytes()


def autoprueba() -> int:
    """Comprueba que la aplicación empaquetada tiene lo que necesita.

    Dibuja un pie con su QR en memoria y carga pyHanko, sin ventana ni red.
    Sirve para probar el ejecutable de cada sistema tras construirlo.

    Returns:
        0 si todo carga; el error se propaga si algo falta.
    """
    from pyhanko.version import __version__ as version_pyhanko

    datos = {"nombre": "Firmante De Prueba", "emisor": "pruebas",
             "emisor_cn": "AC DE PRUEBAS", "formato": "PAdES-B-B",
             "serie": "00", "huella_original": "0000 0000 0000 0000"}
    r = pie(595.28, datos, fecha_firma(dt.datetime.now(ZONA)), "0000-0000",
            1, 1)
    assert len(r.pages) == 1
    assert RAIZ_FNMT.exists() and CONFIANZA_TSA
    print(f"FirmaManPla {VERSION}: pie y QR dibujados, raíz de la FNMT y "
          f"sello presentes, pyHanko {version_pyhanko}")
    return 0


def poner_pie(entrada: Path, salida: Path, nombre: str,
              emisor: str = "la FNMT-RCM", reducir: bool = True,
              motivo: str = "", lugar: str = "",
              referencia: str = "") -> dict:
    """Pone el pie en todas las páginas sin firmar.

    El sello de tiempo lo decide después el programa que firme, así que el
    pie remite a la firma.

    Args:
        entrada: PDF original.
        salida: PDF de destino.
        nombre: firmante que se muestra.
        emisor: emisor del certificado.
        reducir: si se reduce el contenido para liberar la banda.
        motivo: motivo de la firma.
        lugar: lugar de la firma.
        referencia: referencia libre (propuesta, expediente, contrato).

    Returns:
        Diccionario con «salida», «id» y «caja».
    """
    if ya_firmado(entrada):
        raise ValueError(f"{entrada.name} ya lleva una firma: el pie la "
                         "invalidaría")
    fecha = fecha_firma(dt.datetime.now(ZONA))
    ident = _ident()
    # sello, formato y certificado los decide el programa que firme
    datos = {"nombre": nombre, "emisor": emisor, "motivo": motivo,
             "lugar": lugar, "referencia": referencia,
             "huella_original": huella_corta(entrada.read_bytes())}
    con_pie, caja = preparar(entrada, datos, fecha, ident, reducir)
    salida.write_bytes(con_pie)
    return {"salida": salida, "id": ident, "caja": caja}


def firmar_documento(entrada: Path, salida: Path, p12: Path | bytes,
                     clave: bytes,
                     motivo: str = "",
                     lugar: str = "", tsa: str | None = None,
                     reducir: bool = True, referencia: str = "") -> dict:
    """Pone el pie, firma y anota en el registro.

    Args:
        entrada: PDF original.
        salida: PDF firmado de destino.
        p12: fichero PKCS#12 o sus bytes.
        clave: contraseña del fichero.
        motivo: motivo de la firma.
        lugar: lugar de la firma.
        tsa: URL de sellado de tiempo, o None.
        reducir: si se reduce el contenido para liberar la banda.
        referencia: referencia libre (propuesta, expediente, contrato).

    Returns:
        Diccionario con «salida», «id» y «paginas».
    """
    if ya_firmado(entrada):
        raise ValueError(
            f"{entrada.name} ya lleva una firma: poner el pie redibuja las "
            "páginas y la invalidaría. Firma el original sin firmar.")
    datos = datos_certificado(p12, clave)
    ahora = dt.datetime.now(ZONA)
    if datos["caduca"] < ahora:
        raise ValueError("el certificado caducó el "
                         f"{datos['caduca']:%d/%m/%Y}")
    original = entrada.read_bytes()
    datos.update(
        motivo=motivo, lugar=lugar, referencia=referencia,
        sello=descripcion_sello(tsa) if tsa else "",
        formato="PAdES-B-T" if tsa else "PAdES-B-B",
        certificado=f"{datos['emisor_cn']} · nº {datos['serie']}",
        huella_original=huella_corta(original),
    )
    ident = _ident()
    con_pie, caja = preparar(entrada, datos, fecha_firma(ahora), ident,
                             reducir)
    total = len(PdfReader(io.BytesIO(con_pie)).pages)
    firmado = firmar(con_pie, caja, total, p12, clave, motivo, lugar, tsa)
    salida.write_bytes(firmado)

    # se anota en el registro local, como el código de autenticidad
    _anotar({
        "id": ident, "fecha": ahora.isoformat(timespec="seconds"),
        "original": entrada.name,
        "sha256_original": hashlib.sha256(original).hexdigest(),
        "firmado": salida.name,
        "sha256_firmado": hashlib.sha256(firmado).hexdigest(),
        "sello_tiempo": tsa or "", "formato": datos["formato"],
        "referencia": referencia, "certificado": datos["certificado"],
    })
    return {"salida": salida, "id": ident, "paginas": total}


class SesionValide:
    """Envía un PDF al formulario de VALIDe dentro de una misma sesión.

    El formulario exige un código de seguridad en imagen. Esta clase trae la
    imagen y envía el código que escribe la persona; no intenta leerlo.
    """

    def __init__(self) -> None:
        import requests

        self.http = requests.Session()
        self.http.headers["User-Agent"] = "Mozilla/5.0"
        # se abre el formulario para obtener la cookie de sesión
        self.http.get(VALIDE, timeout=30).raise_for_status()

    def captcha(self) -> bytes:
        """Devuelve la imagen del código de seguridad (JPEG)."""
        r = self.http.get(VALIDE_BASE + "kaptcha.jpg", timeout=30)
        r.raise_for_status()
        return r.content

    def enviar(self, pdf: Path, codigo: str) -> dict:
        """Envía el PDF con el código y resume la respuesta.

        Args:
            pdf: documento firmado.
            codigo: código de seguridad escrito por la persona.

        Returns:
            Diccionario con «estado» («respuesta», «codigo_incorrecto» o
            «error»), «texto» legible y «pagina» (HTML guardado en una
            carpeta privada, o None).
        """
        if pdf.stat().st_size > VALIDE_MAX:
            return {"estado": "error", "pagina": None,
                    "texto": "VALIDe solo admite ficheros de hasta 8 MB"}
        with pdf.open("rb") as fh:
            r = self.http.post(
                VALIDE_ENVIO, data={"codigoSeguridad": codigo.strip()},
                files={"fileData": (pdf.name, fh, "application/pdf")},
                timeout=120,
            )
        r.raise_for_status()
        # el formulario va en latin-1 y la respuesta en utf-8
        try:
            pagina = r.content.decode("utf-8")
        except UnicodeDecodeError:
            pagina = r.content.decode("latin-1")
        aviso = re.search(r'class="validacion"[^>]*>(.*?)</span>', pagina,
                          re.S)
        if aviso:
            texto = html.unescape(re.sub(r"<[^>]+>", " ", aviso.group(1)))
            texto = " ".join(texto.split())
            estado = ("codigo_incorrecto" if "seguridad" in texto.lower()
                      else "error")
            return {"estado": estado, "texto": texto, "pagina": None}
        return {"estado": "respuesta", "texto": _texto_de_pagina(pagina),
                "pagina": _guardar_pagina(pagina, pdf.stem)}


def _texto_de_pagina(pagina: str) -> str:
    """Extrae el texto del cuerpo de una página de VALIDe, por líneas."""
    m = re.search(r'<div id="cuerpo">(.*?)<div id="contenidoBottom">',
                  pagina, re.S)
    t = m.group(1) if m else pagina
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = re.sub(r"<(script|style)\b.*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r"</t[dh]>", " | ", t, flags=re.I)
    t = re.sub(r"<br\s*/?>|</(p|div|tr|li|h\d|table|fieldset)>", "\n", t,
               flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    lineas = (" ".join(x.split()).strip(" |") for x in t.splitlines())
    return "\n".join(x for x in lineas if x)


def _guardar_pagina(pagina: str, nombre: str) -> Path:
    """Guarda la respuesta de VALIDe para verla en el navegador.

    Va a la carpeta temporal del usuario (en memoria y privada cuando existe
    XDG_RUNTIME_DIR), con una base para que carguen sus estilos.
    """
    carpeta = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
    destino = carpeta / f"valide-{nombre}.html"
    pagina = re.sub(r"<head>", '<head><base href="https://valide.redsara.es/">',
                    pagina, count=1, flags=re.I)
    destino.write_text(pagina, encoding="utf-8")
    destino.chmod(0o600)
    return destino


def abrir(destino: str | Path) -> None:
    """Abre un fichero o una dirección con la aplicación del sistema."""
    destino = str(destino)
    if sys.platform.startswith("win"):
        os.startfile(destino)  # noqa: S606
    else:
        orden = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([orden, destino], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)


def abrir_valide() -> None:
    """Abre el formulario de VALIDe en el navegador."""
    abrir(VALIDE)


def valide_terminal(pdf: Path) -> bool:
    """Envía a VALIDe desde la terminal, enseñando el código en un visor.

    Args:
        pdf: documento firmado.

    Returns:
        True si VALIDe respondió (su veredicto va en el texto).
    """
    print("el documento se envía a la plataforma @firma (VALIDe)")
    sesion = SesionValide()
    for _ in range(3):
        img = Path(os.environ.get("XDG_RUNTIME_DIR")
                   or tempfile.gettempdir()) / "valide-codigo.jpg"
        img.write_bytes(sesion.captcha())
        abrir(img)
        codigo = input("código de seguridad que ves en la imagen: ")
        r = sesion.enviar(pdf, codigo)
        img.unlink(missing_ok=True)
        if r["estado"] != "codigo_incorrecto":
            break
        print("código incorrecto; otra imagen")
    print(r["texto"])
    if r["pagina"]:
        print(f"página completa: {r['pagina']}")
    return r["estado"] == "respuesta"


def main() -> None:
    """Punto de entrada de la línea de órdenes."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("entrada", type=Path, nargs="?")
    ap.add_argument("--listar", action="store_true",
                    help="enumera los certificados instalados")
    ap.add_argument("--instalado", type=int,
                    help="firma con el certificado N de --listar")
    ap.add_argument("-o", "--salida", type=Path)
    ap.add_argument("--p12", type=Path)
    ap.add_argument("--solo-pie", action="store_true",
                    help="pone el pie sin firmar")
    ap.add_argument("--nombre", help="firmante, con --solo-pie")
    ap.add_argument("--emisor", default="la FNMT-RCM",
                    help="emisor del certificado, con --solo-pie")
    ap.add_argument("--motivo", default="")
    ap.add_argument("--lugar", default="")
    ap.add_argument("--referencia", default="",
                    help="referencia libre: propuesta, expediente, contrato")
    ap.add_argument("--tsa", nargs="?", const=TSA_DEFECTO,
                    help="sello de tiempo; sin URL, el cualificado de "
                         "Sectigo")
    ap.add_argument("--sin-reducir", action="store_true")
    ap.add_argument("--comprobar", action="store_true",
                    help="valida un PDF ya firmado")
    ap.add_argument("--valide", action="store_true",
                    help="envía el PDF a VALIDe (el código lo escribes tú)")
    ap.add_argument("--valide-web", action="store_true",
                    help="abre el formulario de VALIDe en el navegador")
    ap.add_argument("--revocacion", default="hard-fail",
                    choices=["hard-fail", "soft-fail"])
    a = ap.parse_args()
    if a.listar:
        for n, c in enumerate(almacenes.listar(), start=1):
            print(f"{n}. {c['nombre']} · {c['emisor']} · caduca "
                  f"{c['caduca']:%d/%m/%Y} · {c['almacen']}")
        return
    if not a.entrada:
        ap.error("falta el documento")
    if a.comprobar or a.valide or a.valide_web:
        ok = comprobar(a.entrada, a.revocacion) if a.comprobar else True
        if a.valide:
            ok = valide_terminal(a.entrada) and ok
        if a.valide_web:
            print(f"VALIDe: sube {a.entrada.resolve()}")
            abrir_valide()
        sys.exit(0 if ok else 1)
    sufijo = "_pie.pdf" if a.solo_pie else "_firmado.pdf"
    salida = a.salida or a.entrada.with_name(a.entrada.stem + sufijo)

    if a.solo_pie:
        if not a.nombre:
            sys.exit("con --solo-pie hace falta --nombre")
        r = poner_pie(a.entrada, salida, a.nombre, a.emisor,
                      not a.sin_reducir, a.motivo, a.lugar, a.referencia)
        print(f"pie puesto: {salida}  (id {r['id']})")
        print(f"recuadro de la última página, en puntos: {r['caja']}")
        return
    clave = os.environ.get("FIRMA_P12_CLAVE")
    if a.instalado:
        c = almacenes.listar()[a.instalado - 1]
        if clave is None and c["pide_clave"]:
            clave = getpass.getpass("Contraseña principal del navegador "
                                    "(Intro si no tiene): ")
        p12, clave_b = almacenes.exportar(c, clave or "")
    elif a.p12:
        clave = clave or getpass.getpass("Contraseña del certificado: ")
        p12, clave_b = a.p12, clave.encode()
    else:
        sys.exit("falta --p12 o --instalado (o --solo-pie)")
    r = firmar_documento(a.entrada, salida, p12, clave_b, a.motivo,
                         a.lugar, a.tsa, not a.sin_reducir, a.referencia)
    print(f"firmado: {salida}  (id {r['id']}, {r['paginas']} páginas)")


if __name__ == "__main__":
    main()
