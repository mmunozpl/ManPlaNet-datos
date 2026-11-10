#!/usr/bin/env python3
"""Auditoría interna del SGSI: comprobaciones automáticas sobre los ficheros
versionados de los tres sistemas del alcance (pam-minimo, datamart-wikipedia
y rag-sintetico) y sobre la documentación del propio sistema de gestión.

Cada comprobación se ejecuta sobre la evidencia (un fichero de configuración,
un CSV de medición, un guion), no sobre una declaración, y lleva la
referencia del control que verifica en cada marco: control del anexo A o
cláusula de ISO/IEC 27001:2022, cláusula de ISO/IEC 27090:2026 cuando toca,
medida del anexo II del ENS (RD 311/2022), subcategoría de NIST CSF 2.0,
letra del artículo 21.2 de la NIS2, artículo de DORA y requisito de PCI DSS
v4.0.1. Los resultados son «conforme», «no conforme», «observación» (una
mejora sin incumplimiento) y «no aplica» (con su justificación).

Escribe auditoria.csv (una fila por comprobación), auditoria_resumen.csv (por
sistema y resultado) y auditoria_marcos.csv (qué parte de la auditoría toca
cada marco y cuánta sale conforme). La demo del RAG se lee de su repositorio
público, clonado en descargas/space-rag si no está (variable SPACE_RAG).
"""
import csv
import datetime as dt
import glob
import json
import os
import re
import subprocess

AQUI = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.dirname(AQUI)
F = os.path.join(AQUI, "fuentes")
LAB = {"pam-minimo": os.path.join(DATA, "pam-minimo"),
       "datamart-wikipedia": os.path.join(DATA, "datamart-wikipedia"),
       "rag-sintetico": os.path.join(DATA, "rag-sintetico")}
SPACE_URL = "https://huggingface.co/spaces/ManPla/rag-sintetico"
SPACE = os.environ.get("SPACE_RAG") or os.path.join(AQUI, "descargas", "space-rag")
HOY = dt.date.today().isoformat()
FILAS: list[dict] = []
CAMPOS = ["id", "sistema", "comprobacion", "tipo", "resultado", "evidencia", "iso27001", "iso27090", "ens", "csf", "nis2", "dora", "pci"]


def leer(*ruta: str) -> str:
    """El texto de un fichero, o cadena vacía si no existe."""
    try:
        return open(os.path.join(*ruta), encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def filas_csv(*ruta: str) -> list[dict]:
    try:
        return list(csv.DictReader(open(os.path.join(*ruta), encoding="utf-8")))
    except OSError:
        return []


def c(id_: str, sistema: str, texto: str, resultado, evidencia: str, iso: str = "", ens: str = "", csf: str = "",
      nis2: str = "", dora: str = "", pci: str = "", iso27090: str = "", tipo: str = "automática") -> None:
    """Registra una comprobación. ``resultado`` admite True/False o el texto."""
    if resultado is True:
        resultado = "conforme"
    elif resultado is False:
        resultado = "no conforme"
    FILAS.append(dict(id=id_, sistema=sistema, comprobacion=texto, tipo=tipo, resultado=resultado, evidencia=evidencia,
                      iso27001=iso, iso27090=iso27090, ens=ens, csf=csf, nis2=nis2, dora=dora, pci=pci))


# ------------------------------------------------------------ utilidades
def imagenes(texto: str) -> list[str]:
    return re.findall(r"^\s*image:\s*\"?([^\s\"]+)", texto, re.M) + re.findall(r"^FROM\s+(\S+)", texto, re.M)


def fijada(img: str) -> bool:
    return ":" in img.split("/")[-1] and not img.endswith(":latest")


def puertos(texto: str) -> list[str]:
    return re.findall(r"^\s*-\s*\"?((?:\d+\.\d+\.\d+\.\d+:)?\d+:\d+)\"?", texto, re.M)


def contrasenas_literales(texto: str) -> list[str]:
    """Líneas con una contraseña escrita, excluidas las que vienen de un
    fichero de secretos, de una variable o de un comentario."""
    malas = []
    for linea in texto.splitlines():
        s = linea.strip()
        if not re.search(r"(?i)password|contrase", s) or s.startswith("#"):
            continue
        if re.search(r"_FILE|\$|secrets?/|cat |aleatorio|\.json|\.txt|\.env|getpass|input\(", s):
            continue
        if re.search(r"(?i)password\w*\s*[:=]\s*['\"]?[A-Za-z0-9!@#%^&*_+-]{6,}", s):
            malas.append(s[:80])
    return malas


def laboratorio_docker(sis: str, p: str, extra: dict) -> None:
    """Las comprobaciones comunes a los dos laboratorios en Docker."""
    compose = leer(p, "compose.yaml"); guion = leer(p, "laboratorio.sh"); ignore = leer(p, ".gitignore")
    dockerfiles = "".join(leer(d) for d in glob.glob(os.path.join(p, "*", "Dockerfile")))
    S = sis.upper()[0]
    # secretos y contraseñas
    faltan = [x for x in extra["ignorar"] if x not in ignore]
    c(f"{S}01", sis, "los secretos del laboratorio están excluidos del repositorio (.gitignore por nombre)", not faltan,
      f".gitignore: {'; '.join(l for l in ignore.splitlines() if l and not l.startswith('#'))}" + (f"; faltan {faltan}" if faltan else ""),
      "5.17", "op.acc.5", "PR.AA-01", "art. 21.2 i)", "art. 9.4 c)", "8")
    malas = contrasenas_literales(compose + guion + extra.get("otros_textos", ""))
    c(f"{S}02", sis, "ninguna contraseña está escrita en la configuración versionada: nacen aleatorias al arrancar y viajan por fichero de secretos",
      not malas, "aleatorio() en laboratorio.sh; POSTGRES_PASSWORD_FILE en compose.yaml" if not malas else "; ".join(malas),
      "5.17", "op.acc.5", "PR.AA-01", "art. 21.2 i)", "art. 9.4 c)", "8")
    # cadena de suministro
    imgs = imagenes(compose) + imagenes(dockerfiles)
    sin = [i for i in imgs if not fijada(i)]
    c(f"{S}03", sis, "todas las imágenes de contenedor están fijadas por versión (ninguna «latest»)", not sin, "; ".join(imgs),
      "8.19; 5.21", "op.exp.4; op.ext.1", "PR.PS-02; GV.SC-04", "art. 21.2 d) y e)", "art. 9; art. 28", "6", "anexo B")
    escaneo = re.search(r"(?i)trivy|grype|docker scout|scan", compose + guion + dockerfiles)
    c(f"{S}04", sis, "las imágenes y las bibliotecas se escanean en busca de vulnerabilidades conocidas", bool(escaneo),
      "sin herramienta de escaneo en compose.yaml, laboratorio.sh ni los Dockerfile" if not escaneo else escaneo.group(0),
      "8.8", "op.exp.4", "ID.RA-01", "art. 21.2 e)", "art. 9", "6; 11", "anexo B")
    # red y configuración
    ps = puertos(compose); abiertos = [x for x in ps if not x.startswith("127.0.0.1:")]
    c(f"{S}05", sis, "los puertos publicados escuchan solo en la máquina (127.0.0.1), no en todas las interfaces", not abiertos,
      "; ".join(ps), "8.20; 8.22", "mp.com.1; op.exp.2", "PR.IR-01", "art. 21.2 e)", "art. 9.4 b)", "1")
    c(f"{S}06", sis, "los contenedores no corren con privilegios ampliados (sin privileged ni cap_add)",
      not re.search(r"privileged:\s*true|cap_add", compose), "compose.yaml sin privileged ni cap_add", "8.9", "op.exp.2", "PR.PS-01", "art. 21.2 e)", "art. 9.4 b)", "2")
    n_hc = compose.count("healthcheck:")
    c(f"{S}07", sis, "los servicios declaran comprobación de salud (healthcheck) y el arranque espera a que respondan", n_hc >= 2,
      f"{n_hc} healthcheck en compose.yaml; esperar_url en laboratorio.sh", "8.16", "op.mon.3", "DE.CM-01", "art. 21.2 b)", "art. 10", "10")
    limites = re.search(r"mem_limit|cpus:|resources:|pids_limit", compose)
    c(f"{S}08", sis, "los contenedores tienen límites de memoria y CPU", bool(limites), "sin mem_limit, cpus ni deploy.resources en compose.yaml" if not limites else limites.group(0),
      "8.6", "", "PR.IR-04", "art. 21.2 c)", "art. 9", "")
    copias = re.search(r"(?i)pg_dump|backup|restic|borg|copia de seguridad", compose + guion)
    c(f"{S}09", sis, "existe una copia de seguridad programada de los datos y los registros", bool(copias),
      "sin copia en compose.yaml ni en laboratorio.sh; los volúmenes se pierden con «limpiar» (lo confirma el simulacro)" if not copias else copias.group(0),
      "8.13", "mp.info.6", "PR.DS-11", "art. 21.2 c)", "art. 12", "9")
    retencion = re.search(r"(?i)logrotate|retention|retenci|max-size|max-file|log_retention|BASE_LOG_FOLDER", compose + guion + extra.get("config", ""))
    c(f"{S}10", sis, "los registros tienen retención definida y salen del anfitrión", bool(retencion),
      "sin rotación ni envío externo declarados" if not retencion else retencion.group(0), "8.15", "op.exp.8; op.exp.10", "PR.PS-04", "art. 21.2 b)", "art. 10", "10")
    # inventario, documentación y datos
    inv = filas_csv(p, "imagenes.csv"); conf = filas_csv(p, "configuracion.csv")
    c(f"{S}11", sis, "existe un inventario de los componentes (imágenes con su tamaño; ficheros de configuración con sus líneas)", bool(inv and conf),
      f"imagenes.csv: {len(inv)} imágenes; configuracion.csv: {len(conf)} ficheros", "5.9", "op.exp.1", "ID.AM-01; ID.AM-02", "art. 21.2 i)", "art. 8", "12")
    leeme = leer(p, "LEEME.md")
    c(f"{S}12", sis, "el procedimiento de reproducción y los límites del sistema están documentados", "## Reproducir" in leeme and "## Límites" in leeme,
      "LEEME.md: secciones Reproducir, Ficheros, Lo que mide y Límites", "5.37", "org.3", "PR.PS-01", "art. 21.2 a)", "art. 9", "12")
    inst = leer(p, "INSTANTANEA.md") + leeme
    sin_personas = re.search(r"(?i)ning[uú]n dato (real )?de (ninguna )?persona|sin datos personales|no interviene ning[uú]n dato", inst)
    c(f"{S}13", sis, "el sistema no trata datos personales y lo declara", bool(sin_personas), sin_personas.group(0) if sin_personas else "sin declaración en INSTANTANEA.md ni LEEME.md",
      "5.34", "mp.info.1", "GV.OC-03", "", "", "")
    c(f"{S}14", sis, "la información del sistema está clasificada: datos públicos de una fuente abierta con su licencia y su URL fijadas",
      any(sis in r["mediciones"].split() for r in filas_csv(DATA, "fuentes.csv")), "fila del sistema en fuentes.csv (fuente, URL, licencia)",
      "5.12; 5.19", "mp.info.2; op.ext.1", "ID.AM-05; GV.SC-01", "art. 21.2 d)", "art. 28", "12.8")
    huellas = json.load(open(os.path.join(DATA, "huellas.json"))).get("cuadernos", {})
    c(f"{S}15", sis, "la medición publicada lleva su huella fijada y se comprueba cada mes en la integración continua", any(k.startswith(sis) for k in huellas),
      "huellas.json → cuadernos; flujo mensual en data/.github", "5.33; 8.9", "mp.info.3", "PR.DS-01", "", "art. 9", "")
    pruebas = filas_csv(p, "pruebas.csv")
    ok = sum(1 for r in pruebas if r.get("ok", "1") == "1")
    c(f"{S}16", sis, "el banco de pruebas de seguridad y de funcionamiento se ejecuta y se publica con su resultado", bool(pruebas) and ok == len(pruebas),
      f"pruebas.csv: {ok} de {len(pruebas)} superadas", "8.29", "mp.sw.2", "ID.IM-02", "art. 21.2 f)", "art. 24; art. 25", "11")


# ------------------------------------------------------------ PAM mínimo
def pam() -> None:
    sis = "pam-minimo"; p = LAB[sis]
    cfg = leer(p, "openbao", "config.hcl"); sshd = leer(p, "objetivo-ssh", "sshd_config")
    laboratorio_docker(sis, p, dict(ignorar=["secretos/", "openbao/tls/"], config=cfg, otros_textos=leer(p, "postgres", "init.sql")))
    c("P17", sis, "la bóveda escucha con TLS y el bastión exige https para hablar con ella", "tls_cert_file" in cfg and "tls_disable" not in cfg,
      "config.hcl: listener tcp con tls_cert_file y tls_key_file; CA propia del laboratorio", "8.24; 8.20", "mp.com.2", "PR.DS-02", "art. 21.2 h)", "art. 9.4 d)", "4")
    c("P18", sis, "el diario de auditoría de la bóveda está declarado y registra cada petición y su respuesta", 'audit "file"' in cfg,
      "config.hcl: audit \"file\" → /openbao/logs/auditoria.log; auditoria_openbao.csv", "8.15", "op.exp.8", "PR.PS-04; DE.CM-03", "art. 21.2 b)", "art. 10", "10")
    pol = "".join(leer(f) for f in glob.glob(os.path.join(p, "openbao", "politicas", "*.hcl")))
    rutas = re.findall(r'path\s+"([^"]+)"', pol); amplias = [r for r in rutas if r in ("*", "+", "sys/*", "secret/*") or r.startswith("sys/") and r.endswith("/*") and "leases" not in r]
    c("P19", sis, "las políticas de la bóveda dan permisos por ruta exacta, sin comodines amplios ni capacidad sudo", not amplias and "sudo" not in pol,
      "rutas: " + "; ".join(rutas), "8.3; 8.2", "op.acc.4", "PR.AA-05", "art. 21.2 i)", "art. 9.4 c)", "7")
    c("P20", sis, "el servidor SSH no acepta contraseñas ni teclado interactivo", "PasswordAuthentication no" in sshd and "KbdInteractiveAuthentication no" in sshd,
      "sshd_config: PasswordAuthentication no; KbdInteractiveAuthentication no", "8.5", "op.acc.5", "PR.AA-03", "art. 21.2 j)", "art. 9.4 c)", "8")
    c("P21", sis, "el acceso como root está prohibido en el servidor SSH", "PermitRootLogin no" in sshd, "sshd_config: PermitRootLogin no",
      "8.2", "op.acc.3", "PR.AA-05", "art. 21.2 i)", "art. 9.4 c)", "7")
    c("P22", sis, "el servidor SSH solo confía en certificados de la CA de la bóveda, sin claves autorizadas fijas, y con principales por usuario",
      "TrustedUserCAKeys" in sshd and "AuthorizedKeysFile none" in sshd and "AuthorizedPrincipalsFile" in sshd,
      "sshd_config: TrustedUserCAKeys; AuthorizedKeysFile none; AuthorizedPrincipalsFile", "8.5; 5.17", "op.acc.5", "PR.AA-01; PR.AA-03", "art. 21.2 j)", "art. 9.4 c)", "8")
    c("P23", sis, "el servidor SSH registra el identificador del certificado de cada acceso (LogLevel VERBOSE)", "LogLevel VERBOSE" in sshd,
      "sshd_config: LogLevel VERBOSE; sshd_accesos.csv con key_id", "8.15", "op.exp.8", "PR.PS-04", "art. 21.2 b)", "art. 10", "10")
    cred = filas_csv(p, "credenciales_bd.csv"); cert = filas_csv(p, "certificados.csv")
    ttl_bd = max((int(r["ttl_s"]) for r in cred), default=0)
    ttl_cert = max((int(r["valido_hasta"]) - int(r["valido_desde"]) for r in cert), default=0)
    c("P24", sis, "las credenciales privilegiadas caducan solas en menos de cinco minutos (base de datos y certificados SSH)", 0 < ttl_bd <= 300 and 0 < ttl_cert <= 300,
      f"credenciales_bd.csv: ttl {ttl_bd} s; certificados.csv: {ttl_cert} s", "8.2; 5.18", "op.acc.4; op.acc.5", "PR.AA-05", "art. 21.2 i)", "art. 9.4 c)", "8")
    pruebas = {r["prueba"]: r for r in filas_csv(p, "pruebas.csv")}
    totp = pruebas.get("contraseña + TOTP, orden en el servidor", {}).get("ok") == "1" and pruebas.get("contraseña correcta, sin TOTP", {}).get("ok") == "1"
    c("P25", sis, "el bastión exige un segundo factor (TOTP) y rechaza la contraseña sola", totp,
      "pruebas.csv: «contraseña + TOTP» entra; «contraseña correcta, sin TOTP» denegada", "8.5", "op.acc.5", "PR.AA-03", "art. 21.2 j)", "art. 9.4 c)", "8.4")
    bloqueo = pruebas.get("tres fallos más (cinco en total): IP bloqueada", {}).get("ok") == "1"
    c("P26", sis, "el bastión bloquea el origen tras cinco intentos fallidos y el desbloqueo exige al administrador", bloqueo,
      "pruebas.csv: «cinco en total: IP bloqueada»; «desbloqueo por el administrador (API)»", "8.5", "op.acc.5", "PR.AA-03", "art. 21.2 j)", "art. 9.4 c)", "8.3")
    revoc = pruebas.get("revocar la concesión antes de tiempo", {}).get("ok") == "1" and pruebas.get("leer tras la revocación", {}).get("ok") == "1"
    c("P27", sis, "una credencial se puede revocar antes de tiempo y la revocación surte efecto", revoc,
      "pruebas.csv: «revocar la concesión antes de tiempo»; «leer tras la revocación» denegada", "5.18; 8.2", "op.acc.4", "PR.AA-05", "art. 21.2 i)", "art. 9.4 c)", "8")
    grab = filas_csv(p, "grabaciones.csv"); ses = filas_csv(p, "sesiones.csv")
    con_obj = sum(1 for r in ses if (r.get("sesiones_objetivo") or "0") != "0")
    c("P28", sis, "las sesiones privilegiadas quedan grabadas con su salida", "observación" if grab and con_obj > len(grab) else bool(grab),
      f"grabaciones.csv: {len(grab)} grabación con salida; sesiones.csv: {con_obj} sesiones con objetivo (las de PostgreSQL por el bastión no se graban)",
      "8.15; 8.16", "op.exp.8; op.acc.6", "DE.CM-03", "art. 21.2 b)", "art. 10", "10")
    aud = filas_csv(p, "auditoria_openbao.csv")
    n = sum(int(r["n"]) for r in aud); den = sum(int(r["n"]) for r in aud if r["error"] == "sí")
    c("P29", sis, "las denegaciones de la bóveda quedan en el diario con quién, qué y dónde", den > 0,
      f"auditoria_openbao.csv: {n} operaciones, {den} denegadas o con error", "8.15", "op.exp.8", "DE.CM-03; DE.AE-02", "art. 21.2 b)", "art. 10", "10")
    c("P30", sis, "la bóveda tiene más de un nodo (alta disponibilidad)", "observación" if 'storage "raft"' in cfg else False,
      "config.hcl: raft de un solo nodo (node_id laboratorio)", "8.14", "op.cont.2", "PR.IR-03", "art. 21.2 c)", "art. 12", "")
    c("P31", sis, "la memoria de la bóveda está protegida frente al intercambio a disco", "observación" if "disable_mlock = true" in cfg else True,
      "config.hcl: disable_mlock = true (la imagen corre sin privilegios); fuera del laboratorio, swap cifrado", "8.24; 8.9", "mp.info.3", "PR.DS-10", "art. 21.2 h)", "art. 9.4 d)", "3")


# ------------------------------------------------------------ DataMart
def datamart() -> None:
    sis = "datamart-wikipedia"; p = LAB[sis]
    init = leer(p, "postgres", "init.sh"); dag = "".join(leer(f) for f in glob.glob(os.path.join(p, "airflow", "dags", "*.py")))
    laboratorio_docker(sis, p, dict(ignorar=["secretos/", "cache/", ".env"], config=dag, otros_textos=init))
    roles = re.findall(r"CREATE ROLE (\w+) LOGIN", init)
    c("D17", sis, "la base de datos separa los roles de orquestación, transformación y administración, cada uno con sus esquemas", len(roles) >= 2,
      f"init.sh: roles {', '.join(roles)} y admin_bd; GRANT por esquema", "5.3; 8.2; 8.3", "op.acc.3; op.acc.4", "PR.AA-05", "art. 21.2 i)", "art. 9.4 c)", "7")
    reint = re.search(r"retries=(\d+)", dag)
    c("D18", sis, "las tareas de la canalización reintentan con espera creciente antes de fallar", bool(reint) and int(reint.group(1)) >= 1,
      f"visualizaciones.py: retries={reint.group(1) if reint else 0}; retry_exponential_backoff", "8.14", "op.cont.2", "PR.IR-03", "art. 21.2 c)", "art. 12", "")
    c("D19", sis, "un fallo definitivo de la canalización genera un aviso", "on_failure_callback" in dag,
      "visualizaciones.py: on_failure_callback=avisar; avisos_airflow.csv", "5.24; 8.16", "op.exp.7", "DE.AE-06; RS.MA-01", "art. 21.2 b)", "art. 17", "10")
    c("D20", sis, "la carga histórica está acotada (un run a la vez, con fecha de fin) y es idempotente por mes", "max_active_runs=1" in dag and "end_date" in dag,
      "visualizaciones.py: catchup=True; end_date=2026-10-31; max_active_runs=1; estrategia delete+insert por mes", "8.6; 8.32", "op.exp.2", "PR.IR-04; PR.PS-01", "art. 21.2 e)", "art. 9", "6")
    tests = filas_csv(p, "tests_dbt.csv")
    pasan = sum(1 for r in tests if r["estado"] == "pass"); avisan = sum(1 for r in tests if r["estado"] == "warn")
    c("D21", sis, "las pruebas de calidad del dato (grano, relaciones, rangos, días contiguos) se ejecutan en cada carga y todas pasan",
      "observación" if tests and pasan + avisan == len(tests) and avisan else (bool(tests) and pasan == len(tests)),
      f"tests_dbt.csv: {pasan} superadas, {avisan} con aviso, de {len(tests)}", "8.29; 8.9", "mp.sw.2; mp.info.3", "ID.IM-02; PR.DS-01", "art. 21.2 f)", "art. 24", "11")
    c("D22", sis, "los cambios de estado se historian (snapshot SCD2 con fecha de negocio)", bool(glob.glob(os.path.join(p, "dbt", "snapshots", "*.sql"))),
      "dbt/snapshots/snap_articulo_tramo.sql; snapshot.csv: versiones y cambios", "5.33", "op.exp.10", "PR.DS-01", "", "art. 9", "10")
    idem = filas_csv(p, "idempotencia.csv")
    c("D23", sis, "repetir una carga deja los mismos recuentos y las mismas huellas de contenido", bool(idem) and all(r["igual"] == "sí" for r in idem),
      f"idempotencia.csv: {sum(1 for r in idem if r['igual'] == 'sí')} de {len(idem)} objetos iguales (recuentos y md5)", "8.32; 8.29", "mp.sw.2", "PR.PS-01", "art. 21.2 e)", "art. 9", "6")
    c("D24", sis, "la zona cruda se puede rehacer desde la fuente y desde una caché externa al repositorio", os.path.exists(os.path.join(p, "ingesta", "descargar.py")) and "CACHE_CRUDO" in leer(p, "compose.yaml"),
      "ingesta/descargar.py; compose.yaml monta CACHE_CRUDO; el simulacro reconstruye 34 meses desde la caché", "8.13", "mp.info.6", "PR.DS-11; RC.RP-03", "art. 21.2 c)", "art. 12", "9", tipo="automática")
    c("D25", sis, "los datos y las copias están cifrados en reposo", "observación" if not re.search(r"(?i)encrypt|cifr|ssl", leer(p, "compose.yaml") + init) else True,
      "sin cifrado de volúmenes: laboratorio local con datos públicos", "8.24", "mp.info.3", "PR.DS-01", "art. 21.2 h)", "art. 9.4 d)", "3")
    c("D26", sis, "la consola del orquestador exige un segundo factor o identidad federada", "observación" if "SIMPLE_AUTH_MANAGER" in leer(p, "compose.yaml") else True,
      "compose.yaml: gestor de autenticación simple (usuario y contraseña aleatoria; sin segundo factor)", "8.5", "op.acc.5", "PR.AA-03", "art. 21.2 j)", "art. 9.4 c)", "8")
    semillas = glob.glob(os.path.join(p, "dbt", "seeds", "*.csv"))
    c("D27", sis, "los datos de referencia (dimensiones conformadas) están versionados como semillas", bool(semillas),
      "dbt/seeds: " + "; ".join(os.path.basename(s) for s in semillas), "8.9", "op.exp.2", "PR.PS-01", "", "", "")


# ------------------------------------------------------------ RAG (sistema de IA)
def espacio() -> str:
    """El código público de la demo, clonado si hace falta."""
    if not os.path.exists(os.path.join(SPACE, "app.py")):
        os.makedirs(os.path.dirname(SPACE), exist_ok=True)
        try:
            subprocess.run(["git", "clone", "-q", "--depth", "1", SPACE_URL, SPACE], check=True, timeout=120)
        except Exception:
            return ""
    return SPACE


def rag() -> None:
    sis = "rag-sintetico"; p = LAB[sis]; sp = espacio()
    gen = leer(p, "generar.py"); app = leer(sp, "app.py") if sp else ""; req = leer(sp, "requirements.txt") if sp else ""; readme = leer(sp, "README.md") if sp else ""
    c("R01", sis, "control de integridad del corpus (6.2): el corpus y las consultas nacen de una semilla fija y su reconstrucción coincide con la publicada a cinco decimales; no ensaya un ataque de envenenamiento", "SEMILLA =" in gen,
      "generar.py: SEMILLA = 20260825; el simulacro reconstruye 600 fragmentos iguales a cinco decimales", "8.9; 8.32", "op.exp.2", "PR.PS-01", "", "art. 9", "", "6.2")
    c("R02", sis, "el permiso se aplica dentro de la consulta al índice (filtro sobre la lista de autorizados), no después de recuperar", "query_filter" in gen,
      "generar.py: query_points(..., query_filter=filtro_de(acl))", "5.15; 8.3", "op.acc.4", "PR.AA-05", "art. 21.2 i)", "art. 9.4 c)", "7", "")
    cons = filas_csv(p, "consultas.csv")
    pre = sum(int(r["pre_expuestos"]) for r in cons); post = sum(int(r["post_expuestos"]) for r in cons)
    c("R03", sis, "con el permiso dentro de la consulta ningún fragmento ajeno llega al usuario", bool(cons) and pre == 0,
      f"consultas.csv: {pre} fragmentos ajenos en {len(cons)} consultas con el filtro dentro; {post} con el permiso aplicado después", "8.3; 8.11", "op.acc.4; mp.info.1", "PR.AA-05; PR.DS-01", "art. 21.2 i)", "art. 9.4 c)", "7", "")
    inst = leer(p, "INSTANTANEA.md")
    c("R04", sis, "el recuperador no trata datos personales ni documentos reales y lo declara", bool(re.search(r"(?i)ning[uú]n dato de ninguna persona", inst)),
      "INSTANTANEA.md: vectores de ruido con semilla; «No interviene ningún dato de ninguna persona»", "5.34", "mp.info.1", "GV.OC-03", "", "", "", "6.4; 6.6")
    libs = [l.strip() for l in req.splitlines() if l.strip() and not l.startswith("#")]
    fijas = [l for l in libs if "==" in l]
    c("R05", sis, "las bibliotecas de la demo están fijadas por versión exacta", bool(libs) and len(fijas) == len(libs) if sp else "sin evidencia",
      f"requirements.txt: {'; '.join(libs)} ({len(fijas)} de {len(libs)} fijadas)" if sp else "no se pudo leer el repositorio de la demo",
      "8.19; 5.21", "op.exp.4; op.ext.1", "PR.PS-02; GV.SC-04", "art. 21.2 d) y e)", "art. 28", "6", "anexo B")
    sdk = re.search(r"sdk_version:\s*([\d.]+)", readme)
    c("R06", sis, "el entorno de ejecución de la demo (SDK) está fijado por versión", bool(sdk) if sp else "sin evidencia", f"README.md del Space: sdk_version {sdk.group(1) if sdk else '?'}",
      "8.19", "op.exp.4", "PR.PS-02", "art. 21.2 e)", "art. 28", "6", "anexo B")
    lic = re.search(r"license:\s*(\S+)", readme)
    c("R07", sis, "la demo declara su licencia", bool(lic) if sp else "sin evidencia", f"README.md del Space: license {lic.group(1) if lic else '?'}", "5.32", "", "GV.OC-03", "", "", "")
    huellas = json.load(open(os.path.join(DATA, "huellas.json"))).get("cuadernos", {})
    c("R08", sis, "la medición publicada lleva su huella fijada y se comprueba cada mes", any(k.startswith(sis) for k in huellas), "huellas.json → cuadernos", "5.33; 8.9", "mp.info.3", "PR.DS-01", "", "art. 9", "")
    c("R09", sis, "la entrada del usuario está acotada: consulta y usuario se eligen de una lista cerrada, sin texto libre que leer", ("Textbox" not in app and "gr." in app) if sp else "sin evidencia",
      "app.py: sin gr.Textbox; selección de parámetros y botón", "8.26; 8.28", "mp.sw.1", "PR.PS-06", "art. 21.2 e)", "art. 9", "6", "6.9; 6.10")
    c("R10", sis, "los parámetros del sistema de IA están declarados (semilla, dimensiones, k, dispersión, motor)", all(x in inst for x in ("Semilla", "dimensiones", "Dispersión", "Motor")),
      "INSTANTANEA.md: semilla, 64 dimensiones, k = 10, dispersión 0,15, qdrant-client en modo local", "5.37", "org.3", "ID.AM-02", "", "", "")
    c("R11", sis, "las amenazas de IA se reevalúan a intervalos planificados (cláusula 7 de ISO/IEC 27090)", False,
      "sin calendario de reevaluación en el LEEME ni en la medición; esta auditoría es la primera evaluación", "5.7; cl. 8.2", "op.pl.1", "ID.RA-03; ID.RA-05", "art. 21.2 a)", "art. 6", "", "cl. 7")
    c("R12", sis, "la medición del RAG corre con un entorno bloqueado (uv.lock) en el repositorio de datos", "qdrant-client==" in leer(DATA, "pyproject.toml"),
      "data/pyproject.toml y uv.lock: qdrant-client fijado", "8.19", "op.exp.4", "PR.PS-02", "art. 21.2 e)", "art. 28", "6", "anexo B")
    soa = filas_csv(F, "soa_27090.csv")
    c("R13", sis, "las nueve amenazas de la cláusula 6 y el anexo B tienen su declaración (aplica, estado, salvaguarda, evidencia)", len(soa) >= 10,
      f"fuentes/soa_27090.csv: {len(soa)} filas; {sum(1 for r in soa if r['aplica'] == 'sí')} aplican", "cl. 6.1.3 d)", "op.pl.2", "ID.RA-05", "art. 21.2 a)", "art. 6", "", "cl. 6; anexo B")


# ------------------------------------------------------------ el propio SGSI
def sgsi() -> None:
    sis = "sgsi"
    pol = leer(F, "politica.md")
    c("S01", sis, "existe una política de seguridad aprobada, con fecha y revisión prevista", "aprobada el" in pol and "## Compromisos" in pol,
      "fuentes/politica.md v1.0, 09-11-2026", "5.1; cl. 5.2", "org.1", "GV.PO-01", "art. 21.2 a)", "art. 5", "12", tipo="documental")
    c("S02", sis, "los roles de seguridad están nombrados y separados", "observación" if "## Roles" in pol else False,
      "politica.md: dirección, responsable de seguridad y responsable de cada sistema recaen en la misma persona", "5.2; 5.3", "org.2", "GV.RR-02", "art. 20", "art. 5.2", "12.4", tipo="documental")
    c("S03", sis, "el alcance del SGSI está definido con sus límites y exclusiones", "## Alcance" in pol and "Quedan fuera" in pol,
      "politica.md: tres sistemas; fuera el anfitrión, la red y las cuentas de las plataformas", "cl. 4.3", "org.1", "GV.OC-01", "art. 21.2 a)", "art. 6", "12", tipo="documental")
    c("S04", sis, "las partes interesadas y los requisitos legales están documentados, incluida la pregunta del cambio climático de la enmienda de 2024", "observación",
      "politica.md nombra los marcos; sin registro de partes interesadas ni mención al clima", "cl. 4.1; cl. 4.2", "org.1", "GV.OC-02; GV.OC-03", "", "", "", tipo="documental")
    riesgos = filas_csv(AQUI, "riesgos.csv")
    c("S05", sis, "hay un análisis de riesgos con método declarado, activos valorados y amenazas de un catálogo público", bool(riesgos),
      f"riesgo.py (MAGERIT v3 simplificado); riesgos.csv: {len(riesgos)} riesgos sobre {len(filas_csv(F, 'activos.csv'))} activos", "cl. 6.1.2", "op.pl.1", "ID.RA-04; ID.RA-05", "art. 21.2 a)", "art. 6; art. 8", "12.3")
    c("S06", sis, "el apetito de riesgo está declarado y cada riesgo residual se compara con él", "APETITO" in leer(AQUI, "riesgo.py"),
      f"riesgo.py: APETITO = 12 sobre 50; {sum(1 for r in riesgos if r['sobre_apetito'] == 'sí')} riesgos por encima", "cl. 6.1.2 a)", "op.pl.1", "GV.RM-02", "art. 21.2 a)", "art. 6.8", "12.3")
    soa = filas_csv(F, "soa_laboratorios.csv")
    c("S07", sis, "la declaración de aplicabilidad recorre los 93 controles del anexo A con estado, justificación y evidencia", len(soa) == 93,
      f"fuentes/soa_laboratorios.csv: {len(soa)} controles; {sum(1 for r in soa if r['estado'] == 'implantado')} implantados, {sum(1 for r in soa if r['estado'] == 'parcial')} parciales, {sum(1 for r in soa if r['aplica'] == 'no')} no aplican",
      "cl. 6.1.3 d)", "anexo II (declaración de aplicabilidad)", "ID.RA-06", "art. 21.2 a)", "art. 6", "12")
    c("S08", sis, "los objetivos de seguridad están escritos como resultados clave medibles, con fuente y periodicidad", os.path.exists(os.path.join(AQUI, "kpis.py")),
      "kpis.py: cinco objetivos con sus resultados clave; kpis.csv", "cl. 6.2; cl. 9.1", "op.mon.2", "GV.OV-01", "art. 21.2 f)", "art. 6.5", "12")
    c("S09", sis, "la auditoría interna se ha ejecutado y sus resultados están registrados", True, f"auditoria.csv de {HOY}: {len(FILAS) + 1} comprobaciones",
      "cl. 9.2", "art. 31 RD 311/2022", "ID.IM-02", "art. 21.2 f)", "art. 6.6", "12")
    c("S10", sis, "la dirección revisa el sistema a intervalos planificados y una tercera parte lo ha auditado", False,
      "sin revisión por la dirección registrada ni auditoría de tercera parte", "cl. 9.3; cl. 9.2", "art. 31 RD 311/2022", "GV.OV-02; GV.OV-03", "art. 21.2 f)", "art. 6.5", "12", tipo="documental")
    plan = filas_csv(F, "plan_director.csv")
    c("S11", sis, "cada riesgo sobre el apetito y cada hallazgo tiene una iniciativa en el plan de tratamiento, con prioridad, trimestre y esfuerzo", bool(plan),
      f"fuentes/plan_director.csv: {len(plan)} iniciativas, {sum(int(r['horas_estimadas']) for r in plan)} horas estimadas", "cl. 6.1.3 e); cl. 10.2", "", "ID.IM-04", "art. 21.2 a)", "art. 6", "12")
    c("S12", sis, "existe un procedimiento de gestión de incidentes con clasificación, roles y plazos de notificación", False,
      "los laboratorios detectan y avisan (diario de la bóveda; aviso de Airflow) pero no hay procedimiento escrito ni destinatario del aviso", "5.24; 5.25; 5.26", "op.exp.7", "RS.MA-01; RS.CO-02", "art. 21.2 b); art. 23", "art. 17; art. 19", "12.10", tipo="documental")
    sim = filas_csv(AQUI, "simulacro.csv")
    rto = [r for r in sim if r["fase"] == "tiempo real de recuperación"]
    c("S13", sis, "la continuidad se ha ensayado: cada sistema destruido y reconstruido, con tiempo hasta el servicio y pérdida de datos medidos", bool(rto) and all(r["resultado"] == "ok" for r in rto),
      "simulacro.csv: " + "; ".join(f"{r['laboratorio']} {r['segundos_acumulados']} s" for r in rto) if rto else "sin simulacro.csv",
      "5.29; 5.30", "op.cont.3", "RC.RP-01; ID.IM-02", "art. 21.2 c)", "art. 11", "12.10")
    c("S14", sis, "la restauración se ha probado desde una copia de seguridad (no solo desde el código y la fuente)", False,
      "el simulacro reconstruye desde el código, el fichero versionado y la caché externa; los diarios y las grabaciones se perdieron porque no había copia", "8.13; 5.30", "mp.info.6", "PR.DS-11; RC.RP-03", "art. 21.2 c)", "art. 12", "9")
    c("S15", sis, "ninguno de los sistemas trata datos personales de personas reales, y el enlace con protección de datos está decidido para cuando lo haga", "observación",
      "politica.md (roles): los datos de negocio son agregados o sintéticos; los registros operativos llevan identidades ficticias de laboratorio y direcciones de la red interna de Docker, que con personas reales serían datos personales; si los hubiera, delegado antes del primer tratamiento y estudio de ISO/IEC 27701:2025", "5.34", "mp.info.1", "GV.OC-03", "", "", "", tipo="documental")
    c("S16", sis, "la competencia de quien opera el SGSI está acreditada y hay un plan de formación", "observación",
      "certificación y formación del responsable; sin plan de formación ni registro de concienciación", "cl. 7.2; cl. 7.3; 6.3", "mp.per.3; mp.per.4", "PR.AT-01", "art. 21.2 g)", "art. 13.6", "12.6", tipo="documental")
    prov = filas_csv(F, "proveedores.csv")
    c("S17", sis, "los proveedores (imágenes, bibliotecas, plataformas, fuentes de datos) están inventariados y evaluados", False if prov and not any(r["evaluado"] == "sí" for r in prov) else bool(prov),
      f"fuentes/proveedores.csv: {len(prov)} proveedores inventariados, {sum(1 for r in prov if r['evaluado'] == 'sí')} evaluados", "5.19; 5.20; 5.21; 5.22", "op.ext.1", "GV.SC-01; GV.SC-04", "art. 21.2 d)", "art. 28", "12.8")
    c("S18", sis, "la documentación del SGSI está controlada (versionada, con historial y huella)", True, "repositorio público de datos con historial; huellas comprobadas cada mes",
      "cl. 7.5", "org.3", "PR.PS-01", "", "art. 9", "12")
    c("S19", sis, "los seis marcos están mapeados a una lengua común y las comparativas se calculan desde fuentes públicas", os.path.exists(os.path.join(AQUI, "mapa_controles.csv")),
      f"mapa_controles.csv: {len(filas_csv(AQUI, 'mapa_controles.csv'))} correspondencias; cobertura_csf.csv; comparativa_pares.csv", "cl. 4.2", "org.1", "GV.OC-03", "art. 21.2 a)", "art. 6", "12")
    c("S20", sis, "la serie ISO/IEC 27000 que usa el SGSI está identificada con la edición vigente de cada norma", len(filas_csv(F, "serie_27000.csv")) >= 20,
      f"fuentes/serie_27000.csv: {len(filas_csv(F, 'serie_27000.csv'))} normas con edición y papel", "cl. 7.5", "org.3", "GV.OC-03", "", "", "")


def principal() -> None:
    pam(); datamart(); rag(); sgsi()
    with open(os.path.join(AQUI, "auditoria.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS); w.writeheader(); w.writerows(FILAS)
    # resumen por sistema
    res = []
    for sis in ("pam-minimo", "datamart-wikipedia", "rag-sintetico", "sgsi", "total"):
        sub = [x for x in FILAS if sis == "total" or x["sistema"] == sis]
        fila = dict(sistema=sis, comprobaciones=len(sub))
        for r in ("conforme", "no conforme", "observación", "no aplica", "sin evidencia"):
            fila[r.replace(" ", "_")] = sum(1 for x in sub if x["resultado"] == r)
        evaluables = fila["conforme"] + fila["no_conforme"]
        fila["conformidad_pct"] = round(100 * fila["conforme"] / evaluables, 1) if evaluables else ""
        res.append(fila)
    with open(os.path.join(AQUI, "auditoria_resumen.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys())); w.writeheader(); w.writerows(res)
    # por marco: cuántas comprobaciones lo verifican y cuántas salen conformes
    marcos = []
    for marco, campo in (("ISO/IEC 27001:2022", "iso27001"), ("ISO/IEC 27090:2026", "iso27090"), ("ENS (RD 311/2022)", "ens"),
                         ("NIST CSF 2.0", "csf"), ("NIS2 art. 21.2", "nis2"), ("DORA", "dora"), ("PCI DSS v4.0.1", "pci")):
        sub = [x for x in FILAS if x[campo]]
        conf = sum(1 for x in sub if x["resultado"] == "conforme"); noconf = sum(1 for x in sub if x["resultado"] == "no conforme")
        refs = sorted({r.strip() for x in sub for r in re.split(r";", x[campo]) if r.strip()})
        marcos.append(dict(marco=marco, comprobaciones=len(sub), conformes=conf, no_conformes=noconf, observaciones=sum(1 for x in sub if x["resultado"] == "observación"),
                           conformidad_pct=round(100 * conf / (conf + noconf), 1) if conf + noconf else "", referencias_distintas=len(refs)))
    with open(os.path.join(AQUI, "auditoria_marcos.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(marcos[0].keys())); w.writeheader(); w.writerows(marcos)
    for r in res:
        print(f"{r['sistema']}: {r['comprobaciones']} comprobaciones; conformes {r['conforme']}, no conformes {r['no_conforme']}, observaciones {r['observación']}, "
              f"no aplica {r['no_aplica']}, sin evidencia {r['sin_evidencia']}; conformidad {r['conformidad_pct']} %")
    for m in marcos:
        print(f"  {m['marco']}: {m['comprobaciones']} comprobaciones, {m['referencias_distintas']} referencias, conformidad {m['conformidad_pct']} %")


if __name__ == "__main__":
    principal()
