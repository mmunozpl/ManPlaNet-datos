"""Las nueve amenazas de ISO/IEC 27090:2026 frente a lo que ya se cataloga.

Toma el catálogo público de MITRE ATLAS (técnicas, tácticas y casos de
estudio) y lo reparte entre las nueve amenazas de la cláusula 6 de la norma
(6.2 a 6.10) o fuera de ellas, con una regla escrita por técnica; y recoge
las correspondencias de la taxonomía de NIST AI 100-2 E2025, de la lista
OWASP Top 10 para aplicaciones con LLM (2025) y del artículo 15.5 del
Reglamento (UE) 2024/1689 con esas mismas nueve amenazas. Escribe los CSV
junto a sí mismo.

Uso:
    python generar.py              # descarga ATLAS.yaml y escribe los CSV
    python generar.py --atlas F    # usa un ATLAS.yaml ya descargado

Fuentes: github.com/mitre-atlas/atlas-data (dist/ATLAS.yaml, licencia
Apache-2.0); NIST AI 100-2 E2025, índice (páginas 4 a 54); OWASP Top 10 for
LLM Applications 2025; Reglamento (UE) 2024/1689, artículo 15.5. La norma
ISO/IEC 27090:2026 no es pública: las nueve amenazas se nombran por el título
de sus cláusulas. Ningún dato de ninguna persona interviene.
"""

import argparse
import collections
import csv
import json
import re
import urllib.request
from pathlib import Path

import yaml

AQUI = Path(__file__).resolve().parent
ATLAS_URL = ("https://raw.githubusercontent.com/mitre-atlas/atlas-data/"
             "main/dist/ATLAS.yaml")
UA = {"User-Agent": "Mozilla/5.0"}

# las nueve amenazas de la cláusula 6 de ISO/IEC 27090:2026
CLAUSULAS = {
    "6.2": "envenenamiento de datos",
    "6.3": "evasión",
    "6.4": "inferencia de pertenencia",
    "6.5": "exfiltración del modelo",
    "6.6": "inversión del modelo",
    "6.7": "envenenamiento directo del modelo",
    "6.8": "salida sensible del modelo",
    "6.9": "inyección de prompt",
    "6.10": "salida con ataques de inyección",
}
FUERA = "fuera"
ANEXO_B = "anexo B"

# regla por técnica de ATLAS: una subtécnica hereda la de su técnica raíz
# salvo que tenga la suya. Lo no listado queda «fuera» (reconocimiento,
# preparación, acceso, recolección, movimiento, impacto genérico), que la
# norma deja a ISO/IEC 27002; el anexo B recoge las versiones para IA de
# tres ataques convencionales (cadena de suministro, denegación de servicio
# y puertas traseras), y ahí van las técnicas de ATLAS de esa familia.
MAPA = {
    ANEXO_B: ["AML.T0010", "AML.T0104", "AML.T0109", "AML.T0110", "AML.T0111",
              "AML.T0011.002", "AML.T0060", "AML.T0029", "AML.T0046",
              "AML.T0034"],
    "6.2": ["AML.T0019", "AML.T0020", "AML.T0059", "AML.T0070", "AML.T0080",
            "AML.T0099", "AML.T0010.002", "AML.T0043.004"],
    "6.3": ["AML.T0015", "AML.T0043", "AML.T0031"],
    "6.4": ["AML.T0024.000"],
    "6.5": ["AML.T0024.002", "AML.T0005.001", "AML.T0048.004"],
    "6.6": ["AML.T0024.001"],
    "6.7": ["AML.T0018", "AML.T0058", "AML.T0010.003", "AML.T0076",
            "AML.T0081"],
    "6.8": ["AML.T0057", "AML.T0056", "AML.T0069", "AML.T0085", "AML.T0082",
            "AML.T0024"],
    "6.9": ["AML.T0051", "AML.T0054", "AML.T0065", "AML.T0066", "AML.T0071",
            "AML.T0068", "AML.T0093", "AML.T0094", "AML.T0061", "AML.T0092",
            "AML.T0100"],
    "6.10": ["AML.T0077", "AML.T0067", "AML.T0053", "AML.T0086", "AML.T0101",
             "AML.T0102"],
}
MOTIVOS = {
    "AML.T0024": "exfiltración por la API de inferencia: la técnica raíz "
                 "agrupa pertenencia, inversión y extracción; cada subtécnica "
                 "va a la suya",
    "AML.T0043.004": "insertar un disparador de puerta trasera es parte del "
                     "envenenamiento de datos",
    "AML.T0031": "erosionar la integridad del modelo con entradas es evasión "
                 "sostenida",
    "AML.T0054": "el jailbreak entra por el prompt directo; la norma no le da "
                 "cláusula propia",
    "AML.T0081": "alterar la configuración del agente es manipular el modelo "
                 "desplegado",
    "AML.T0082": "las credenciales recogidas del índice RAG salen por la "
                 "salida del modelo",
    "AML.T0053": "la invocación de herramientas es la salida del modelo "
                 "convertida en acción",
}

# correspondencias con las otras tres referencias; «—» en la columna de la
# cláusula es que la referencia nombra algo que la norma no recoge en las
# nueve (va a su anexo B o a 27002). Páginas del NIST, las de su índice.
NIST = [
    ("2.2", "Evasion Attacks", 11, "6.3"),
    ("2.3.1", "Availability Poisoning", 19, "6.2"),
    ("2.3.2", "Targeted Poisoning", 21, "6.2"),
    ("2.3.3", "Backdoor Poisoning", 22, "6.2"),
    ("2.3.4", "Model Poisoning", 26, "6.7"),
    ("2.4.1", "Data Reconstruction", 28, "6.6"),
    ("2.4.2", "Membership Inference", 29, "6.4"),
    ("2.4.3", "Property Inference", 30, "6.6"),
    ("2.4.4", "Model Extraction", 31, "6.5"),
    ("3.2.1", "Data Poisoning Attacks (supply chain)", 42, "6.2"),
    ("3.2.2", "Model Poisoning Attacks (supply chain)", 42, "6.7"),
    ("3.3.1", "Direct Prompting: Attack Techniques", 44, "6.9"),
    ("3.3.2", "Direct Prompting: Information Extraction", 46, "6.8"),
    ("3.4.1", "Indirect Prompt Injection: Availability Attacks", 51, "6.9"),
    ("3.4.2", "Indirect Prompt Injection: Integrity Attacks", 51, "6.9"),
    ("3.4.3", "Indirect Prompt Injection: Privacy Compromise", 52, "6.8"),
    ("3.5", "Security of Agents", 54, "6.10"),
]
OWASP = [
    ("LLM01:2025", "Prompt Injection", "6.9"),
    ("LLM02:2025", "Sensitive Information Disclosure", "6.8"),
    ("LLM03:2025", "Supply Chain", FUERA),
    ("LLM04:2025", "Data and Model Poisoning", "6.2; 6.7"),
    ("LLM05:2025", "Improper Output Handling", "6.10"),
    ("LLM06:2025", "Excessive Agency", "6.10"),
    ("LLM07:2025", "System Prompt Leakage", "6.8"),
    ("LLM08:2025", "Vector and Embedding Weaknesses", "6.2; 6.8"),
    ("LLM09:2025", "Misinformation", FUERA),
    ("LLM10:2025", "Unbounded Consumption", FUERA),
]
AI_ACT = [
    ("art. 15.5", "data poisoning", "6.2"),
    ("art. 15.5", "model poisoning", "6.7"),
    ("art. 15.5", "adversarial examples or model evasion", "6.3"),
    ("art. 15.5", "confidentiality attacks", "6.4; 6.5; 6.6; 6.8"),
    ("art. 15.5", "model flaws", FUERA),
]


def nombre(cl: str) -> str:
    """Nombre de la amenaza, del anexo B o de lo que queda fuera."""
    if cl == ANEXO_B:
        return "anexo B: versiones para IA de ataques convencionales"
    return CLAUSULAS.get(cl, "fuera de las nueve")


def orden(cl: str) -> tuple:
    """Orden de presentación: las nueve, el anexo B y lo de fuera."""
    if cl in CLAUSULAS:
        return (0, float(cl))
    return (1, 0.0) if cl == ANEXO_B else (2, 0.0)


def descargar(destino: Path) -> None:
    """Descarga ATLAS.yaml si no está junto al guion."""
    req = urllib.request.Request(ATLAS_URL, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        destino.write_bytes(r.read())


def clausula_de(tid: str) -> tuple[str, str]:
    """Cláusula de una técnica y el motivo, con herencia de la raíz."""
    for cl, ids in MAPA.items():
        if tid in ids:
            return cl, MOTIVOS.get(tid, "regla por técnica")
    raiz = tid.split(".")[0] + "." + tid.split(".")[1] if tid.count(".") == 2 else None
    if raiz:
        for cl, ids in MAPA.items():
            if raiz in ids:
                return cl, "hereda la de su técnica raíz " + raiz
    return FUERA, "ataque convencional, reconocimiento, preparación o impacto genérico"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--atlas", type=Path, default=AQUI / "ATLAS.yaml")
    a = p.parse_args()
    if not a.atlas.exists():
        descargar(a.atlas)
    d = yaml.safe_load(a.atlas.read_text(encoding="utf-8"))
    m = d["matrices"][0]
    tacticas = {t["id"]: t["name"] for t in m["tactics"]}
    tecnicas = m["techniques"]
    casos = d["case-studies"]

    # 1. cada técnica con su cláusula
    filas = []
    raiz_de = {}
    for t in tecnicas:
        tid = t["id"]
        es_sub = bool(re.match(r"AML\.T\d{4}\.\d{3}$", tid))
        if es_sub:
            raiz_de[tid] = tid.rsplit(".", 1)[0]
        cl, motivo = clausula_de(tid)
        tac = t.get("tactics") or []
        filas.append({
            "tecnica": tid, "nombre": t["name"],
            "nivel": "subtécnica" if es_sub else "raíz",
            "tacticas": "; ".join(tacticas.get(x, x) for x in tac),
            "madurez": t.get("maturity", ""),
            "clausula": cl,
            "amenaza": nombre(cl),
            "motivo": motivo,
        })
    # las subtécnicas sin tácticas propias heredan las de su raíz
    tac_raiz = {f["tecnica"]: f["tacticas"] for f in filas if f["nivel"] == "raíz"}
    for f in filas:
        if f["nivel"] == "subtécnica" and not f["tacticas"]:
            f["tacticas"] = tac_raiz.get(raiz_de[f["tecnica"]], "")
    escribe("atlas_tecnicas_27090.csv", filas)

    # 2. casos de estudio: qué cláusulas toca cada uno
    cl_de = {f["tecnica"]: f["clausula"] for f in filas}
    filas_casos = []
    for c in casos:
        usadas = [pr.get("technique") for pr in c["procedure"] if pr.get("technique")]
        cls = sorted({cl_de.get(u, FUERA) for u in usadas}, key=orden)
        filas_casos.append({
            "caso": c["id"], "nombre": c["name"],
            "fecha": str(c.get("incident-date", ""))[:10],
            "tipo": c.get("case-study-type", ""),
            "tecnicas": len(usadas),
            "clausulas": "; ".join(cls),
            "solo_fuera": int(all(x not in CLAUSULAS for x in cls)),
        })
    escribe("atlas_casos_27090.csv", filas_casos)

    # 3. resumen por cláusula
    resumen = []
    for cl in list(CLAUSULAS) + [ANEXO_B, FUERA]:
        de = [f for f in filas if f["clausula"] == cl]
        mad = collections.Counter(f["madurez"] for f in de)
        toca = [c for c in filas_casos if cl in c["clausulas"].split("; ")]
        resumen.append({
            "clausula": cl, "amenaza": nombre(cl),
            "tecnicas": len(de),
            "raiz": sum(f["nivel"] == "raíz" for f in de),
            "subtecnicas": sum(f["nivel"] == "subtécnica" for f in de),
            "realized": mad.get("realized", 0),
            "demonstrated": mad.get("demonstrated", 0),
            "feasible": mad.get("feasible", 0),
            "casos": len(toca),
            "incidentes": sum(c["tipo"] == "incident" for c in toca),
            "ejercicios": sum(c["tipo"] == "exercise" for c in toca),
            "nist": sum(1 for n in NIST if cl in n[3].split("; ")),
            "owasp": sum(1 for o in OWASP if cl in o[2].split("; ")),
            "ai_act": sum(1 for x in AI_ACT if cl in x[2].split("; ")),
        })
    escribe("resumen_27090.csv", resumen)

    # 3b. mitigaciones de ATLAS: qué cláusulas cubre cada una (por las
    # técnicas que declara tratar) y cuántas cubren cada cláusula
    mits = d.get("mitigations") or m.get("mitigations") or []
    filas_mit = []
    for x in mits:
        tids = [y["id"] for y in (x.get("techniques") or [])]
        cls = sorted({cl_de.get(u, FUERA) for u in tids}, key=orden)
        filas_mit.append({"mitigacion": x["id"], "nombre": x["name"],
                          "categoria": x.get("category", ""),
                          "tecnicas": len(tids),
                          "tecnicas_en_las_nueve": sum(cl_de.get(u, FUERA) in CLAUSULAS for u in tids),
                          "clausulas": "; ".join(cls)})
    escribe("atlas_mitigaciones_27090.csv", filas_mit)
    for r in resumen:
        r["mitigaciones"] = sum(r["clausula"] in f["clausulas"].split("; ") for f in filas_mit)
    escribe("resumen_27090.csv", resumen)

    # 4. casos por año y por tipo
    anios = collections.Counter((c["fecha"][:4], c["tipo"]) for c in filas_casos)
    escribe("atlas_casos_anio.csv", [
        {"anio": y, "incidentes": anios.get((y, "incident"), 0),
         "ejercicios": anios.get((y, "exercise"), 0)}
        for y in sorted({k[0] for k in anios})])

    # 5. correspondencias de las otras referencias
    corr = ([{"fuente": "NIST AI 100-2 E2025", "elemento": f"{n[0]} {n[1]}",
              "pagina": n[2], "clausula": n[3]} for n in NIST]
            + [{"fuente": "OWASP Top 10 for LLM Applications 2025",
                "elemento": f"{o[0]} {o[1]}", "pagina": "", "clausula": o[2]}
               for o in OWASP]
            + [{"fuente": "Reglamento (UE) 2024/1689", "elemento": f"{x[0]} {x[1]}",
                "pagina": "", "clausula": x[2]} for x in AI_ACT])
    escribe("correspondencias_27090.csv", corr)

    # 6. volúmenes
    dentro = sum(r["tecnicas"] for r in resumen if r["clausula"] in CLAUSULAS)
    anexo_b = sum(r["tecnicas"] for r in resumen if r["clausula"] == ANEXO_B)
    vol = {
        "atlas_version": d.get("version"),
        "atlas_url": ATLAS_URL,
        "tacticas": len(tacticas), "tecnicas": len(filas),
        "tecnicas_raiz": sum(f["nivel"] == "raíz" for f in filas),
        "subtecnicas": sum(f["nivel"] == "subtécnica" for f in filas),
        "tecnicas_en_las_nueve": dentro,
        "tecnicas_anexo_b": anexo_b,
        "tecnicas_fuera": len(filas) - dentro - anexo_b,
        "casos": len(filas_casos),
        "incidentes": sum(c["tipo"] == "incident" for c in filas_casos),
        "ejercicios": sum(c["tipo"] == "exercise" for c in filas_casos),
        "casos_solo_fuera": sum(c["solo_fuera"] for c in filas_casos),
        "casos_en_las_nueve": sum(any(x in CLAUSULAS for x in c["clausulas"].split("; ")) for c in filas_casos),
        "casos_primero": min(c["fecha"] for c in filas_casos),
        "casos_ultimo": max(c["fecha"] for c in filas_casos),
        "mitigaciones_atlas": len(mits),
        "mitigaciones_que_cubren_alguna_de_las_nueve": sum(any(c in CLAUSULAS for c in f["clausulas"].split("; ")) for f in filas_mit),
        "nist_elementos": len(NIST), "owasp_elementos": len(OWASP),
        "ai_act_elementos": len(AI_ACT),
    }
    (AQUI / "volumenes.json").write_text(
        json.dumps(vol, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(vol, ensure_ascii=False, indent=1))
    for r in resumen:
        print(f"{r['clausula']:>5} {r['amenaza']:<36} técnicas {r['tecnicas']:3d} "
              f"(realized {r['realized']:2d}) · casos {r['casos']:2d} "
              f"(incidentes {r['incidentes']:2d})")


def escribe(nombre: str, filas: list[dict]) -> None:
    """Escribe un CSV junto al guion."""
    with open(AQUI / nombre, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


if __name__ == "__main__":
    main()
