#!/usr/bin/env python3
"""Mediciones del laboratorio «un PAM mínimo con software libre».

Corre dentro del servicio ``medidor`` del compose, en la red interna, con las
credenciales de laboratorio que ``laboratorio.sh medir`` le pasa por entorno,
y escribe los CSV en el directorio de la medición (montado en /salida). Cada
prueba anota qué se esperaba, qué pasó y cuánto tardó.

Bloques, en orden:
  1. bastión SSH: contraseña y TOTP, orden ejecutada y grabada; TOTP erróneo
     y sin TOTP, rechazados;
  2. certificados SSH: la bóveda firma para «operador» y no para «root» ni
     más allá del TTL máximo; el objetivo acepta el certificado y lo rechaza
     al caducar;
  3. credenciales dinámicas de PostgreSQL: se crean, leen, no escriben, se
     revocan antes de tiempo y caducan solas;
  4. bastión PostgreSQL: la usuaria entra con su contraseña y el bastión toma
     la de la base de datos de la bóveda;
  5. límites de las políticas: lo que el bastión y la operadora no pueden
     pedir;
  6. rotación: la contraseña original del administrador de la base de datos
     ya no vale;
  7. grabaciones y sesiones del bastión.
"""
import base64
import csv
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import re
import ssl
import struct
import subprocess
import time
import urllib.error
import urllib.request

import paramiko
import psycopg
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SALIDA = "/salida"
BAO = os.environ["BAO_ADDR"]
CA_BAO = os.environ["BAO_CACERT"]
WG_URL = os.environ.get("WARPGATE_URL", "https://warpgate:8888")
WG_SSH = ("warpgate", 2222)
WG_PG = ("warpgate", 55432)
ANA = os.environ["ANA_USUARIO"]
ANA_CLAVE_BASTION = os.environ["ANA_CLAVE_BASTION"]
ANA_TOTP = os.environ["ANA_TOTP_B32"]
ANA_CLAVE_BAO = os.environ["ANA_CLAVE_BAO"]
BASTION_ROLE_ID = os.environ["BASTION_ROLE_ID"]
BASTION_SECRET_ID = os.environ["BASTION_SECRET_ID"]
PG_ADMIN_ORIGINAL = os.environ["PG_ADMIN_ORIGINAL"]
WG_TOKEN = os.environ["WARPGATE_ADMIN_TOKEN"]
TTL_CERT_DIRECTO = os.environ.get("TTL_CERT_DIRECTO", "2m")
ORDEN_BASTION = "id; hostname; cat /etc/os-release | head -1"

CTX_BAO = ssl.create_default_context(cafile=CA_BAO)
CTX_WG = ssl.create_default_context()
CTX_WG.check_hostname = False
CTX_WG.verify_mode = ssl.CERT_NONE  # certificado autofirmado del bastión

PRUEBAS: list[dict] = []
ABIERTO: dict = {}  # conexiones abiertas antes de caducar, para probarlas después
CERTIFICADOS: list[dict] = []
CREDENCIALES: list[dict] = []


# ---------------------------------------------------------------- utilidades
def ahora() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def anota(bloque: str, prueba: str, esperado: str, resultado: str, ok: bool,
          ms: float, detalle: str = "") -> None:
    """Guarda una fila de pruebas.csv y la imprime."""
    limpio = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", detalle)  # sin colores ANSI
    fila = dict(instante=ahora(), bloque=bloque, prueba=prueba,
                esperado=esperado, resultado=resultado, ok=int(bool(ok)),
                ms=round(ms), detalle=" ".join(limpio.split())[:300])
    PRUEBAS.append(fila)
    marca = "ok" if ok else "XX"
    print(f"[{marca}] {bloque} · {prueba}: {resultado} ({fila['ms']} ms) "
          f"{fila['detalle'][:120]}", flush=True)


def http(url: str, datos=None, cab: dict | None = None, ctx=None,
         metodo: str | None = None) -> tuple[int, object]:
    cuerpo = None if datos is None else json.dumps(datos).encode()
    metodo = metodo or ("POST" if cuerpo is not None else "GET")
    req = urllib.request.Request(url, data=cuerpo, method=metodo)
    req.add_header("Content-Type", "application/json")
    for k, v in (cab or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            crudo = r.read()
            return r.status, (json.loads(crudo) if crudo else None)
    except urllib.error.HTTPError as e:
        crudo = e.read()
        try:
            return e.code, (json.loads(crudo) if crudo else None)
        except ValueError:
            return e.code, {"texto": crudo.decode(errors="replace")[:300]}


def bao(ruta: str, datos=None, token: str | None = None,
        metodo: str | None = None) -> tuple[int, object]:
    cab = {"X-Vault-Token": token} if token else {}
    return http(f"{BAO}/v1/{ruta}", datos, cab, CTX_BAO, metodo)


def wg_admin(ruta: str) -> tuple[int, object]:
    return http(f"{WG_URL}/@warpgate/admin/api/{ruta}", None,
                {"X-Warpgate-Token": WG_TOKEN}, CTX_WG)


def errores(resp) -> str:
    if isinstance(resp, dict):
        return "; ".join(resp.get("errors") or [resp.get("texto", "")])
    return str(resp)[:200]


def totp(b32: str, instante: float | None = None) -> str:
    """TOTP de seis dígitos, SHA-1 y paso de 30 s (RFC 6238), que es lo que
    comprueba Warpgate."""
    clave = base64.b32decode(b32.upper() + "=" * (-len(b32) % 8))
    contador = int((instante or time.time()) // 30)
    resumen = hmac.new(clave, struct.pack(">Q", contador), hashlib.sha1)
    resumen = resumen.digest()
    desplaz = resumen[-1] & 0x0F
    numero = struct.unpack(">I", resumen[desplaz:desplaz + 4])[0] & 0x7FFFFFFF
    return f"{numero % 10**6:06d}"


def cronometro():
    t0 = time.perf_counter()
    return lambda: (time.perf_counter() - t0) * 1000


# ----------------------------------------------------------- bastión por SSH
ASKPASS = "/tmp/askpass.py"


def escribir_askpass() -> None:
    """Guion que ssh invoca sin terminal para cada aviso: devuelve la
    contraseña o el TOTP según el texto del aviso, y solo contesta el TOTP
    una vez, para que cada intento cuente como uno en la protección contra
    fuerza bruta del bastión."""
    with open(ASKPASS, "w") as f:
        f.write(
            "#!/usr/bin/env python3\n"
            "import os, signal, sys\n"
            "texto = sys.argv[1] if len(sys.argv) > 1 else ''\n"
            "contador = os.environ['MEDIDOR_CONTADOR']\n"
            "if 'ne-time' in texto or 'OTP' in texto:\n"
            "    n = int(open(contador).read() or 0) + 1\n"
            "    open(contador, 'w').write(str(n))\n"
            "    if n > 1:\n"
            "        # el bastión vuelve a preguntar tras un código erróneo;\n"
            "        # como haría una persona, el cliente se rinde al primero\n"
            "        os.kill(os.getppid(), signal.SIGTERM)\n"
            "        sys.exit(1)\n"
            "    print(os.environ.get('MEDIDOR_CODIGO', ''))\n"
            "else:\n"
            "    print(os.environ.get('MEDIDOR_CLAVE', ''))\n")
    os.chmod(ASKPASS, 0o755)


def ssh_bastion(objetivo: str, clave: str, codigo: str | None,
                orden: str = ORDEN_BASTION) -> tuple[bool, str, str]:
    """Entra por el bastión como ana:<objetivo> con el ssh de OpenSSH, que
    da la contraseña por el método «password» y el TOTP por
    keyboard-interactive, y ejecuta una orden con pty (es lo que graba el
    bastión). Devuelve (autenticado, salida, error)."""
    contador = "/tmp/askpass.contador"
    with open(contador, "w") as f:
        f.write("0")
    entorno = dict(os.environ, SSH_ASKPASS=ASKPASS, SSH_ASKPASS_REQUIRE="force",
                   DISPLAY=":0", MEDIDOR_CLAVE=clave, MEDIDOR_CODIGO=codigo or "",
                   MEDIDOR_CONTADOR=contador)
    try:
        r = subprocess.run(
            ["ssh", "-p", str(WG_SSH[1]), "-tt",
             "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
             "-o", "PreferredAuthentications=password,keyboard-interactive",
             "-o", "NumberOfPasswordPrompts=1", "-o", "ConnectTimeout=20",
             "-o", "LogLevel=ERROR", f"{ANA}:{objetivo}@{WG_SSH[0]}", orden],
            env=entorno, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, "", "tiempo agotado"
    err = " ".join(r.stderr.split())[-200:]
    return r.returncode == 0, r.stdout, err


def desbloquear() -> None:
    """Preparación: levanta los bloqueos por fuerza bruta que dejaran
    ejecuciones anteriores, para que la medición parta de cero."""
    cod, ips = wg_admin("login-protection/blocked-ips")
    for ip in (ips or []) if cod == 200 else []:
        http(f"{WG_URL}/@warpgate/admin/api/login-protection/blocked-ips",
             {"ip": ip.get("ip_address")}, {"X-Warpgate-Token": WG_TOKEN},
             CTX_WG, "DELETE")
    http(f"{WG_URL}/@warpgate/admin/api/login-protection/locked-users/{ANA}",
         None, {"X-Warpgate-Token": WG_TOKEN}, CTX_WG, "DELETE")


def bloque_bastion_ssh() -> None:
    b = "bastión SSH"
    ms = cronometro()
    ok, salida, err = ssh_bastion("servidor", ANA_CLAVE_BASTION, totp(ANA_TOTP))
    bien = ok and "uid=" in salida
    anota(b, "contraseña + TOTP, orden en el servidor", "entra y ejecuta",
          "entra y ejecuta" if bien else "no", bien, ms(),
          salida.strip()[-160:] if ok else err)


def bloque_bastion_ssh_negativo() -> None:
    """Los intentos fallidos van al final de las pruebas del bastión: cada
    uno cuenta en su protección contra fuerza bruta, que bloquea la IP a los
    cinco fallos en quince minutos."""
    b = "bastión SSH"
    ms = cronometro()
    ok, _, err = ssh_bastion("servidor", ANA_CLAVE_BASTION, "000000")
    anota(b, "contraseña correcta, TOTP erróneo", "rechazado",
          "entra" if ok else "rechazado", not ok, ms(), err)
    ms = cronometro()
    ok, _, err = ssh_bastion("servidor", ANA_CLAVE_BASTION, None)
    anota(b, "contraseña correcta, sin TOTP", "rechazado",
          "entra" if ok else "rechazado", not ok, ms(), err)
    cod, estado = wg_admin("login-protection/status")
    anota(b, "protección contra fuerza bruta tras los dos fallos",
          "cuenta los intentos", f"HTTP {cod}", cod == 200, 0,
          json.dumps(estado, ensure_ascii=False) if estado else "")
    # tres fallos más, hasta cinco en el cuarto de hora: el bastión bloquea
    # la IP y el administrador la desbloquea por la API
    ms = cronometro()
    for _ in range(3):
        ssh_bastion("servidor", ANA_CLAVE_BASTION, "000000")
    cod, ips = wg_admin("login-protection/blocked-ips")
    bloqueadas = (ips or []) if cod == 200 else []
    anota(b, "tres fallos más (cinco en total): IP bloqueada", "1 bloqueada",
          f"{len(bloqueadas)} bloqueada(s)", len(bloqueadas) == 1, ms(),
          "; ".join(f"{ip.get('reason', '')} hasta {ip.get('expires_at', '')}"
                    for ip in bloqueadas)[:200])
    ms = cronometro()
    ok, _, err = ssh_bastion("servidor", ANA_CLAVE_BASTION, totp(ANA_TOTP))
    anota(b, "contraseña y TOTP correctos con la IP bloqueada", "rechazado",
          "entra" if ok else "rechazado", not ok, ms(), err)
    desbloquear()
    anota(b, "desbloqueo por el administrador (API)", "sin bloqueos",
          f"{len(wg_admin('login-protection/blocked-ips')[1] or [])} bloqueada(s)",
          True, 0)


# ------------------------------------------------------- certificados SSH
def clave_efimera() -> tuple[paramiko.Ed25519Key, str]:
    priv = Ed25519PrivateKey.generate()
    pem = priv.private_bytes(serialization.Encoding.PEM,
                             serialization.PrivateFormat.OpenSSH,
                             serialization.NoEncryption()).decode()
    pub = priv.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                         serialization.PublicFormat.OpenSSH)
    return paramiko.Ed25519Key.from_private_key(io.StringIO(pem)), pub.decode()


def campos_certificado(cert: str) -> dict:
    """Lee tipo, serie, key_id, principales y validez de un certificado
    OpenSSH (PROTOCOL.certkeys) sin dependencias."""
    datos = base64.b64decode(cert.split()[1])
    pos = 0

    def cadena() -> bytes:
        nonlocal pos
        n = struct.unpack(">I", datos[pos:pos + 4])[0]
        pos += 4
        v = datos[pos:pos + n]
        pos += n
        return v

    def u64() -> int:
        nonlocal pos
        v = struct.unpack(">Q", datos[pos:pos + 8])[0]
        pos += 8
        return v

    tipo = cadena().decode()
    cadena()  # nonce
    cadena()  # clave pública
    serie = u64()
    pos += 4  # tipo de certificado (usuario = 1)
    key_id = cadena().decode()
    blob = cadena()
    principales, p = [], 0
    while p < len(blob):
        n = struct.unpack(">I", blob[p:p + 4])[0]
        p += 4
        principales.append(blob[p:p + n].decode())
        p += n
    desde, hasta = u64(), u64()
    return dict(tipo=tipo, serie=serie, key_id=key_id,
                principales=" ".join(principales), valido_desde=desde,
                valido_hasta=hasta)


def ssh_directo(pkey: paramiko.PKey) -> tuple[bool, str, str]:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        c.connect("objetivo-ssh", 22, username="operador", pkey=pkey,
                  look_for_keys=False, allow_agent=False, timeout=15,
                  banner_timeout=15, auth_timeout=15)
        _, out, _ = c.exec_command("id")
        return True, out.read().decode().strip(), ""
    except paramiko.AuthenticationException as e:
        return False, "", f"rechazado: {e}"
    except Exception as e:
        return False, "", f"{type(e).__name__}: {e}"
    finally:
        c.close()


def token_ana() -> str:
    cod, resp = bao(f"auth/userpass/login/{ANA}", {"password": ANA_CLAVE_BAO})
    if cod != 200:
        raise RuntimeError(f"login userpass {cod}: {errores(resp)}")
    return resp["auth"]["client_token"]


def firmar(token: str, pub: str, principal: str, ttl: str, key_id: str):
    return bao("ssh-ca/sign/operador",
               {"public_key": pub, "valid_principals": principal, "ttl": ttl,
                "cert_type": "user", "key_id": key_id}, token)


def bloque_certificados() -> tuple[paramiko.PKey, int]:
    b = "certificados SSH"
    tok = token_ana()
    pkey, pub = clave_efimera()
    ms = cronometro()
    cod, resp = firmar(tok, pub, "root", TTL_CERT_DIRECTO, f"medidor:{ANA}")
    anota(b, "firmar para «root»", "la bóveda lo rechaza",
          f"HTTP {cod}", cod == 400, ms(), errores(resp))
    ms = cronometro()
    cod, resp = firmar(tok, pub, "operador", "1h", f"medidor:{ANA}")
    anota(b, "firmar con TTL de 1 h (máximo del rol: 15 min)",
          "la bóveda lo rechaza", f"HTTP {cod}", cod == 400, ms(),
          errores(resp))
    ms = cronometro()
    cod, resp = firmar(tok, pub, "operador", TTL_CERT_DIRECTO, f"medidor:{ANA}")
    t_firma = ms()
    if cod != 200:
        anota(b, f"firmar para «operador», TTL {TTL_CERT_DIRECTO}", "certificado",
              f"HTTP {cod}", False, t_firma, errores(resp))
        raise RuntimeError("sin certificado")
    cert = resp["data"]["signed_key"].strip()
    campos = campos_certificado(cert)
    campos.update(camino="directo", emitido=ahora(), ms_firma=round(t_firma),
                  ttl_pedido=TTL_CERT_DIRECTO)
    CERTIFICADOS.append(campos)
    anota(b, f"firmar para «operador», TTL {TTL_CERT_DIRECTO}", "certificado",
          "certificado", True, t_firma,
          f"{campos['tipo']} key_id={campos['key_id']} "
          f"principales={campos['principales']} "
          f"válido {campos['valido_hasta'] - campos['valido_desde']} s")
    pkey.load_certificate(cert)
    ms = cronometro()
    ok, salida, err = ssh_directo(pkey)
    anota(b, "entrar en el servidor con el certificado", "entra",
          "entra" if ok else "rechazado", ok, ms(), salida or err)
    # una segunda sesión se deja abierta para ver qué pasa al caducar
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect("objetivo-ssh", 22, username="operador", pkey=pkey,
                  look_for_keys=False, allow_agent=False, timeout=15)
        c.get_transport().set_keepalive(20)
        ABIERTO["ssh"] = c
    except Exception as e:
        anota(b, "dejar una sesión abierta antes de caducar", "abierta", "no",
              False, 0, f"{type(e).__name__}: {e}")
    ms = cronometro()
    ok, _, err = ssh_directo(clave_efimera()[0])
    anota(b, "entrar con una clave sin certificado", "rechazado",
          "entra" if ok else "rechazado", not ok, ms(), err)
    return pkey, campos["valido_hasta"]


def caducidad_certificado(pkey: paramiko.PKey, valido_hasta: int) -> None:
    b = "certificados SSH"
    espera = valido_hasta + 5 - time.time()
    if espera > 0:
        print(f"... esperando {espera:.0f} s a que caduque el certificado",
              flush=True)
        time.sleep(espera)
    ms = cronometro()
    ok, _, err = ssh_directo(pkey)
    anota(b, "entrar con el certificado caducado", "rechazado",
          "entra" if ok else "rechazado", not ok, ms(),
          f"{time.time() - valido_hasta:.0f} s después de la caducidad; {err}")
    c = ABIERTO.get("ssh")
    if c is not None:
        ms = cronometro()
        try:
            _, out, _ = c.exec_command("id", timeout=15)
            salida = out.read().decode().strip()
            viva = "uid=" in salida
            det = salida
        except Exception as e:
            viva, det = False, f"{type(e).__name__}: {e}"
        anota(b, "orden en la sesión abierta antes de caducar",
              "sigue viva (sshd solo comprueba el certificado al entrar)",
              "sigue viva" if viva else "cerrada", viva, ms(),
              f"{time.time() - valido_hasta:.0f} s después de la caducidad; {det}")
        c.close()


# ------------------------------------------------- credenciales dinámicas
def pg(usuario: str, clave: str, host: str = "postgres", port: int = 5432,
       sslmode: str = "disable", escribir: bool = False
       ) -> tuple[bool, str, float]:
    ms = cronometro()
    consulta = ("INSERT INTO salarios (comunidad, ocupacion, sexo, periodo, "
                "ganancia_media_anual, muestra_pequena) "
                "VALUES ('prueba', 'prueba', 'prueba', 2099, 1, false)"
                if escribir else
                "SELECT count(*), round(avg(ganancia_media_anual)) "
                "FROM salarios WHERE periodo = 2024")
    try:
        with psycopg.connect(host=host, port=port, dbname="salarios",
                             user=usuario, password=clave, sslmode=sslmode,
                             connect_timeout=15) as con:
            with con.cursor() as cur:
                cur.execute(consulta)
                fila = None if escribir else cur.fetchone()
            if escribir:
                con.rollback()
        return True, (f"{fila[0]} filas de 2024, media {fila[1]} €" if fila
                      else "escrito"), ms()
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e).strip()[:200]}", ms()


def credencial(tok: str, etiqueta: str) -> dict:
    ms = cronometro()
    cod, resp = bao("database/creds/lectura", token=tok)
    t = ms()
    if cod != 200:
        raise RuntimeError(f"creds {cod}: {errores(resp)}")
    fila = dict(etiqueta=etiqueta, emitida=ahora(), ms_emision=round(t),
                lease_id=resp["lease_id"], ttl_s=resp["lease_duration"],
                usuario=resp["data"]["username"], clave=resp["data"]["password"],
                emitida_ts=time.time())
    CREDENCIALES.append(fila)
    return fila


def bloque_credenciales() -> dict:
    b = "credenciales dinámicas"
    tok = token_ana()
    a = credencial(tok, "revocada")
    anota(b, "pedir credenciales de lectura", "usuario y contraseña con TTL",
          f"TTL {a['ttl_s']} s", True, a["ms_emision"],
          f"usuario {a['usuario'][:40]}")
    ok, det, t = pg(a["usuario"], a["clave"])
    anota(b, "leer la tabla con ellas", "lee", "lee" if ok else "no", ok, t, det)
    ok, det, t = pg(a["usuario"], a["clave"], escribir=True)
    anota(b, "escribir en la tabla con ellas", "rechazado",
          "escribe" if ok else "rechazado", not ok, t, det)
    ms = cronometro()
    cod, resp = bao(f"sys/leases/revoke/{a['lease_id']}", {}, tok, "PUT")
    anota(b, "revocar la concesión antes de tiempo", "HTTP 204",
          f"HTTP {cod}", cod in (200, 204), ms(), errores(resp) if resp else "")
    ok, det, t = pg(a["usuario"], a["clave"])
    anota(b, "leer tras la revocación", "rechazado",
          "lee" if ok else "rechazado", not ok, t, det)
    c = credencial(tok, "caducada")
    ok, det, t = pg(c["usuario"], c["clave"])
    anota(b, "segunda credencial, leer", "lee", "lee" if ok else "no", ok, t,
          f"TTL {c['ttl_s']} s; {det}")
    # una conexión se deja abierta para ver qué pasa cuando venza el TTL
    try:
        ABIERTO["pg"] = psycopg.connect(host="postgres", port=5432,
                                        dbname="salarios", user=c["usuario"],
                                        password=c["clave"], sslmode="disable",
                                        connect_timeout=15, autocommit=True)
    except Exception as e:
        anota(b, "dejar una conexión abierta antes del TTL", "abierta", "no",
              False, 0, f"{type(e).__name__}: {e}")
    return c


def caducidad_credencial(c: dict) -> None:
    b = "credenciales dinámicas"
    espera = c["emitida_ts"] + c["ttl_s"] + 20 - time.time()
    if espera > 0:
        print(f"... esperando {espera:.0f} s a que caduque la credencial",
              flush=True)
        time.sleep(espera)
    ok, det, t = pg(c["usuario"], c["clave"])
    anota(b, "leer con la credencial caducada", "rechazado",
          "lee" if ok else "rechazado", not ok, t,
          f"{time.time() - c['emitida_ts'] - c['ttl_s']:.0f} s después del "
          f"TTL; {det}")
    con = ABIERTO.get("pg")
    if con is not None:
        ms = cronometro()
        # VALID UNTIL de PostgreSQL solo afecta a autenticaciones nuevas; lo
        # que corta la conexión abierta son las sentencias de revocación que
        # la bóveda ejecuta al vencer la concesión (quitan los privilegios)
        try:
            with con.cursor() as cur:
                cur.execute("SELECT count(*) FROM salarios")
                n = cur.fetchone()[0]
            resultado, det, bien = "sigue leyendo", f"lee {n} filas", False
        except Exception as e:
            texto = str(e).strip()
            bien = "permission denied" in texto
            resultado = "sin privilegios" if bien else "cortada"
            det = f"{type(e).__name__}: {texto[:160]}"
        anota(b, "consulta en la conexión abierta antes del TTL",
              "sin privilegios (la bóveda los revoca al vencer la concesión)",
              resultado, bien, ms(),
              f"{time.time() - c['emitida_ts'] - c['ttl_s']:.0f} s después del "
              f"TTL; {det}")
        try:
            con.close()
        except Exception:
            pass


# -------------------------------------------------- bastión por PostgreSQL
def bloque_bastion_pg() -> None:
    b = "bastión PostgreSQL"
    ok, det, t = pg(f"{ANA}:salarios", ANA_CLAVE_BASTION, WG_PG[0], WG_PG[1],
                    sslmode="require")
    anota(b, "entrar por el bastión con la contraseña de la usuaria", "lee",
          "lee" if ok else "no", ok, t, det)
    ok, det, t = pg(f"{ANA}:salarios", "incorrecta", WG_PG[0], WG_PG[1],
                    sslmode="require")
    anota(b, "contraseña incorrecta", "rechazado",
          "lee" if ok else "rechazado", not ok, t, det)
    ok, det, t = pg(f"{ANA}:salarios", ANA_CLAVE_BASTION, WG_PG[0], WG_PG[1],
                    sslmode="require", escribir=True)
    anota(b, "escribir a través del bastión", "rechazado (cuenta de lectura)",
          "escribe" if ok else "rechazado", not ok, t, det)


# ------------------------------------------------------- políticas y límites
def bloque_politicas() -> None:
    b = "límites de las políticas"
    cod, resp = bao("auth/approle/login",
                    {"role_id": BASTION_ROLE_ID, "secret_id": BASTION_SECRET_ID})
    if cod != 200:
        anota(b, "entrar como el bastión (AppRole)", "token", f"HTTP {cod}",
              False, 0, errores(resp))
        return
    tb = resp["auth"]["client_token"]
    anota(b, "entrar como el bastión (AppRole)", "token con política «bastion»",
          ", ".join(resp["auth"]["policies"]), True, 0)
    pruebas = [
        (tb, "bastión", "database/creds/lectura", None, "GET", 403),
        (tb, "bastión", "secret/data/bastion/salarios", None, "GET", 200),
        (tb, "bastión", "sys/policies/acl/bastion", None, "GET", 403),
        (tb, "bastión", "ssh-ca/sign/operador",
         {"public_key": clave_efimera()[1], "valid_principals": "root",
          "cert_type": "user"}, "POST", 400),
    ]
    ta = token_ana()
    pruebas += [
        (ta, "operadora", "secret/data/bastion/salarios", None, "GET", 403),
        (ta, "operadora", "sys/policies/acl/operador", None, "GET", 403),
        (ta, "operadora", "database/config/salarios", None, "GET", 403),
    ]
    for tok, quien, ruta, datos, metodo, esperado in pruebas:
        ms = cronometro()
        cod, resp = bao(ruta, datos, tok, metodo)
        anota(b, f"{quien}: {metodo} {ruta}", f"HTTP {esperado}", f"HTTP {cod}",
              cod == esperado, ms(), errores(resp) if cod >= 400 else "")


def bloque_rotacion() -> None:
    ok, det, t = pg("admin_bd", PG_ADMIN_ORIGINAL)
    anota("rotación", "contraseña original del administrador de la base de "
          "datos", "rechazada (la rotó la bóveda)",
          "entra" if ok else "rechazada", not ok, t, det)


# ------------------------------------------------- grabaciones y sesiones
def bloque_grabaciones() -> None:
    raiz = "/warpgate/recordings"
    filas = []
    for carpeta in sorted(os.listdir(raiz)) if os.path.isdir(raiz) else []:
        ruta = os.path.join(raiz, carpeta)
        if not os.path.isdir(ruta):
            continue
        # el bastión graba cada terminal como ndjson: un índice y los trozos
        # de salida (y de teclado, si los hay) en base64 con su instante
        ficheros, octetos, trozos, salida, teclado = [], 0, 0, b"", 0
        for base, _d, fs in os.walk(ruta):
            for f in fs:
                p = os.path.join(base, f)
                octetos += os.path.getsize(p)
                ficheros.append(os.path.relpath(p, ruta))
                if not f.startswith("data"):
                    continue
                with open(p) as fh:
                    for linea in fh:
                        try:
                            e = json.loads(linea)
                        except ValueError:
                            continue
                        if "data" not in e:
                            continue
                        trozos += 1
                        dato = base64.b64decode(e["data"])
                        if e.get("stream") == "Output":
                            salida += dato
                        else:
                            teclado += 1
        filas.append(dict(grabacion=carpeta, ficheros=len(ficheros),
                          octetos=octetos, trozos=trozos,
                          trozos_de_teclado=teclado,
                          contiene_la_salida=int(b"uid=" in salida),
                          nombres=" ".join(sorted(ficheros))[:200]))
    escribir_csv("grabaciones.csv", filas,
                 ["grabacion", "ficheros", "octetos", "trozos",
                  "trozos_de_teclado", "contiene_la_salida", "nombres"])
    anota("grabaciones", "grabaciones en disco del bastión",
          "una por sesión de terminal", f"{len(filas)} grabaciones",
          len(filas) >= 1, 0, f"{sum(f['octetos'] for f in filas)} octetos")
    cod, resp = wg_admin("sessions?limit=200&offset=0")
    sesiones = (resp or {}).get("items", []) if cod == 200 else []
    filas = []
    for s in sesiones:
        objetivos = s.get("target_sessions") or []
        nombre = ""
        for ts in objetivos:
            t = ts.get("target") if isinstance(ts, dict) else None
            nombre = (t.get("name") if isinstance(t, dict) else ts.get("target_name", "")) or nombre
        filas.append(dict(
            id=s.get("id", ""), usuario=s.get("username") or "",
            protocolo=s.get("protocol", ""), objetivo=nombre,
            sesiones_objetivo=len(objetivos),
            inicio=s.get("started", ""), fin=s.get("ended") or ""))
    escribir_csv("sesiones.csv", filas,
                 ["id", "usuario", "protocolo", "objetivo", "sesiones_objetivo",
                  "inicio", "fin"])
    con_usuaria = sum(1 for f in filas if f["usuario"])
    anota("grabaciones", "sesiones registradas por el bastión", "lista",
          f"HTTP {cod}, {len(filas)} sesiones, {con_usuaria} autenticadas",
          cod == 200, 0)


# ---------------------------------------------------------------- salida
def escribir_csv(nombre: str, filas: list[dict], campos: list[str]) -> None:
    with open(os.path.join(SALIDA, nombre), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)


def volcar() -> None:
    escribir_csv("pruebas.csv", PRUEBAS,
                 ["instante", "bloque", "prueba", "esperado", "resultado",
                  "ok", "ms", "detalle"])
    escribir_csv("certificados.csv", CERTIFICADOS,
                 ["camino", "emitido", "ms_firma", "ttl_pedido", "tipo",
                  "serie", "key_id", "principales", "valido_desde",
                  "valido_hasta"])
    escribir_csv("credenciales_bd.csv", CREDENCIALES,
                 ["etiqueta", "emitida", "ms_emision", "lease_id", "ttl_s"])


def principal() -> None:
    inicio = time.time()
    pkey, valido_hasta, cred = None, None, None
    escribir_askpass()
    desbloquear()
    try:
        bloque_bastion_ssh()
        bloque_bastion_pg()
        bloque_bastion_ssh_negativo()
        pkey, valido_hasta = bloque_certificados()
        cred = bloque_credenciales()
        bloque_politicas()
        bloque_rotacion()
        if pkey is not None:
            caducidad_certificado(pkey, valido_hasta)
        if cred is not None:
            caducidad_credencial(cred)
        bloque_grabaciones()
    finally:
        volcar()
        total = sum(1 for p in PRUEBAS)
        bien = sum(p["ok"] for p in PRUEBAS)
        print(f"\n{bien} de {total} pruebas como se esperaba, "
              f"{time.time() - inicio:.0f} s", flush=True)


if __name__ == "__main__":
    principal()
