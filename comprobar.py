"""Ejecuta los cuadernos de lectura y dice cuáles siguen funcionando.

Cada cuaderno se ejecuta entero, desde su carpeta, con el dato de al lado.
No se escribe nada en ellos: el resultado se queda en memoria. De lo que
cada cuaderno imprime (tablas y texto, sin las figuras) se calcula una
huella, y se compara con la guardada en `huellas.json` cuando el entorno es
el del bloqueo: así se sabe que el cuaderno funciona y también que sigue
diciendo lo mismo. Sale con código 1 si algo falla o cambia.

Uso:
    uv run python comprobar.py            # todos
    uv run python comprobar.py kev ijepa  # solo esas mediciones
    uv run python comprobar.py --fijar    # guarda las huellas de hoy
"""
import hashlib
import importlib.metadata as md
import json
import platform
import re
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient

RAIZ = Path(__file__).resolve().parent
HUELLAS = RAIZ / "huellas.json"
PAQUETES = ("pandas", "matplotlib", "numpy")
# mediciones cuyo dato se renueva a diario: se ejecutan, pero no tienen
# una huella fija que comparar
VIVAS = {"vigencia-boe"}


def entorno() -> dict[str, str]:
    """Versiones que deciden cómo se imprime una tabla."""
    v = {"python": ".".join(platform.python_version_tuple()[:2])}
    v.update({p: md.version(p) for p in PAQUETES})
    return v


def impreso(nb) -> str:
    """Texto que imprime un cuaderno ya ejecutado, sin las figuras."""
    trozos = []
    for celda in nb.cells:
        for s in celda.get("outputs", []):
            if s.output_type == "stream":
                # los avisos van por stderr y llevan rutas temporales
                if s.name == "stdout":
                    trozos.append(s.text)
            elif s.output_type in ("execute_result", "display_data"):
                plano = s.data.get("text/plain", "")
                # la figura se identifica por su tamaño, no por su dirección
                if "image/png" not in s.data and "image/svg+xml" not in s.data:
                    trozos.append(plano)
    lineas = [l.rstrip() for t in trozos for l in t.splitlines()]
    # la dirección de memoria de un objeto cambia en cada ejecución
    return re.sub(r"0x[0-9a-f]+", "0x", "\n".join(lineas))


def ejecutar(cuaderno: Path) -> tuple[bool, float, str, str]:
    """Ejecuta un cuaderno en su carpeta.

    Args:
        cuaderno: ruta del fichero .ipynb.

    Returns:
        Si terminó sin error, los segundos que tardó, la última línea del
        error si lo hubo y la huella de lo impreso.
    """
    nb = nbformat.read(cuaderno, as_version=4)
    cliente = NotebookClient(
        nb, timeout=600, kernel_name="python3",
        resources={"metadata": {"path": str(cuaderno.parent)}},
    )
    t0 = time.perf_counter()
    try:
        cliente.execute()
    except Exception as e:  # se informa de cualquier fallo, sin cortar
        lineas = [l for l in str(e).strip().splitlines() if l.strip()]
        return False, time.perf_counter() - t0, lineas[-1][:200], ""
    huella = hashlib.sha256(impreso(nb).encode("utf-8")).hexdigest()[:16]
    return True, time.perf_counter() - t0, "", huella


def main() -> int:
    """Recorre los cuadernos pedidos e imprime el resultado de cada uno."""
    args = sys.argv[1:]
    fijar = "--fijar" in args
    pedidos = {a for a in args if not a.startswith("--")}
    cuadernos = sorted(RAIZ.glob("*/reproducir.ipynb"))
    if pedidos:
        cuadernos = [c for c in cuadernos if c.parent.name in pedidos]
    aqui = entorno()
    guardado = (json.loads(HUELLAS.read_text(encoding="utf-8"))
                if HUELLAS.exists() else {"entorno": {}, "cuadernos": {}})
    mismo = guardado["entorno"] == aqui
    print("Python {python} · pandas {pandas}, matplotlib {matplotlib}, "
          "numpy {numpy}".format(**aqui))
    if not mismo and not fijar:
        print("entorno distinto del bloqueo: se comprueba que funcionan, "
              "no las huellas")
    print(f"cuadernos: {len(cuadernos)}\n")
    fallos, distintos, nuevas = [], [], {}
    for c in cuadernos:
        nombre = c.parent.name
        bien, seg, error, huella = ejecutar(c)
        nota = error
        if nombre in VIVAS:
            huella = "dato vivo"
        nuevas[nombre] = huella
        if bien and mismo and not fijar and nombre not in VIVAS:
            esperada = guardado["cuadernos"].get(nombre)
            if esperada is None:
                nota = "sin huella guardada"
            elif esperada != huella:
                nota = "imprime otra cosa que la guardada"
                distintos.append(nombre)
        marca = "bien " if bien and nombre not in distintos else "FALLA"
        print(f"  {marca}  {nombre:22s} {seg:5.1f} s  {huella:16s}  {nota}")
        if not bien:
            fallos.append(nombre)
    print(f"\n{len(cuadernos) - len(fallos)} de {len(cuadernos)} "
          "cuadernos se ejecutan sin error")
    if fallos:
        print("fallan: " + ", ".join(fallos))
    if mismo and not fijar:
        fijos = [c for c in cuadernos if c.parent.name not in VIVAS
                 and c.parent.name not in fallos]
        print(f"{len(fijos) - len(distintos)} de {len(fijos)} imprimen lo "
              "mismo que la huella guardada")
    if distintos:
        print("cambian: " + ", ".join(distintos))
    if fijar and not fallos and not pedidos:
        HUELLAS.write_text(json.dumps(
            {"entorno": aqui, "cuadernos": nuevas},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"huellas guardadas en {HUELLAS.name}")
    return 1 if fallos or distintos else 0


if __name__ == "__main__":
    sys.exit(main())
