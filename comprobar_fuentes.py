"""Pregunta a cada fuente pública si sigue respondiendo.

Hace una petición mínima a cada dirección de `fuentes.csv` y dice cuáles
contestan. No descarga ninguna instantánea ni escribe nada: volver a tomar
un dato es trabajo de cada `generar.py`, y cambiaría cifras ya publicadas.
Sale con código 1 si alguna fuente no responde.

Uso:
    python comprobar_fuentes.py
"""
import csv
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
# la misma identificación que usan los generadores: dos fuentes rechazan
# con 403 un agente más largo
CABECERAS = {"User-Agent": "Mozilla/5.0"}
INTENTOS = 3


def pregunta(url: str) -> tuple[int, str]:
    """Pide una dirección y devuelve su código de estado.

    Args:
        url: dirección que se comprueba.

    Returns:
        El código HTTP, o 0 si no hubo respuesta, y el motivo.
    """
    motivo = ""
    for intento in range(INTENTOS):
        try:
            req = urllib.request.Request(url, headers=CABECERAS)
            with urllib.request.urlopen(req, timeout=45) as r:
                r.read(512)  # basta el principio para saber que contesta
                return r.status, ""
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                return e.code, e.reason
            motivo = f"{e.code} {e.reason}"
        except Exception as e:  # red caída, certificado, tiempo agotado
            motivo = type(e).__name__
        time.sleep(10 * (intento + 1))
    return 0, motivo


def main() -> int:
    """Recorre las fuentes e imprime el resultado de cada una."""
    with open(RAIZ / "fuentes.csv", encoding="utf-8", newline="") as f:
        fuentes = list(csv.DictReader(f))
    caidas = []
    for fila in fuentes:
        codigo, motivo = pregunta(fila["url"])
        bien = 200 <= codigo < 300
        marca = "responde" if bien else "NO RESPONDE"
        print(f"  {marca:12s} {codigo or '---':>3}  {fila['fuente']}"
              f"  [{fila['mediciones']}]  {motivo}")
        if not bien:
            caidas.append(fila["fuente"])
        time.sleep(1)
    print(f"\n{len(fuentes) - len(caidas)} de {len(fuentes)} fuentes "
          "responden")
    if caidas:
        print("no responden: " + "; ".join(caidas))
    return 1 if caidas else 0


if __name__ == "__main__":
    sys.exit(main())
