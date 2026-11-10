#!/usr/bin/env python3
"""Análisis de riesgos de los dos laboratorios con el método de MAGERIT v3,
simplificado y declarado: activos con su valor por dimensión (0 a 10),
amenazas del catálogo del Libro II con una frecuencia de 1 a 5 y una
degradación por dimensión, salvaguardas existentes con una eficacia estimada.

Cálculo, por fila de ``fuentes/riesgos_entrada.csv``:
  impacto_dim  = valor_dim × degradación_dim / 100      (0 a 10)
  impacto      = max(impacto_dim)
  riesgo       = impacto × frecuencia                   (0 a 50)
  residual     = riesgo × (1 − eficacia / 100)
Niveles: crítico ≥ 30, alto ≥ 20, medio ≥ 10, bajo < 10. Apetito de riesgo
declarado: residual ≤ 12 (medio bajo); lo que queda por encima va al plan.

Escribe riesgos.csv (una fila por activo y amenaza) y riesgos_resumen.csv.
"""
import csv
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
F = os.path.join(AQUI, "fuentes")
DIMS = ["D", "I", "C", "A", "T"]
APETITO = 12.0


def nivel(x: float) -> str:
    return "crítico" if x >= 30 else "alto" if x >= 20 else "medio" if x >= 10 else "bajo"


def principal() -> None:
    activos = {r["id"]: r for r in csv.DictReader(open(os.path.join(F, "activos.csv"), encoding="utf-8"))}
    amenazas = {r["codigo"]: r for r in csv.DictReader(open(os.path.join(AQUI, "magerit_amenazas.csv"), encoding="utf-8"))}
    # las amenazas propias de los sistemas de IA (cláusula 6 y anexo B de
    # ISO/IEC 27090:2026) se suman al catálogo convencional de MAGERIT
    amenazas.update({r["codigo"]: r for r in csv.DictReader(open(os.path.join(F, "amenazas_27090.csv"), encoding="utf-8"))})
    filas = []
    for r in csv.DictReader(open(os.path.join(F, "riesgos_entrada.csv"), encoding="utf-8")):
        a = activos[r["activo"]]; am = amenazas.get(r["amenaza"], {"amenaza": "?", "grupo": "?"})
        imp = {d: int(a[d]) * int(r[f"deg_{d}"]) / 100 for d in DIMS}
        dim_max = max(DIMS, key=lambda d: imp[d])
        impacto = imp[dim_max]; frec = int(r["frecuencia"])
        riesgo = impacto * frec; residual = riesgo * (1 - int(r["eficacia"]) / 100)
        filas.append(dict(activo=r["activo"], laboratorio=a["laboratorio"], nombre_activo=a["activo"], amenaza=r["amenaza"],
                          amenaza_nombre=am["amenaza"], grupo=am["grupo"], frecuencia=frec, dimension=dim_max,
                          impacto=round(impacto, 1), riesgo=round(riesgo, 1), nivel=nivel(riesgo), salvaguardas=r["salvaguardas"],
                          eficacia=int(r["eficacia"]), residual=round(residual, 1), nivel_residual=nivel(residual),
                          sobre_apetito="sí" if residual > APETITO else "no"))
    filas.sort(key=lambda x: -x["residual"])
    campos = ["activo", "laboratorio", "nombre_activo", "amenaza", "amenaza_nombre", "grupo", "frecuencia", "dimension", "impacto", "riesgo", "nivel",
              "salvaguardas", "eficacia", "residual", "nivel_residual", "sobre_apetito"]
    with open(os.path.join(AQUI, "riesgos.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos); w.writeheader(); w.writerows(filas)
    # resumen por laboratorio y por nivel, antes y después de las salvaguardas
    res = []
    for lab in ("pam-minimo", "datamart-wikipedia", "rag-sintetico", "total"):
        sub = [x for x in filas if lab == "total" or x["laboratorio"] == lab]
        fila = dict(laboratorio=lab, riesgos=len(sub), sobre_apetito=sum(1 for x in sub if x["sobre_apetito"] == "sí"),
                    riesgo_promedio=round(sum(x["riesgo"] for x in sub) / len(sub), 1), residual_promedio=round(sum(x["residual"] for x in sub) / len(sub), 1),
                    reduccion_pct=round(100 * (1 - sum(x["residual"] for x in sub) / sum(x["riesgo"] for x in sub)), 1))
        for n in ("crítico", "alto", "medio", "bajo"):
            fila[f"inherente_{n}"] = sum(1 for x in sub if x["nivel"] == n)
            fila[f"residual_{n}"] = sum(1 for x in sub if x["nivel_residual"] == n)
        res.append(fila)
    with open(os.path.join(AQUI, "riesgos_resumen.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys())); w.writeheader(); w.writerows(res)
    for r in res:
        print(f"{r['laboratorio']}: {r['riesgos']} riesgos, {r['sobre_apetito']} sobre el apetito ({APETITO}); promedio {r['riesgo_promedio']} → residual {r['residual_promedio']} ({r['reduccion_pct']} % menos); "
              f"residual crítico {r['residual_crítico']}, alto {r['residual_alto']}, medio {r['residual_medio']}, bajo {r['residual_bajo']}")
    print("los cinco mayores residuales:")
    for x in filas[:5]:
        print(f"  {x['activo']} {x['amenaza']} {x['amenaza_nombre']}: riesgo {x['riesgo']} → residual {x['residual']} ({x['nivel_residual']})")


if __name__ == "__main__":
    principal()
