"""Construye la aplicación de escritorio para el sistema en que se ejecuta.

PyInstaller no compila para otros sistemas: el ejecutable de Windows se
construye en Windows y el de macOS en macOS (a mano o con el flujo de
.github/workflows/construir.yml). El resultado queda en dist/ como carpeta y
como zip con el nombre del sistema.

Uso:
    uv run --group construir python construir.py
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import PyInstaller.__main__

AQUI = Path(__file__).resolve().parent
NOMBRE = "FirmaManPla"


def main() -> None:
    """Llama a PyInstaller con los recursos y el icono de cada sistema."""
    sep = os.pathsep
    if sys.platform.startswith("win"):
        sistema, icono = "windows", AQUI / "recursos" / "icono.ico"
    elif sys.platform == "darwin":
        # PyInstaller convierte el png a icns con pillow
        sistema, icono = "macos", AQUI / "recursos" / "icono.png"
    else:
        sistema, icono = "linux", AQUI / "recursos" / "icono.png"
    PyInstaller.__main__.run([
        str(AQUI / "firma_gui.py"),
        "--name", NOMBRE,
        "--windowed",
        "--noconfirm",
        "--clean",
        "--icon", str(icono),
        "--add-data", f"{AQUI / 'confianza'}{sep}confianza",
        "--add-data", f"{AQUI / 'recursos'}{sep}recursos",
        "--collect-submodules", "pyhanko",
        "--collect-submodules", "pyhanko_certvalidator",
        # reportlab carga sus códigos de barras de forma dinámica
        "--collect-submodules", "reportlab.graphics.barcode",
        "--osx-bundle-identifier", "net.manpla.firma-pdf",
        "--distpath", str(AQUI / "dist"),
        "--workpath", str(AQUI / "build"),
        "--specpath", str(AQUI / "build"),
    ])
    # se empaqueta en zip con el sistema y la arquitectura en el nombre
    arquitectura = platform.machine().lower()
    origen = AQUI / "dist" / (f"{NOMBRE}.app" if sistema == "macos"
                              else NOMBRE)
    zip_base = AQUI / "dist" / f"{NOMBRE}-{sistema}-{arquitectura}"
    if sistema == "macos":
        # ditto conserva los enlaces simbólicos y la firma ad hoc del .app;
        # make_archive los convertiría en copias y macOS lo daría por dañado
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(origen),
                        f"{zip_base}.zip"], check=True)
    else:
        shutil.make_archive(str(zip_base), "zip", origen.parent,
                            origen.name)
    print(f"construido: {origen}\nzip: {zip_base}.zip")


if __name__ == "__main__":
    main()
