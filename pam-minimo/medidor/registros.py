#!/usr/bin/env python3
"""Resume los registros del laboratorio desde el anfitrión (solo biblioteca
estándar): la auditoría de OpenBao, el diario de sshd del objetivo, el del
bastión, el esfuerzo por fase, las imágenes y la memoria, y escribe los CSV
y la INSTANTANEA.md junto a las pruebas del medidor.

Uso: registros.py <dir de registros> <fases.csv> <dir de salida>
"""
import collections
import csv
import datetime as dt
import json
import os
import re
import sys

REGISTROS, FASES, SALIDA = sys.argv[1:4]
FICHEROS_CONFIG = [
    "compose.yaml", "laboratorio.sh", "openbao/config.hcl",
    "openbao/rol-ssh-operador.json", "openbao/politicas/bastion.hcl",
    "openbao/politicas/operador.hcl", "objetivo-ssh/Dockerfile",
    "objetivo-ssh/sshd_config", "objetivo-ssh/entrada.sh", "postgres/init.sql",
]


def escribir(nombre: str, filas: list[dict], campos: list[str]) -> None:
    with open(os.path.join(SALIDA, nombre), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)


def leer_csv(nombre: str) -> list[dict]:
    ruta = os.path.join(SALIDA, nombre)
    if not os.path.exists(ruta):
        return []
    with open(ruta, newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------- auditoría OpenBao
def auditoria_openbao() -> list[dict]:
    """Cuenta las respuestas del diario de auditoría por quién pide, qué
    operación y en qué ruta; los errores aparte."""
    cuenta: collections.Counter = collections.Counter()
    ruta = os.path.join(REGISTROS, "openbao-auditoria.jsonl")
    if not os.path.exists(ruta):
        return []
    with open(ruta) as f:
        for linea in f:
            try:
                e = json.loads(linea)
            except ValueError:
                continue
            if e.get("type") != "response":
                continue
            auth = e.get("auth") or {}
            quien = auth.get("display_name") or auth.get("token_type") or "sin token"
            quien = re.sub(r"-[0-9a-f]{8,}.*$", "", quien)
            req = e.get("request") or {}
            camino = re.sub(r"/[A-Za-z0-9_-]{20,}$", "/<id>", req.get("path", ""))
            error = "sí" if e.get("error") else "no"
            cuenta[(quien, req.get("operation", ""), camino, error)] += 1
    filas = [dict(quien=q, operacion=o, ruta=r, error=err, n=n)
             for (q, o, r, err), n in sorted(cuenta.items())]
    escribir("auditoria_openbao.csv", filas,
             ["quien", "operacion", "ruta", "error", "n"])
    return filas


# ----------------------------------------------------------------- sshd
def accesos_sshd() -> list[dict]:
    """Líneas de sshd del objetivo que deciden un acceso: aceptados con su
    key ID (que es como el objetivo sabe quién entró a través del bastión),
    certificados inválidos y conexiones cerradas antes de autenticar."""
    ruta = os.path.join(REGISTROS, "sshd.log")
    filas = []
    if not os.path.exists(ruta):
        return filas
    # cada patrón devuelve (tipo, usuario, key_id, detalle)
    patrones = [
        (re.compile(r'Accepted certificate ID "([^"]+)" \(serial \d+\) signed by (\S+ CA \S+)'),
         lambda m: ("certificado aceptado por la CA", "", m.group(1), m.group(2))),
        (re.compile(r"Accepted publickey for (\S+) from \S+ port \d+ ssh2: (\S+) \S+"
                    r"(?: ID (\S+) \(serial \d+\))?"),
         lambda m: ("acceso aceptado", m.group(1), m.group(3) or "", m.group(2))),
        (re.compile(r"Certificate invalid: (.+)$"),
         lambda m: ("certificado inválido", "", "", m.group(1))),
        (re.compile(r"Failed publickey for (\S+) from \S+ port \d+ ssh2: (\S+) \S+"
                    r"(?: ID (\S+) \(serial \d+\))?"),
         lambda m: ("acceso rechazado", m.group(1), m.group(3) or "", m.group(2))),
        (re.compile(r"Connection closed by authenticating user (\S+)"),
         lambda m: ("cerrada sin autenticar", m.group(1), "", "")),
        (re.compile(r"User (\S+) not allowed because account is locked"),
         lambda m: ("cuenta bloqueada", m.group(1), "", "")),
    ]
    with open(ruta, errors="replace") as f:
        for linea in f:
            linea = linea.strip()
            for pat, forma in patrones:
                m = pat.search(linea)
                if not m:
                    continue
                tipo, usuario, key_id, detalle = forma(m)
                filas.append(dict(tipo=tipo, usuario=usuario, key_id=key_id,
                                  detalle=detalle[:120]))
                break
    escribir("sshd_accesos.csv", filas, ["tipo", "usuario", "key_id", "detalle"])
    return filas


# ---------------------------------------------------------------- bastión
def auditoria_bastion() -> list[dict]:
    """Eventos de auditoría que el bastión escribe en su diario (target
    «audit»): certificados pedidos, secretos resueltos, sesiones."""
    ruta = os.path.join(REGISTROS, "warpgate.log")
    cuenta: collections.Counter = collections.Counter()
    if not os.path.exists(ruta):
        return []
    with open(ruta, errors="replace") as f:
        for linea in f:
            m = re.search(r'audit: .*?_type="([A-Za-z]+?)\d*"', linea)
            if not m:
                continue
            evento = m.group(1)
            p = re.search(r"\b(SSH|PostgreSQL|HTTP|MySQL)\b", linea)
            protocolo = p.group(1) if p else ""
            s = re.search(r"success=(true|false)", linea)
            exito = {"true": "sí", "false": "no"}[s.group(1)] if s else ""
            cuenta[(protocolo, evento, exito)] += 1
    filas = [dict(protocolo=p, evento=e, exito=x, n=n)
             for (p, e, x), n in sorted(cuenta.items())]
    escribir("auditoria_bastion.csv", filas, ["protocolo", "evento", "exito", "n"])
    return filas


# ---------------------------------------------------- esfuerzo y recursos
def esfuerzo() -> list[dict]:
    filas = []
    if os.path.exists(FASES):
        with open(FASES) as f:
            for linea in f:
                fase, seg = linea.strip().rsplit(",", 1)
                filas.append(dict(fase=fase, segundos_acumulados=int(seg)))
    escribir("esfuerzo.csv", filas, ["fase", "segundos_acumulados"])
    return filas


def configuracion() -> list[dict]:
    filas = []
    for nombre in FICHEROS_CONFIG:
        ruta = os.path.join(SALIDA, nombre)
        if not os.path.exists(ruta):
            continue
        with open(ruta) as f:
            lineas = [l for l in f if l.strip() and not l.lstrip().startswith(("#", "--"))]
        filas.append(dict(fichero=nombre, lineas=len(lineas)))
    escribir("configuracion.csv", filas, ["fichero", "lineas"])
    return filas


def imagenes() -> list[dict]:
    filas = []
    ruta = os.path.join(REGISTROS, "imagenes.txt")
    if os.path.exists(ruta):
        vistas = set()
        with open(ruta) as f:
            for linea in f:
                imagen, tam = linea.strip().rsplit(",", 1)
                if imagen in vistas:
                    continue
                vistas.add(imagen)
                filas.append(dict(imagen=imagen, tamano=tam))
    escribir("imagenes.csv", filas, ["imagen", "tamano"])
    return filas


def recursos() -> list[dict]:
    filas = []
    ruta = os.path.join(REGISTROS, "recursos.txt")
    if os.path.exists(ruta):
        with open(ruta) as f:
            for linea in f:
                nombre, mem = linea.strip().split(",", 1)
                filas.append(dict(contenedor=nombre.replace("pam-minimo-", ""),
                                  memoria=mem.split("/")[0].strip()))
    escribir("recursos.csv", filas, ["contenedor", "memoria"])
    return filas


# ------------------------------------------------------------- instantánea
def instantanea(audit_bao, sshd, audit_wg, fases, config, imgs, recs) -> None:
    pruebas = leer_csv("pruebas.csv")
    certs = leer_csv("certificados.csv")
    creds = leer_csv("credenciales_bd.csv")
    grabs = leer_csv("grabaciones.csv")
    sesiones = leer_csv("sesiones.csv")
    bien = sum(int(p["ok"]) for p in pruebas)
    hoy = dt.date.today().isoformat()
    lineas = [
        "# Instantánea del laboratorio PAM mínimo",
        "",
        f"Medido el {hoy}. OpenBao 2.7.2, Warpgate 0.30.2, PostgreSQL 17.11, "
        "Debian bookworm con OpenSSH como objetivo, todo en Docker Compose, "
        "en una sola máquina. Dato protegido: la tabla 28193 del INE "
        "(ganancia media anual por comunidad, ocupación, sexo y año, 3.672 "
        "filas), sin ninguna persona.",
        "",
        "## Pruebas",
        "",
        f"- {bien} de {len(pruebas)} pruebas con el resultado esperado.",
    ]
    por_bloque = collections.OrderedDict()
    for p in pruebas:
        por_bloque.setdefault(p["bloque"], []).append(p)
    for bloque, ps in por_bloque.items():
        lineas.append(f"- **{bloque}**: " + "; ".join(
            f"{p['prueba']} → {p['resultado']} ({p['ms']} ms)" for p in ps) + ".")
    if certs:
        c = certs[0]
        dur = int(c["valido_hasta"]) - int(c["valido_desde"])
        lineas += ["", "## Certificados SSH", "",
                   f"- Certificado del camino directo: {c['tipo']}, principal "
                   f"«{c['principales']}», key ID «{c['key_id']}», válido "
                   f"{dur} s, firmado en {c['ms_firma']} ms."]
    if creds:
        lineas += ["", "## Credenciales dinámicas", ""]
        for c in creds:
            lineas.append(f"- {c['etiqueta']}: TTL {c['ttl_s']} s, emitida en "
                          f"{c['ms_emision']} ms.")
    if grabs:
        total = sum(int(g["octetos"]) for g in grabs)
        con = sum(int(g.get("contiene_la_salida", 0)) for g in grabs)
        aut = sum(1 for s in sesiones if s.get("usuario"))
        lineas += ["", "## Grabaciones y sesiones", "",
                   f"- {len(grabs)} grabaciones, {total} octetos en total; "
                   f"{con} contienen la salida de la orden en claro "
                   "(base64 por trozos, con su instante).",
                   f"- {len(sesiones)} sesiones en el registro del bastión, "
                   f"{aut} de ellas autenticadas."]
    if sshd:
        cuenta = collections.Counter(f["tipo"] for f in sshd)
        ids = sorted({f["key_id"] for f in sshd if f["key_id"]})
        lineas += ["", "## Lo que vio el servidor SSH", "",
                   "- " + ", ".join(f"{n} {t}" for t, n in sorted(cuenta.items())) + ".",
                   f"- Key ID de los certificados aceptados: {', '.join(ids)}."]
    if audit_bao:
        n = sum(f["n"] for f in audit_bao)
        err = sum(f["n"] for f in audit_bao if f["error"] == "sí")
        lineas += ["", "## Auditoría de la bóveda", "",
                   f"- {n} respuestas registradas, {err} con error, en "
                   f"{len(audit_bao)} combinaciones de quién, operación y ruta."]
    if audit_wg:
        lineas += ["", "## Auditoría del bastión", "",
                   "- " + ", ".join(f"{f['n']} {f['evento']}"
                                    + (f" {f['protocolo']}" if f["protocolo"] else "")
                                    + (f" (éxito {f['exito']})" if f["exito"] else "")
                                    for f in audit_wg) + "."]
    if fases:
        lineas += ["", "## Esfuerzo", "",
                   f"- `init` completo en {fases[-1]['segundos_acumulados']} s: "
                   + "; ".join(f"{f['fase']} a los {f['segundos_acumulados']} s"
                               for f in fases) + "."]
    if config:
        lineas.append(f"- {sum(f['lineas'] for f in config)} líneas de "
                      f"configuración y guion en {len(config)} ficheros, sin "
                      "comentarios ni líneas en blanco.")
    if imgs:
        lineas.append("- Imágenes: " + "; ".join(f"{f['imagen']} {f['tamano']}"
                                                 for f in imgs) + ".")
    if recs:
        lineas.append("- Memoria en reposo: " + "; ".join(
            f"{f['contenedor']} {f['memoria']}" for f in recs) + ".")
    with open(os.path.join(SALIDA, "INSTANTANEA.md"), "w") as f:
        f.write("\n".join(lineas) + "\n")
    print("\n".join(lineas))


if __name__ == "__main__":
    instantanea(auditoria_openbao(), accesos_sshd(), auditoria_bastion(),
                esfuerzo(), configuracion(), imagenes(), recursos())
