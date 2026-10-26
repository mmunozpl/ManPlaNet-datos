"""Utilidades compartidas del banco Polars y DuckDB.

Reúne la definición de los entornos aislados (uno por combinación de
versiones, creados con uv fuera de este directorio), la expulsión de ficheros
de la caché de página sin privilegios y el lanzamiento de cada medición en un
proceso propio, dentro de un ámbito de cgroup con tope de memoria.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DIR_REQ = AQUI / "entornos"
PYTHON = "3.11.14"

# versión de duckdb 2.0 por defecto: la pre-versión más reciente en pypi el
# día de la medición; con la estable basta pasar --duckdb2 2.0.0
DUCKDB2 = "2.0.0.dev2610011535"

POLARS = ["1.43.1", "1.44.2", "2.0.0"]
PANDAS = ["2.3.3", "3.0.6", "3.1.0rc0"]


def especificaciones(duckdb2: str = DUCKDB2) -> dict:
    """Devuelve las dependencias directas de cada entorno.

    Las de agosto repiten las versiones de la entrada del 11-08-2026
    (numpy 2.3.3, pyarrow 22.0.0); el resto toma la última publicada.

    Args:
        duckdb2: versión de duckdb 2.0 que se quiere medir.

    Returns:
        Diccionario nombre de entorno -> lista de requisitos exactos.
    """
    # numpy 2.5 exige python 3.12; se fija la última que admite 3.11
    reciente = ["numpy==2.4.6", "pyarrow==26.0.0"]
    agosto = ["numpy==2.3.3", "pyarrow==22.0.0"]
    esp = {
        "pandas-2.3.3": ["pandas==2.3.3"] + agosto,
        "pandas-3.0.6": ["pandas==3.0.6"] + reciente,
        "pandas-3.1.0rc0": ["pandas==3.1.0rc0"] + reciente,
    }
    for v in POLARS:
        extra = agosto if v == "1.43.1" else reciente
        esp[f"polars-{v}"] = [f"polars=={v}",
                              f"polars-runtime-32=={v}"] + extra
    for v in ["1.5.5", "1.5.6", duckdb2]:
        esp[f"duckdb-{v}"] = [f"duckdb=={v}"]
    return esp


def py(entornos: Path, nombre: str) -> Path:
    """Ruta del intérprete de un entorno."""
    return entornos / nombre / "bin" / "python"


def crea_entornos(entornos: Path, esp: dict, log) -> dict:
    """Crea con uv los entornos que falten y fija sus versiones.

    Si existe `entornos/<nombre>.txt` junto a este módulo, se instala desde
    él (todas las dependencias transitivas con versión exacta); si no, se
    resuelven los requisitos directos y se guarda el resultado congelado.

    Args:
        entornos: directorio raíz de los entornos, fuera del árbol del sitio.
        esp: salida de `especificaciones`.
        log: función de registro.

    Returns:
        Diccionario nombre -> {paquete: versión} de lo instalado.
    """
    DIR_REQ.mkdir(exist_ok=True)
    entornos.mkdir(parents=True, exist_ok=True)
    versiones = {}
    for nombre, reqs in esp.items():
        destino = entornos / nombre
        fijado = DIR_REQ / f"{nombre}.txt"
        if not py(entornos, nombre).exists():
            log(f"se crea el entorno {nombre}")
            subprocess.run(["uv", "venv", "-q", "--python", PYTHON,
                            str(destino)], check=True)
            # con el bytecode compilado, como un entorno de conda: si no,
            # cada proceso hijo compila sus importaciones y lo cronometra
            orden = ["uv", "pip", "install", "-q", "--compile-bytecode",
                     "--python", str(py(entornos, nombre))]
            if fijado.exists():
                subprocess.run(orden + ["-r", str(fijado)], check=True)
            else:
                subprocess.run(orden + reqs, check=True)
        congelado = subprocess.run(
            ["uv", "pip", "freeze", "--python", str(py(entornos, nombre))],
            check=True, capture_output=True, text=True).stdout
        if not fijado.exists():
            fijado.write_text(congelado)
        versiones[nombre] = dict(
            linea.split("==", 1) for linea in congelado.split()
            if "==" in linea)
        for r in reqs:
            paq, ver = r.split("==")
            if versiones[nombre].get(paq) != ver:
                raise RuntimeError(f"{nombre}: {paq} es "
                                   f"{versiones[nombre].get(paq)}, no {ver}")
    return versiones


def enfria(*rutas: str | os.PathLike) -> int:
    """Expulsa de la caché de página los ficheros bajo las rutas.

    `drop_caches` exige root; `posix_fadvise(POSIX_FADV_DONTNEED)` no, y
    actúa fichero a fichero. Se sincroniza antes porque las páginas sucias
    no se descartan. Es el método de la entrada de agosto.

    Args:
        rutas: ficheros o directorios.

    Returns:
        Número de ficheros expulsados.
    """
    os.sync()
    n = 0
    for r in rutas:
        p = Path(r)
        ficheros = [p] if p.is_file() else sorted(p.rglob("*"))
        for f in ficheros:
            if not f.is_file():
                continue
            fd = os.open(f, os.O_RDONLY)
            try:
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
                n += 1
            finally:
                os.close(fd)
    return n


def hay_systemd_run() -> bool:
    """Indica si se puede abrir un ámbito de cgroup de usuario."""
    if not shutil.which("systemd-run"):
        return False
    p = subprocess.run(["systemd-run", "--user", "--scope", "-q",
                        "-p", "MemoryMax=64M", "true"],
                       capture_output=True)
    return p.returncode == 0


def mide(python: Path, codigo: str, *, enfriar: list | None = None,
         tope_gib: float | None = 20, muestreo: bool = False,
         dir_derrame: Path | None = None, cwd: Path | None = None,
         env: dict | None = None, limite_s: float = 1800,
         trabajo: Path, vista_contenedor: bool = False) -> dict:
    """Ejecuta una medición en un proceso nuevo, bajo tope de memoria.

    El lanzador `medir.py` corre dentro del ámbito de cgroup con el
    intérprete del entorno, expulsa de la caché los ficheros indicados,
    arranca el hijo con `python -c codigo` y cronometra su vida entera, como
    se hizo en agosto. Con muestreo, además, lee cada 50 ms la memoria
    anónima del hijo, sus bytes escritos y el tamaño del directorio de
    volcado.

    Args:
        python: intérprete del entorno.
        codigo: programa del hijo.
        enfriar: ficheros o directorios que se expulsan antes de medir.
        tope_gib: MemoryMax del ámbito, en GiB; None para no poner tope.
        muestreo: activa el muestreo de /proc.
        dir_derrame: directorio cuyo tamaño se vigila.
        cwd: directorio de trabajo del hijo.
        env: variables de entorno añadidas al hijo.
        limite_s: tiempo máximo antes de matar al hijo.
        trabajo: directorio donde se deja la especificación.
        vista_contenedor: monta el cgroup del ámbito como raíz de
            /sys/fs/cgroup en un espacio de nombres propio, que es como lo
            ve un proceso dentro de un contenedor.

    Returns:
        Diccionario con la salida del lanzador.
    """
    espec = {"codigo": codigo,
             "enfriar": [str(x) for x in (enfriar or [])],
             "muestreo": muestreo,
             "dir_derrame": str(dir_derrame) if dir_derrame else None,
             "cwd": str(cwd) if cwd else None,
             "env": env or {}, "limite_s": limite_s}
    trabajo.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1(codigo.encode()).hexdigest()[:10]
    f_espec = trabajo / f"espec-{h}-{time.time_ns()}.json"
    f_espec.write_text(json.dumps(espec))
    orden = [str(python), str(AQUI / "medir.py"), str(f_espec)]
    if tope_gib is not None and hay_systemd_run.cache:
        if vista_contenedor:
            orden = ["sh", "-c", VISTA, "sh"] + orden
        orden = ["systemd-run", "--user", "--scope", "-q",
                 "-p", f"MemoryMax={int(tope_gib * 1024)}M",
                 "-p", "MemorySwapMax=0", "-p", "OOMPolicy=continue"] + orden
    p = subprocess.run(orden, capture_output=True, text=True)
    f_espec.unlink(missing_ok=True)
    lineas = [x for x in p.stdout.splitlines() if x.startswith("{")]
    if not lineas:
        return {"rc": None, "error_lanzador": (p.stderr or p.stdout)[-800:]}
    r = json.loads(lineas[-1])
    r["tope_gib"] = tope_gib if hay_systemd_run.cache else None
    return r


hay_systemd_run.cache = None

# sin privilegios: espacio de nombres de usuario, de montaje y de cgroup, y
# el directorio del ámbito montado encima de /sys/fs/cgroup
VISTA = ("P=$(cut -d: -f3 /proc/self/cgroup); exec unshare --user "
         "--map-root-user --mount --cgroup --propagation private sh -c "
         "'mount --bind \"/sys/fs/cgroup$0\" /sys/fs/cgroup && "
         "exec \"$@\"' \"$P\" \"$@\"")


def prepara_cgroup() -> bool:
    """Comprueba una vez si hay ámbitos de cgroup y lo memoriza."""
    hay_systemd_run.cache = hay_systemd_run()
    return hay_systemd_run.cache


def marcas(stdout: str) -> dict:
    """Extrae las líneas `CLAVE valor` que imprimen los hijos."""
    d = {}
    for linea in stdout.splitlines():
        partes = linea.split(" ", 1)
        if len(partes) == 2 and partes[0].isupper():
            d[partes[0]] = partes[1].strip()
    return d


def sha256(ruta: Path) -> str:
    """Huella sha256 de un fichero, leída por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 22), b""):
            h.update(bloque)
    return h.hexdigest()


class Registro:
    """Registro intermedio con marca de tiempo, en pantalla y en fichero."""

    def __init__(self, fichero: Path):
        self.fichero = fichero
        fichero.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, msg: str) -> None:
        linea = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        print(linea, flush=True, file=sys.stderr)
        with open(self.fichero, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
