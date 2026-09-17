#!/usr/bin/env python3
"""Dos transcripciones codificadas del survey de automejora recursiva
(Duan et al., «The Last AI Built by Humans», arXiv 2609.11873v2, 15-09-2026).

1. Los ocho sistemas de su tabla 7 (mecanismos L5), con la codificación
   propia de dos preguntas que el propio survey distingue en la sección
   3.6: si el mecanismo revisado se hereda y gobierna una ronda posterior
   —L5 estructural— y si hay evidencia, con presupuesto comparable y
   evaluación independiente, de que produce sucesores mejores —L5
   efectivo—. Cada fila lleva la frase del survey o de la fuente primaria
   en la que se apoya la codificación.

2. Las trayectorias de la figura 3 (índice HCI a 2026, sección 2.1) y la
   proyección «ilustrativa» de la ecuación 4, R = 100 − 0,22·(100 − T),
   recalculada dominio a dominio para dejar a la vista que cierra el 78 %
   del margen restante en todos por igual.

No mide nada en la red: transcribe cifras publicadas y añade una
codificación explícita. Escribe csv, resumen y ficha junto a sí mismo.
"""
import csv
import datetime
import json
from pathlib import Path

DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo
SURVEY = "arXiv 2609.11873v2 (15-09-2026)"

# tabla 7 del survey más la codificación propia; estructural / efectivo
# toman «sí», «parcial» o «no» y llevan su evidencia
SISTEMAS = [
    {
        "sistema":
            "STOP",
        "fuente":
            "Zelikman et al., COLM 2024, arXiv 2310.02304",
        "cierra_en":
            "la siguiente búsqueda de programas",
        "estado_heredado":
            "código del mejorador",
        "controles_externos":
            "utilidad; modelo base; presupuesto",
        "estructural":
            "sí",
        "efectivo":
            "parcial",
        "evidencia":
            ("un mejorador de cuarta generación superó al semilla en las "
             "cinco tareas de transferencia; las tiradas con modelos más "
             "débiles retrocedieron de media y algunos programas evadieron "
             "presupuestos o explotaron fallos de evaluación (survey, 3.6.1)"),
    },
    {
        "sistema":
            "Gödel Agent",
        "fuente":
            "Yin et al., ACL 2025, arXiv 2410.04444",
        "cierra_en":
            "la siguiente autorrevisión",
        "estado_heredado":
            "código de tarea y de actualización",
        "controles_externos":
            "objetivo de la tarea; acceso en ejecución",
        "estructural":
            "sí",
        "efectivo":
            "no",
        "evidencia":
            ("14 de 100 ensayos en MGSM acabaron por debajo de la política "
             "inicial y el 92 % sufrió caídas temporales; la versión sin "
             "restricciones pide ayuda a GPT-4o (fuente primaria, 6.2)"),
    },
    {
        "sistema":
            "Darwin Gödel Machine",
        "fuente":
            "Zhang et al., ICLR 2026, arXiv 2505.22954",
        "cierra_en":
            "la búsqueda de descendientes",
        "estado_heredado":
            "código del agente; archivo",
        "controles_externos":
            "selección de progenitores; benchmark",
        "estructural":
            "no",
        "efectivo":
            "no",
        "evidencia":
            ("«archive maintenance and parent-selection rules remain outside "
             "self-modification»; «task gains alone do not establish a "
             "better improvement procedure» (survey, 1.3 y 3.6.1); 20,0 → "
             "50,0 % en SWE-bench es ganancia de tarea"),
    },
    {
        "sistema":
            "HyperAgents",
        "fuente":
            "Zhang et al., arXiv 2603.19461, marzo de 2026",
        "cierra_en":
            "la siguiente generación de agentes",
        "estado_heredado":
            "código del agente de tarea y del meta-agente",
        "controles_externos":
            "selección del estudio principal; evaluación",
        "estructural":
            "sí",
        "efectivo":
            "no",
        "evidencia":
            ("a 200 iteraciones, 0,640 con inicialización transferida frente "
             "a 0,630 sin ella, «not statistically significant (p > 0.05)»; "
             "selección de progenitores y evaluación fijas (fuente primaria)"),
    },
    {
        "sistema":
            "Red Queen Gödel Machine",
        "fuente":
            "Iacob et al., arXiv 2606.26294, junio de 2026",
        "cierra_en":
            "la selección de la siguiente época",
        "estado_heredado":
            "evaluador; código del agente",
        "controles_externos":
            "anclaje; calendario de sustitución",
        "estructural":
            "sí",
        "efectivo":
            "parcial",
        "evidencia":
            ("71,7 % de aciertos reservados frente a 69,9 % del sistema "
             "anterior con 1,35-1,72 veces menos tokens; los autores llaman "
             "preliminar a la investigación y las garantías valen dentro de "
             "cada época (fuente primaria)"),
    },
    {
        "sistema":
            "A-Evolve-Training",
        "fuente":
            "Shi et al., arXiv 2606.20657, 2026",
        "cierra_en":
            "la siguiente ronda de investigación",
        "estado_heredado":
            "política de búsqueda; registro de descubrimientos",
        "controles_externos":
            "constitución; benchmark; sustrato",
        "estructural":
            "sí",
        "efectivo":
            "parcial",
        "evidencia":
            ("cuatro rondas autónomas sobre un modelo de 30B, de 0,80 a 0,86 "
             "frente a 0,87 del mejor equipo humano; «policy-level L5 within "
             "a human-defined objective, with no demonstrated autonomous "
             "revision of that objective» (survey, 3.6.3)"),
    },
    {
        "sistema":
            "AIRA2 / Automated Alignment Researchers",
        "fuente":
            "Meta [154]; Anthropic [155], según el survey",
        "cierra_en":
            "los experimentos de la tarea",
        "estado_heredado":
            "artefactos de investigación",
        "controles_externos":
            "arnés de investigación; evaluación",
        "estructural":
            "no",
        "efectivo":
            "no",
        "evidencia":
            ("«automate experiment execution within researcher-designed "
             "workflows. Their reported results concern research outputs, "
             "without establishing inherited changes to the procedures "
             "conducting the research» (survey, 3.6.4)"),
    },
    {
        "sistema":
            "AIDE2",
        "fuente":
            "Weco, blog del 14-07-2026",
        "cierra_en":
            "las siguientes tiradas de investigación",
        "estado_heredado":
            "arnés del agente de investigación",
        "controles_externos":
            "puntuaciones privadas; presupuesto de coste",
        "estructural":
            "sí",
        "efectivo":
            "no",
        "evidencia":
            ("«we do not think this is strong evidence of ignition, given "
             "that AIDE47 is not asymptotically better»; informe técnico "
             "anunciado como pendiente (fuente primaria)"),
    },
]

# figura 3 y sección 2.1 del survey: HCI a 2026 por dominio, y la ecuación 4
HCI_2026 = [
    ("matemáticas avanzadas", 86.4), ("ciencia de posgrado", 85.8),
    ("conocimiento general", 77.2), ("razonamiento jurídico", 64.5),
    ("razonamiento multimodal", 62.2),
    ("amplitud académica de frontera", 60.4),
    ("ingeniería de software", 52.6), ("agentes de búsqueda y terminal", 56.8),
    ("agentes con herramientas", 39.9), ("agente de ciberseguridad", 91.9),
]
FRACCION = 0.22   # R_d = 100 − 0,22·(100 − T_d): cierra el 78 % del margen


def main() -> None:
    """Escribe los dos csv, el resumen y la ficha."""
    with open(DESTINO / "l5-sistemas.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(SISTEMAS[0].keys()))
        w.writeheader(); w.writerows(SISTEMAS)
    filas = []
    for dominio, t in HCI_2026:
        r = 100 - FRACCION * (100 - t)
        filas.append({"dominio": dominio, "hci_2026": t,
                      "margen_restante": round(100 - t, 1),
                      "proyeccion_eq4": round(r, 1),
                      "ganancia_ilustrativa": round(r - t, 1),
                      "fraccion_del_margen_cerrada":
                          round((r - t) / (100 - t), 2)})
    with open(DESTINO / "hci-eq4.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader(); w.writerows(filas)
    cuenta = lambda k, v: sum(1 for s in SISTEMAS if s[k] == v)
    res = {
        "fecha": datetime.date.today().isoformat(), "survey": SURVEY,
        "sistemas": len(SISTEMAS),
        "estructural": {v: cuenta("estructural", v)
                        for v in ("sí", "parcial", "no")},
        "efectivo": {v: cuenta("efectivo", v)
                     for v in ("sí", "parcial", "no")},
        "fraccion_eq4": FRACCION,
        "ganancia_media_eq4": round(
            sum(f["ganancia_ilustrativa"] for f in filas) / len(filas), 1),
    }
    (DESTINO / "resumen.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    ficha = "\n".join([
        "# El survey de automejora recursiva, codificado", "",
        f"Transcripción del {SURVEY} generada el {res['fecha']}. No interviene "
        "ningún dato de ninguna persona ni ninguna consulta a la red: las "
        "cifras son las publicadas y la codificación es propia y "
        "explícita.", "",
        "## `l5-sistemas.csv` — los ocho mecanismos L5 de la tabla 7", "",
        "| Columna | Origen |", "|---|---|",
        "| `sistema`, `fuente` | tabla 7 del survey y la fuente primaria "
        "leída |",
        "| `cierra_en`, `estado_heredado`, `controles_externos` | las tres "
        "columnas de la tabla 7, traducidas |",
        "| `estructural` | codificación propia: el mecanismo revisado persiste "
        "y gobierna una ronda posterior (sí / parcial / no) |",
        "| `efectivo` | codificación propia: evidencia de sucesores mejores "
        "con "
        "presupuesto comparable y evaluación independiente, con significación "
        "(sí / parcial / no) |",
        "| `evidencia` | la frase del survey o de la fuente primaria en la que "
        "se apoya la codificación |", "",
        "## `hci-eq4.csv` — la figura 3 y la ecuación 4", "",
        "| Columna | Origen |", "|---|---|",
        "| `dominio`, `hci_2026` | sección 2.1 del survey, observaciones 1 y "
        "2 |",
        "| `margen_restante` | 100 − HCI |",
        f"| `proyeccion_eq4` | R = 100 − {FRACCION}·(100 − T), ecuación 4 |",
        "| `ganancia_ilustrativa` | R − T |",
        "| `fraccion_del_margen_cerrada` | (R − T) / (100 − T): la misma en "
        "todos los dominios por construcción |", "",
    ])
    (DESTINO / "INSTANTANEA.md").write_text(ficha, encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    for f in filas:
        print(f)


if __name__ == "__main__":
    main()
