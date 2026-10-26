"""Lanzador de una medición; corre dentro del ámbito de cgroup.

Recibe la ruta de una especificación JSON, expulsa de la caché los ficheros
pedidos, ejecuta el hijo con `python -c` y cronometra su vida entera (el
método de la entrada de agosto: arranque e importaciones incluidos). Con
muestreo, lee cada 50 ms /proc del hijo y el tamaño del directorio de
volcado. Imprime una línea JSON con todo; solo usa la biblioteca estándar.
"""

import json
import os
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path


def enfria(rutas: list) -> None:
    """Se expulsan de la caché de página los ficheros bajo las rutas."""
    os.sync()
    for r in rutas:
        p = Path(r)
        ficheros = [p] if p.is_file() else sorted(p.rglob("*"))
        for f in ficheros:
            if f.is_file():
                fd = os.open(f, os.O_RDONLY)
                try:
                    os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
                finally:
                    os.close(fd)


def tam_dir(ruta: str) -> int:
    """Suma el tamaño de los ficheros bajo una ruta; tolera borrados."""
    total = 0
    pila = [ruta]
    while pila:
        d = pila.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            pila.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_blocks
                    except FileNotFoundError:
                        pass
        except (FileNotFoundError, NotADirectoryError):
            pass
    return total * 512


def lee_proc(pid: int) -> dict:
    """Lee memoria residente y E/S del proceso; vacío si ya no existe."""
    d = {}
    try:
        with open(f"/proc/{pid}/status") as f:
            for linea in f:
                k, _, v = linea.partition(":")
                if k in ("VmRSS", "RssAnon", "RssFile", "VmHWM"):
                    d[k] = int(v.split()[0])
        with open(f"/proc/{pid}/io") as f:
            for linea in f:
                k, _, v = linea.partition(":")
                d[k] = int(v)
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass
    return d


class Muestreador(threading.Thread):
    """Guarda los máximos de memoria anónima, residente y volcado."""

    def __init__(self, pid: int, dir_derrame: str | None):
        super().__init__(daemon=True)
        self.pid = pid
        self.dir_derrame = dir_derrame
        self.fin = threading.Event()
        self.max_anon = 0
        self.max_rss = 0
        self.max_derrame = 0
        self.ultimo = {}

    def run(self) -> None:
        n = 0
        while not self.fin.is_set():
            d = lee_proc(self.pid)
            if d:
                self.ultimo = d
                self.max_anon = max(self.max_anon, d.get("RssAnon", 0))
                self.max_rss = max(self.max_rss, d.get("VmRSS", 0))
            # el directorio se recorre cada 0,5 s, que es más caro
            if self.dir_derrame and n % 10 == 0:
                self.max_derrame = max(self.max_derrame,
                                       tam_dir(self.dir_derrame))
            n += 1
            self.fin.wait(0.05)


VMSTAT = ("pswpin", "pswpout", "compact_stall", "compact_fail",
          "thp_fault_alloc", "thp_fault_fallback")


def lee_vmstat() -> dict:
    """Contadores del sistema: swap, compactación y páginas enormes."""
    d = {}
    try:
        with open("/proc/vmstat") as f:
            for linea in f:
                k, _, v = linea.partition(" ")
                if k in VMSTAT:
                    d[k] = int(v)
    except OSError:
        pass
    return d


def lee_cgroup() -> dict:
    """Lee el tope, el pico y los avisos de memoria del propio ámbito."""
    try:
        ruta = open("/proc/self/cgroup").read().strip().split(":", 2)[2]
        base = Path("/sys/fs/cgroup" + ruta)
        d = {"memory.max": (base / "memory.max").read_text().strip(),
             "memory.peak": (base / "memory.peak").read_text().strip()}
        for linea in (base / "memory.events").read_text().split("\n"):
            if linea:
                k, v = linea.split()
                d["events." + k] = int(v)
        return d
    except (OSError, IndexError, ValueError):
        return {}


def main(f_espec: str) -> None:
    espec = json.loads(Path(f_espec).read_text())
    enfria(espec["enfriar"])
    vm0 = lee_vmstat()
    env = dict(os.environ)
    # el hijo usa el bytecode ya compilado del entorno, como en agosto
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env.update(espec["env"])
    t0 = time.perf_counter()
    p = subprocess.Popen([sys.executable, "-c", espec["codigo"]],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, cwd=espec["cwd"], env=env)
    m = None
    if espec["muestreo"]:
        m = Muestreador(p.pid, espec["dir_derrame"])
        m.start()
    agotado = False
    try:
        out, err = p.communicate(timeout=espec["limite_s"])
    except subprocess.TimeoutExpired:
        agotado = True
        p.kill()
        out, err = p.communicate()
    dt = time.perf_counter() - t0
    if m:
        m.fin.set()
        m.join()
    vm1 = lee_vmstat()
    hijos = resource.getrusage(resource.RUSAGE_CHILDREN)
    r = {"rc": p.returncode, "agotado": agotado,
         "seg_pared": dt, "maxrss_hijo_kb": hijos.ru_maxrss,
         "stdout": out[-20000:], "stderr": err[-3000:],
         "cgroup": lee_cgroup(),
         "swap_entradas": vm1.get("pswpin", 0) - vm0.get("pswpin", 0),
         "swap_salidas": vm1.get("pswpout", 0) - vm0.get("pswpout", 0),
         "vmstat": {k: vm1.get(k, 0) - vm0.get(k, 0) for k in VMSTAT}}
    if m:
        r["max_rss_anon_kb"] = m.max_anon
        r["max_vmrss_kb"] = m.max_rss
        r["max_derrame_bytes"] = m.max_derrame
        r["io_final"] = m.ultimo
    print(json.dumps(r))


if __name__ == "__main__":
    main(sys.argv[1])
