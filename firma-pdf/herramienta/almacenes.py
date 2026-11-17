"""Certificados personales instalados en el sistema, en los tres sistemas.

- Linux: bases NSS de Firefox y Chrome (certutil y pk12util, paquete
  libnss3-tools).
- Windows: almacén personal del usuario (Cert:\\CurrentUser\\My), el que usan
  Edge y Chrome, leído con PowerShell y .NET.
- macOS: llavero del usuario, con la orden «security»; macOS pide permiso
  para exportar cada clave.

En los tres casos la clave privada sale del almacén a la memoria del
proceso, dentro de un PKCS#12 con una contraseña aleatoria de un solo uso, y
se descarta tras firmar; no se escribe en disco, pero tampoco queda confinada
en el almacén. Si el certificado se instaló como no exportable, hay que usar
un fichero .p12 o .pfx.

Las contraseñas no viajan en la línea de órdenes, que otros procesos del
mismo usuario pueden leer: en Linux van por tuberías, y en Windows dentro del
guion, que PowerShell lee de su entrada estándar. En macOS «security export»
solo admite la contraseña de un solo uso como argumento; protege bytes que
van directos a la tubería de este proceso.
"""
import os
import re
import secrets
import subprocess
import sys
import threading
import warnings
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption, pkcs12,
)

ES_WINDOWS = sys.platform.startswith("win")
ES_MAC = sys.platform == "darwin"
# en Windows, sin ventana de consola al llamar a PowerShell
SIN_CONSOLA = 0x08000000 if ES_WINDOWS else 0

# bases NSS donde los navegadores de Linux guardan los certificados
ALMACENES_NSS = [
    ("Firefox", Path.home() / ".mozilla/firefox"),
    ("Firefox (snap)", Path.home() / "snap/firefox/common/.mozilla/firefox"),
    ("Chrome", Path.home() / ".pki/nssdb"),
]


def datos_de_cert(cert: x509.Certificate) -> dict:
    """Nombre, emisor, caducidad y huella de un certificado.

    El CN de los certificados de la FNMT lleva el DNI, así que el nombre se
    compone con los atributos de nombre y apellidos, que no lo llevan.

    Args:
        cert: certificado X.509.

    Returns:
        Diccionario con «nombre», «emisor», «emisor_cn», «serie» (en
        hexadecimal), «caduca» (UTC) y «huella».
    """
    from cryptography.x509.oid import NameOID

    sujeto, emisor = cert.subject, cert.issuer

    def attr(nombre, oid):
        v = nombre.get_attributes_for_oid(oid)
        return v[0].value if v else ""

    nombre = " ".join(
        x for x in (attr(sujeto, NameOID.GIVEN_NAME),
                    attr(sujeto, NameOID.SURNAME)) if x
    )
    if not nombre:
        # sin nombre y apellidos se toma el CN sin la parte del documento
        nombre = attr(sujeto, NameOID.COMMON_NAME).split(" - ")[0]
    emisor_txt = (attr(emisor, NameOID.ORGANIZATION_NAME)
                  or attr(emisor, NameOID.COMMON_NAME))
    if "FNMT" in emisor_txt.upper():
        emisor_txt = "la FNMT-RCM"
    return {"nombre": nombre.title(), "emisor": emisor_txt,
            "emisor_cn": attr(emisor, NameOID.COMMON_NAME) or emisor_txt,
            "serie": f"{cert.serial_number:X}",
            "caduca": cert.not_valid_after_utc,
            "huella": cert.fingerprint(hashes.SHA256()).hex()}


def _reempaquetar(clave, cert, otros) -> tuple[bytes, bytes]:
    """Empaqueta clave y certificados en un PKCS#12 DER en memoria."""
    nueva = secrets.token_urlsafe(24).encode()
    der = pkcs12.serialize_key_and_certificates(
        b"firma", clave, cert, otros or None, BestAvailableEncryption(nueva))
    return der, nueva


def _ejecutar(orden: list, **kw) -> subprocess.CompletedProcess:
    """Ejecuta una orden sin consola y con salida capturada.

    Sin «input», la entrada estándar va vacía.
    """
    if "input" not in kw:
        kw["stdin"] = subprocess.DEVNULL
    return subprocess.run(orden, capture_output=True, timeout=120,
                          creationflags=SIN_CONSOLA, **kw)


# linux: nss ---------------------------------------------------------------

def _listar_nss() -> list[dict]:
    """Certificados con clave privada de las bases NSS."""
    lista = []
    for etiqueta, base in ALMACENES_NSS:
        bds = ([base] if (base / "cert9.db").exists()
               else sorted(p.parent for p in base.glob("*/cert9.db")))
        for bd in bds:
            r = _ejecutar(["certutil", "-L", "-d", f"sql:{bd}"], text=True)
            for linea in r.stdout.splitlines():
                partes = linea.rstrip().rsplit(None, 1)
                # los certificados propios llevan «u» (clave privada)
                if len(partes) != 2 or "u" not in partes[1].split(","):
                    continue
                nick = partes[0].strip()
                pem = _ejecutar(["certutil", "-L", "-d", f"sql:{bd}",
                                 "-n", nick, "-a"]).stdout
                try:
                    cert = x509.load_pem_x509_certificate(pem)
                except ValueError:
                    continue
                d = datos_de_cert(cert)
                d.update(almacen=etiqueta, tipo="nss", bd=str(bd), nick=nick,
                         pide_clave=True,
                         rotulo_clave="Contraseña principal",
                         ayuda_clave="la del navegador; vacía si no tiene")
                lista.append(d)
    return lista


def _tuberia_con(texto: str) -> tuple[int, int]:
    """Tubería cuyo extremo de lectura entrega el texto y luego fin.

    Las contraseñas caben de sobra en el búfer de la tubería, así que se
    escriben antes de lanzar la orden.
    """
    r, w = os.pipe()
    os.write(w, texto.encode() + b"\n")
    os.close(w)
    return r, w


def _exportar_nss(d: dict, clave: str) -> tuple[bytes, bytes]:
    """Saca el certificado de una base NSS a memoria.

    pk12util lee la contraseña principal (-k) y la del PKCS#12 (-w) de
    ficheros, que aquí son tuberías: no aparecen en la línea de órdenes. El
    PKCS#12 sale por otra tubería, separado de los mensajes de pk12util.
    """
    temporal = secrets.token_urlsafe(24)
    r_k, _ = _tuberia_con(clave)
    r_w, _ = _tuberia_con(temporal)
    r_o, w_o = os.pipe()
    trozos: list[bytes] = []

    def leer():
        with os.fdopen(r_o, "rb") as fh:
            trozos.append(fh.read())

    hilo = threading.Thread(target=leer, daemon=True)
    hilo.start()
    try:
        proc = subprocess.Popen(
            ["pk12util", "-o", f"/dev/fd/{w_o}", "-n", d["nick"],
             "-d", f"sql:{d['bd']}", "-k", f"/dev/fd/{r_k}",
             "-w", f"/dev/fd/{r_w}"],
            pass_fds=(r_k, r_w, w_o), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    finally:
        for fd in (r_k, r_w, w_o):
            os.close(fd)
    salida, err = proc.communicate(timeout=120)
    hilo.join(timeout=120)
    datos = trozos[0] if trozos else b""
    if proc.returncode != 0 or not datos:
        error = (err or salida).decode(errors="replace").strip()
        if "PASSWORD" in error.upper() or "authenticate" in error:
            raise ValueError("contraseña principal del navegador incorrecta")
        raise ValueError(f"no se pudo leer el certificado: {error[-200:]}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        k, c, otros = pkcs12.load_key_and_certificates(datos,
                                                       temporal.encode())
    return _reempaquetar(k, c, otros)


# windows: almacén personal --------------------------------------------------

def _powershell(script: str) -> str:
    """Ejecuta un guion de PowerShell y devuelve su salida.

    El guion entra por la entrada estándar («-Command -»), no como
    argumento: así lo que lleve dentro no aparece en la línea de órdenes.
    """
    r = _ejecutar(["powershell", "-NoProfile", "-NonInteractive",
                   "-ExecutionPolicy", "Bypass", "-Command", "-"],
                  input=script + "\n", text=True)
    if r.returncode != 0:
        raise ValueError(r.stderr.strip()[-300:] or "PowerShell falló")
    return r.stdout


def _listar_windows() -> list[dict]:
    """Certificados con clave privada del almacén personal de Windows."""
    salida = _powershell(
        "Get-ChildItem Cert:\\CurrentUser\\My | "
        "Where-Object { $_.HasPrivateKey } | ForEach-Object { "
        "$_.Thumbprint + '|' + [Convert]::ToBase64String($_.RawData) }")
    lista = []
    for linea in salida.splitlines():
        if "|" not in linea:
            continue
        huella_sha1, b64 = linea.strip().split("|", 1)
        try:
            import base64
            cert = x509.load_der_x509_certificate(base64.b64decode(b64))
        except ValueError:
            continue
        d = datos_de_cert(cert)
        d.update(almacen="Windows", tipo="windows", ref=huella_sha1,
                 pide_clave=False, rotulo_clave="Contraseña",
                 ayuda_clave="no hace falta: la pide Windows si procede")
        lista.append(d)
    return lista


def _exportar_windows(d: dict, _clave: str) -> tuple[bytes, bytes]:
    """Exporta el certificado del almacén de Windows a memoria."""
    import base64

    if not re.fullmatch(r"[0-9A-Fa-f]{40}", d["ref"]):
        raise ValueError("huella de certificado no válida")
    temporal = secrets.token_urlsafe(24)
    try:
        b64 = _powershell(
            f"$c = Get-Item 'Cert:\\CurrentUser\\My\\{d['ref']}'; "
            "$b = $c.Export([System.Security.Cryptography.X509Certificates."
            f"X509ContentType]::Pkcs12, '{temporal}'); "
            "[Convert]::ToBase64String($b)")
    except ValueError as e:
        if "not valid" in str(e).lower() or "export" in str(e).lower():
            raise ValueError("Windows no deja exportar la clave de este "
                             "certificado (no exportable): usa un fichero "
                             ".pfx") from e
        raise
    datos = base64.b64decode(b64.strip())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        k, c, otros = pkcs12.load_key_and_certificates(datos,
                                                       temporal.encode())
    return _reempaquetar(k, c, otros)


# macos: llavero -------------------------------------------------------------

def _listar_mac() -> list[dict]:
    """Identidades (certificado con clave) del llavero de macOS."""
    ids = _ejecutar(["security", "find-identity", "-v"], text=True).stdout
    sha1s = set(re.findall(r"\)\s+([0-9A-F]{40})\s", ids))
    todos = _ejecutar(["security", "find-certificate", "-a", "-Z", "-p"],
                      text=True).stdout
    lista, vistos = [], set()
    for bloque in re.split(r"(?=SHA-256 hash:)", todos):
        m = re.search(r"SHA-1 hash:\s*([0-9A-F]{40})", bloque)
        pem = re.search(r"-----BEGIN CERTIFICATE-----.*?-----END "
                        r"CERTIFICATE-----", bloque, re.S)
        if not (m and pem) or m.group(1) not in sha1s or m.group(1) in vistos:
            continue
        vistos.add(m.group(1))
        cert = x509.load_pem_x509_certificate(pem.group(0).encode())
        d = datos_de_cert(cert)
        d.update(almacen="Llavero", tipo="mac", ref=m.group(1),
                 pide_clave=False, rotulo_clave="Contraseña",
                 ayuda_clave="no hace falta: la pide macOS si procede")
        lista.append(d)
    return lista


def _exportar_mac(d: dict, _clave: str) -> tuple[bytes, bytes]:
    """Exporta las identidades del llavero y se queda con la elegida.

    «security export» saca todas las identidades a la salida estándar; macOS
    pide permiso para cada clave. openssl las separa y se empareja la clave
    con el certificado elegido por su clave pública.
    """
    temporal = secrets.token_urlsafe(24)
    r = _ejecutar(["security", "export", "-t", "identities", "-f", "pkcs12",
                   "-P", temporal])
    if r.returncode != 0 or not r.stdout:
        raise ValueError("macOS no ha permitido exportar la clave: "
                         + r.stderr.decode(errors="replace").strip()[-200:])
    entorno = dict(os.environ, FIRMA_TMP=temporal)
    pem = subprocess.run(
        ["openssl", "pkcs12", "-nodes", "-passin", "env:FIRMA_TMP"],
        input=r.stdout, capture_output=True, env=entorno, timeout=60).stdout
    certs = [x509.load_pem_x509_certificate(b) for b in re.findall(
        rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", pem,
        re.S)]
    claves = [serialization.load_pem_private_key(b, None) for b in re.findall(
        rb"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----.*?-----END (?:RSA |EC )?"
        rb"PRIVATE KEY-----", pem, re.S)]
    def spki(obj) -> bytes:
        return obj.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo)

    def sha1(c) -> str:
        return c.fingerprint(hashes.SHA1()).hex().upper()

    elegido = next((c for c in certs if sha1(c) == d["ref"]), None)
    if elegido is None:
        raise ValueError("el certificado elegido no salió del llavero")
    clave = next((k for k in claves if spki(k) == spki(elegido)), None)
    if clave is None:
        raise ValueError("no se encontró la clave del certificado elegido")
    otros = [c for c in certs if c is not elegido]
    return _reempaquetar(clave, elegido, otros)


# interfaz común -------------------------------------------------------------

def listar() -> list[dict]:
    """Certificados con clave privada instalados en este sistema.

    Un mismo certificado presente en varios almacenes aparece una vez.

    Returns:
        Lista de diccionarios con «nombre», «emisor», «caduca», «huella»,
        «almacen», «tipo», «pide_clave», «rotulo_clave» y «ayuda_clave».

    Raises:
        FileNotFoundError: si falta la herramienta del sistema.
    """
    if ES_WINDOWS:
        crudos = _listar_windows()
    elif ES_MAC:
        crudos = _listar_mac()
    else:
        crudos = _listar_nss()
    vistos, lista = set(), []
    for d in crudos:
        if d["huella"] not in vistos:
            vistos.add(d["huella"])
            lista.append(d)
    return lista


def exportar(d: dict, clave: str = "") -> tuple[bytes, bytes]:
    """Saca a memoria el certificado elegido con su clave privada.

    Args:
        d: elemento devuelto por listar().
        clave: contraseña principal (solo NSS).

    Returns:
        El PKCS#12 en bytes y su contraseña de un solo uso.
    """
    funcion = {"nss": _exportar_nss, "windows": _exportar_windows,
               "mac": _exportar_mac}[d["tipo"]]
    return funcion(d, clave)
