#!/usr/bin/env python3
"""Tendencias del vocabulario hacia la AGI en arXiv, por cuota y por año.

Cuenta, para cada término y cada año, cuántos artículos de cs.LG, cs.AI,
cs.CL y cs.CV llevan el término en el resumen, y lo divide por el total de
artículos de esas categorías ese año. Lee el recuento de
`opensearch:totalResults` con `max_results=1` —`max_results=0` da error 500—
y espera entre consultas, como pide arXiv.

Dos cosas del buscador que gobiernan el método y se dejan comprobadas en la
propia salida: lematiza, de modo que una palabra acuñada puede devolver el
recuento de su raíz; y el guion crea tokens distintos en algunos compuestos y
en otros no. Cada término lleva escrita su consulta exacta.
"""
import csv
import datetime
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

CATS = "(cat:cs.LG OR cat:cs.AI OR cat:cs.CL OR cat:cs.CV)"
ANIOS = list(range(2018, 2027))
HOY = datetime.date.today()
PAUSA = 3.5
DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo

# término visible -> consulta exacta sobre el resumen
TERMINOS = {
    "world model": 'abs:"world model"',
    "chain-of-thought": 'abs:"chain-of-thought"',
    "test-time compute": 'abs:"test-time compute"',
    "scaling law": 'abs:"scaling law"',
    "in-context learning": 'abs:"in-context learning"',
    "continual learning": 'abs:"continual learning"',
    "self-supervised": 'abs:"self-supervised"',
    "neurosymbolic": '(abs:"neurosymbolic" OR abs:"neuro-symbolic")',
    "artificial general intelligence": 'abs:"artificial general intelligence"',
    # añadidos el 18-09-2026, segunda entrega de la serie: el vocabulario de la
    # automejora. el buscador lematiza, así que «self-improvement» devuelve
    # también «self-improving» y «self-improve» (véase comprobaciones.csv)
    "self-improvement": 'abs:"self-improvement"',
    "recursive self-improvement": 'abs:"recursive self-improvement"',
    "self-evolving": 'abs:"self-evolving"',
    "reward hacking": 'abs:"reward hacking"',
    # el nombre del destino, frase o sigla, con un OR que deduplica: es la
    # fila que la primera entrega llevaba a mano (5,5 → 21,3 → 24,6 → 17,1)
    "artificial general intelligence o AGI":
        '(abs:"artificial general intelligence" OR abs:"AGI")',
}

# comprobaciones del buscador, que se guardan como evidencia
COMPROBACIONES = [
    ("agentic", 'abs:"agentic"'), ("agent", 'abs:"agent"'),
    ("reasoning", 'abs:"reasoning"'), ("reason", 'abs:"reason"'),
    ("neurosymbolic", 'abs:"neurosymbolic"'),
    ("neuro-symbolic", 'abs:"neuro-symbolic"'),
    ("chain-of-thought", 'abs:"chain-of-thought"'),
    ("chain of thought", 'abs:"chain of thought"'),
    ("self-improvement", 'abs:"self-improvement"'),
    ("self-improving", 'abs:"self-improving"'),
    ("self-improve", 'abs:"self-improve"'),
]


def total(consulta: str) -> int | None:
    """el recuento total de una consulta, sin traer resultados."""
    u = ("https://export.arxiv.org/api/query?search_query="
         + urllib.parse.quote(consulta) + "&max_results=1")
    for _ in range(4):
        try:
            t = urllib.request.urlopen(u, timeout=60).read().decode()
            m = re.search(r"opensearch:totalResults[^>]*>(\d+)<", t)
            if m:
                return int(m.group(1))
        except Exception:
            pass
        time.sleep(6)
    return None


def rango(anio: int) -> str:
    fin = f"{anio}12312359"
    if anio == HOY.year:
        fin = HOY.strftime("%Y%m%d") + "2359"
    return f"submittedDate:[{anio}01010000 TO {fin}]"


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    filas = []
    den = {}
    for a in ANIOS:
        den[a] = total(f"{CATS} AND {rango(a)}")
        print(f"[agi] denominador {a}: {den[a]}")
        time.sleep(PAUSA)
    for nombre, q in TERMINOS.items():
        for a in ANIOS:
            n = total(f"{CATS} AND {q} AND {rango(a)}")
            filas.append({"termino": nombre, "consulta": q, "anio": a,
                          "recuento": n, "denominador": den[a],
                          "por_diez_mil": (round(10000 * n / den[a], 2)
                                           if n is not None and den[a] else ""),
                          "anio_parcial": int(a == HOY.year)})
            time.sleep(PAUSA)
        print(f"[agi] {nombre}: "
              + " ".join(str(f["recuento"]) for f in filas if f["termino"] == nombre))

    with (DESTINO / "cuotas.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader(); w.writerows(filas)

    comp = []
    for nombre, q in COMPROBACIONES:
        n = total(f"{CATS} AND {q} AND {rango(2025)}")
        comp.append({"termino": nombre, "consulta": q, "anio": 2025, "recuento": n})
        time.sleep(PAUSA)
    with (DESTINO / "comprobaciones.csv").open("w", newline="",
                                              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(comp[0]))
        w.writeheader(); w.writerows(comp)

    (DESTINO / "INSTANTANEA.md").write_text(f"""# Instantánea de tendencias del vocabulario hacia la AGI en arXiv

Recuentos, no artículos: `cuotas.csv` guarda cuántos resúmenes de cs.LG,
cs.AI, cs.CL y cs.CV contienen cada término por año, el total de artículos de
esas categorías ese año, y la cuota por diez mil. No guarda ningún artículo.

- API: https://export.arxiv.org/api/query
- Extraído: {HOY.isoformat()}
- Años: {ANIOS[0]}-{ANIOS[-1]} · el {HOY.year} es parcial, hasta el {HOY.isoformat()}
- Categorías del denominador: cs.LG, cs.AI, cs.CL, cs.CV (unión)
- Términos: {len(TERMINOS)}

## Campos de `cuotas.csv`

| Columna | Origen |
|---|---|
| `termino` | nombre visible |
| `consulta` | la consulta exacta enviada, sobre `abs:` |
| `anio`, `anio_parcial` | año de `submittedDate`; 1 si el año no ha terminado |
| `recuento` | `opensearch:totalResults` de la consulta con el rango del año |
| `denominador` | lo mismo, sin término |
| `por_diez_mil` | 10000 · recuento / denominador, cálculo propio |

## `comprobaciones.csv`

Evidencia de dos propiedades del buscador que gobiernan el método, medidas
sobre 2025: lematiza —`agentic` y `agent` devuelven lo mismo, y `reasoning` y
`reason` también—, y el guion crea tokens distintos en `neurosymbolic` frente
a `neuro-symbolic` pero no en `chain-of-thought` frente a `chain of thought`.
Por eso `agentic` y `reasoning` no están en la tabla, y `neurosymbolic` suma
las dos grafías con un OR.
""", encoding="utf-8")
    print(f"[agi] {len(filas)} filas en {DESTINO/'cuotas.csv'}")


if __name__ == "__main__":
    main()
