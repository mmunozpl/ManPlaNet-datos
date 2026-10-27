"""Las nueve amenazas de ISO/IEC 27090:2026 frente a lo que ya se cataloga.

Toma el catálogo público de MITRE ATLAS (técnicas, tácticas, casos de estudio
y mitigaciones) y lo reparte entre las nueve amenazas de la cláusula 6 de la
norma (6.2 a 6.10), el anexo B o fuera de ellas, con una regla escrita por
técnica; recoge las correspondencias de la taxonomía de NIST AI 100-2 E2025,
de la lista OWASP Top 10 para aplicaciones con LLM (2025) y del artículo 15.5
del Reglamento (UE) 2024/1689 con esas mismas nueve amenazas; y repite el
reparto con las decisiones dudosas cambiadas de sitio, como prueba de
sensibilidad. Escribe los CSV junto a sí mismo.

Uso:
    python generar.py              # descarga la versión fijada y escribe los CSV
    python generar.py --atlas F    # usa un fichero ya descargado

La versión de ATLAS va fijada: la publicación 2026.09 (15-09-2026), formato
6.0.0, fichero `dist/v6/ATLAS-2026.09.yaml` del repositorio público
`mitre-atlas/atlas-data` (licencia Apache-2.0). El fichero `dist/ATLAS.yaml`
de la raíz de ese repositorio es una copia en el formato heredado 5.6.0 que
no se actualiza desde mayo de 2026; `dist/manifest.yaml` dice cuál es la
publicación vigente. La norma ISO/IEC 27090:2026 no es pública: las nueve
amenazas se nombran por el título de sus cláusulas. Ningún dato de ninguna
persona interviene.
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
ATLAS_VERSION = "2026.09"
ATLAS_URL = ("https://raw.githubusercontent.com/mitre-atlas/atlas-data/"
             f"v{ATLAS_VERSION}/dist/v6/ATLAS-{ATLAS_VERSION}.yaml")
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
# preparación, acceso, recolección, movimiento, mando y control, impacto
# genérico, y la IA usada por el atacante para atacar), que la norma remite
# a los controles de ISO/IEC 27002; el anexo B recoge las versiones para IA
# de tres ataques convencionales (cadena de suministro, denegación de
# servicio y puertas traseras), y ahí van las técnicas de esa familia.
MAPA = {
    ANEXO_B: ["AML.T0010", "AML.T0115", "AML.T0109", "AML.T0110", "AML.T0111",
              "AML.T0011.002", "AML.T0060", "AML.T0029", "AML.T0046",
              "AML.T0034", "AML.T0119"],
    "6.2": ["AML.T0115.000", "AML.T0020", "AML.T0059", "AML.T0070", "AML.T0080",
            "AML.T0099", "AML.T0010.002", "AML.T0043.004"],
    "6.3": ["AML.T0015", "AML.T0043", "AML.T0031", "AML.T0129"],
    "6.4": ["AML.T0024.000"],
    "6.5": ["AML.T0024.002", "AML.T0005.001", "AML.T0048.004"],
    "6.6": ["AML.T0024.001"],
    "6.7": ["AML.T0018", "AML.T0115.001", "AML.T0010.003", "AML.T0076",
            "AML.T0081"],
    "6.8": ["AML.T0057", "AML.T0056", "AML.T0069", "AML.T0085", "AML.T0082",
            "AML.T0024", "AML.T0133"],
    "6.9": ["AML.T0051", "AML.T0054", "AML.T0065", "AML.T0066", "AML.T0071",
            "AML.T0068", "AML.T0093", "AML.T0094", "AML.T0061", "AML.T0092",
            "AML.T0100", "AML.T0131", "AML.T0130", "AML.T0134"],
    "6.10": ["AML.T0077", "AML.T0067", "AML.T0053", "AML.T0086", "AML.T0101",
             "AML.T0102"],
}
MOTIVOS = {
    "AML.T0024": "exfiltración por la API de inferencia: la técnica raíz "
                 "agrupa pertenencia, inversión y extracción; cada subtécnica "
                 "va a la suya",
    "AML.T0043.004": "insertar un disparador de puerta trasera es parte del "
                     "envenenamiento de datos",
    "AML.T0129": "un disparador escondido en una entrada multimodal activa "
                 "una puerta trasera: es una entrada preparada, evasión",
    "AML.T0031": "erosionar la integridad del modelo con entradas es evasión "
                 "sostenida",
    "AML.T0054": "el jailbreak entra por el prompt directo; la norma no le da "
                 "cláusula propia",
    "AML.T0081": "alterar la configuración del agente es manipular el modelo "
                 "desplegado",
    "AML.T0018.003": "alterar la lógica que construye el prompt es manipular "
                     "el modelo desplegado",
    "AML.T0082": "las credenciales recogidas del índice RAG salen por la "
                 "salida del modelo",
    "AML.T0133": "descubrir las capacidades del agente por sus respuestas es "
                 "salida que revela de más",
    "AML.T0053": "la invocación de herramientas es la salida del modelo "
                 "convertida en acción",
    "AML.T0131": "un enlace preparado inyecta instrucciones en el asistente",
    "AML.T0130": "sesgar las respuestas del agente se hace con contenido "
                 "inyectado en lo que lee",
    "AML.T0134": "servir contenido distinto al agente que a la persona es "
                 "inyección indirecta por el contenido recuperado",
    "AML.T0119": "explotar la cadena automática que procesa artefactos es "
                 "cadena de suministro",
}
# prueba de sensibilidad: las decisiones dudosas, cambiadas de sitio
MAPA_ALT = {
    "AML.T0054": "6.3",      # jailbreak como evasión de los filtros
    "AML.T0053": "6.9",      # la acción del agente, como efecto de la inyección
    "AML.T0086": "6.9",
    "AML.T0101": "6.9",
    "AML.T0102": "6.9",
    "AML.T0070": "6.9",      # envenenar el RAG como inyección indirecta
    "AML.T0080": "6.9",
    "AML.T0080.000": "6.9",
    "AML.T0080.001": "6.9",
    "AML.T0043.004": "6.7",  # el disparador, como parte del modelo envenenado
    "AML.T0129": "6.7",
    "AML.T0081": FUERA,      # la configuración del agente, como activo clásico
    "AML.T0018.003": FUERA,
    "AML.T0130": FUERA,
    "AML.T0134": FUERA,
    "AML.T0082": FUERA,
    "AML.T0133": FUERA,
}

# correspondencias con las otras tres referencias; «fuera» es que la
# referencia nombra algo que la norma no recoge en las nueve (va a su anexo B
# o a 27002). Páginas del NIST, las de su índice.
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
    """Descarga el fichero de ATLAS de la versión fijada."""
    req = urllib.request.Request(ATLAS_URL, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        destino.write_bytes(r.read())


def raiz_de(tid: str) -> str | None:
    """Técnica raíz de una subtécnica (AML.T0051.001 → AML.T0051)."""
    return tid.rsplit(".", 1)[0] if re.match(r"AML\.T\d{4}\.\d{3}$", tid) else None


def clausula_de(tid: str, mapa: dict, alt: dict | None = None) -> tuple[str, str]:
    """Cláusula de una técnica y el motivo, con herencia de la raíz."""
    if alt and tid in alt:
        return alt[tid], "prueba de sensibilidad"
    for cl, ids in mapa.items():
        if tid in ids:
            return cl, MOTIVOS.get(tid, "regla por técnica")
    raiz = raiz_de(tid)
    if raiz:
        if alt and raiz in alt:
            return alt[raiz], "prueba de sensibilidad (hereda la raíz)"
        for cl, ids in mapa.items():
            if raiz in ids:
                return cl, "hereda la de su técnica raíz " + raiz
    return FUERA, ("reconocimiento, preparación, acceso, recolección, mando y "
                   "control o impacto genérico")


def repartir(tecnicas: dict, rel: dict, tacticas: dict, alt: dict | None):
    """Una fila por técnica con su cláusula."""
    filas = []
    for tid, t in tecnicas.items():
        cl, motivo = clausula_de(tid, MAPA, alt)
        tac = [x["target"] for x in rel.get(tid, {}).get("achieves", [])]
        if not tac and raiz_de(tid):
            tac = [x["target"] for x in rel.get(raiz_de(tid), {}).get("achieves", [])]
        filas.append({
            "tecnica": tid, "nombre": t["name"],
            "nivel": "subtécnica" if raiz_de(tid) else "raíz",
            "tacticas": "; ".join(tacticas[x]["name"] for x in tac if x in tacticas),
            "madurez": (t.get("maturity") or "").lower(),
            "clausula": cl, "amenaza": nombre(cl), "motivo": motivo,
        })
    return filas


def casos_y_mitigaciones(filas: list, casos: dict, mits: dict, rel: dict):
    """Casos y mitigaciones con las cláusulas que heredan de sus técnicas."""
    cl_de = {f["tecnica"]: f["clausula"] for f in filas}
    fc = []
    for cid, c in casos.items():
        usadas = [x["target"] for x in rel.get(cid, {}).get("employs", [])]
        cls = sorted({cl_de.get(u, FUERA) for u in usadas}, key=orden)
        fc.append({
            "caso": cid, "nombre": c["name"], "fecha": str(c.get("date", ""))[:10],
            "tipo": (c.get("type") or "").lower(), "tecnicas": len(usadas),
            "clausulas": "; ".join(cls),
            "solo_fuera": int(all(x not in CLAUSULAS for x in cls)),
        })
    fm = []
    for mid, mm in mits.items():
        tids = [x["target"] for x in rel.get(mid, {}).get("mitigates", [])]
        cls = sorted({cl_de.get(u, FUERA) for u in tids}, key=orden)
        fm.append({
            "mitigacion": mid, "nombre": mm["name"],
            "categoria": "; ".join(mm.get("categories") or []),
            "tecnicas": len(tids),
            "tecnicas_en_las_nueve": sum(cl_de.get(u, FUERA) in CLAUSULAS for u in tids),
            "clausulas": "; ".join(cls),
        })
    return fc, fm


def resumir(filas: list, casos: list, mits: list) -> list:
    """Una fila por cláusula con técnicas, madurez, casos y mitigaciones."""
    out = []
    for cl in list(CLAUSULAS) + [ANEXO_B, FUERA]:
        de = [f for f in filas if f["clausula"] == cl]
        mad = collections.Counter(f["madurez"] for f in de)
        toca = [c for c in casos if cl in c["clausulas"].split("; ")]
        out.append({
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
            "mitigaciones": sum(cl in m["clausulas"].split("; ") for m in mits),
            "nist": sum(1 for n in NIST if cl in n[3].split("; ")),
            "owasp": sum(1 for o in OWASP if cl in o[2].split("; ")),
            "ai_act": sum(1 for x in AI_ACT if cl in x[2].split("; ")),
        })
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--atlas", type=Path, default=AQUI / f"ATLAS-{ATLAS_VERSION}.yaml")
    a = p.parse_args()
    if not a.atlas.exists():
        descargar(a.atlas)
    d = yaml.safe_load(a.atlas.read_text(encoding="utf-8"))
    assert str(d.get("format-version", "")).startswith("6."), "se espera el formato 6"
    tacticas, tecnicas = d["tactics"], d["techniques"]
    casos, mits, rel = d["case-studies"], d["mitigations"], d["relationships"]

    # 1. reparto principal
    filas = repartir(tecnicas, rel, tacticas, None)
    escribe("atlas_tecnicas_27090.csv", filas)
    fc, fm = casos_y_mitigaciones(filas, casos, mits, rel)
    escribe("atlas_casos_27090.csv", fc)
    escribe("atlas_mitigaciones_27090.csv", fm)
    resumen = resumir(filas, fc, fm)
    escribe("resumen_27090.csv", resumen)

    # 2. prueba de sensibilidad: las decisiones dudosas cambiadas de sitio
    filas_alt = repartir(tecnicas, rel, tacticas, MAPA_ALT)
    fc_alt, fm_alt = casos_y_mitigaciones(filas_alt, casos, mits, rel)
    resumen_alt = resumir(filas_alt, fc_alt, fm_alt)
    for r, r2 in zip(resumen, resumen_alt):
        r2["tecnicas_principal"] = r["tecnicas"]
        r2["casos_principal"] = r["casos"]
    escribe("resumen_27090_sensibilidad.csv", resumen_alt)

    # 3. casos por año y por tipo
    anios = collections.Counter((c["fecha"][:4], c["tipo"]) for c in fc)
    escribe("atlas_casos_anio.csv", [
        {"anio": y, "incidentes": anios.get((y, "incident"), 0),
         "ejercicios": anios.get((y, "exercise"), 0)}
        for y in sorted({k[0] for k in anios})])

    # 4. correspondencias de las otras referencias
    corr = ([{"fuente": "NIST AI 100-2 E2025", "elemento": f"{n[0]} {n[1]}",
              "pagina": n[2], "clausula": n[3]} for n in NIST]
            + [{"fuente": "OWASP Top 10 for LLM Applications 2025",
                "elemento": f"{o[0]} {o[1]}", "pagina": "", "clausula": o[2]}
               for o in OWASP]
            + [{"fuente": "Reglamento (UE) 2024/1689", "elemento": f"{x[0]} {x[1]}",
                "pagina": "", "clausula": x[2]} for x in AI_ACT])
    escribe("correspondencias_27090.csv", corr)

    # 5. volúmenes
    def dentro(res):
        return sum(r["tecnicas"] for r in res if r["clausula"] in CLAUSULAS)

    def anexo(res):
        return sum(r["tecnicas"] for r in res if r["clausula"] == ANEXO_B)

    vol = {
        "atlas_version": ATLAS_VERSION, "atlas_formato": d.get("format-version"),
        "atlas_url": ATLAS_URL,
        "tacticas": len(tacticas), "tecnicas": len(filas),
        "tecnicas_raiz": sum(f["nivel"] == "raíz" for f in filas),
        "subtecnicas": sum(f["nivel"] == "subtécnica" for f in filas),
        "tecnicas_en_las_nueve": dentro(resumen),
        "tecnicas_anexo_b": anexo(resumen),
        "tecnicas_fuera": len(filas) - dentro(resumen) - anexo(resumen),
        "casos": len(fc),
        "incidentes": sum(c["tipo"] == "incident" for c in fc),
        "ejercicios": sum(c["tipo"] == "exercise" for c in fc),
        "casos_en_las_nueve": sum(1 - c["solo_fuera"] for c in fc),
        "casos_solo_fuera": sum(c["solo_fuera"] for c in fc),
        "casos_primero": min(c["fecha"] for c in fc),
        "casos_ultimo": max(c["fecha"] for c in fc),
        "mitigaciones_atlas": len(fm),
        "mitigaciones_que_cubren_alguna_de_las_nueve": sum(
            any(c in CLAUSULAS for c in m["clausulas"].split("; ")) for m in fm),
        "sensibilidad_tecnicas_en_las_nueve": dentro(resumen_alt),
        "sensibilidad_tecnicas_fuera": len(filas) - dentro(resumen_alt) - anexo(resumen_alt),
        "sensibilidad_casos_en_las_nueve": sum(1 - c["solo_fuera"] for c in fc_alt),
        "sensibilidad_tecnicas_cambiadas": sum(
            f["clausula"] != g["clausula"] for f, g in zip(filas, filas_alt)),
        "nist_elementos": len(NIST), "owasp_elementos": len(OWASP),
        "ai_act_elementos": len(AI_ACT),
    }
    (AQUI / "volumenes.json").write_text(
        json.dumps(vol, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(vol, ensure_ascii=False, indent=1))
    for r, r2 in zip(resumen, resumen_alt):
        print(f"{r['clausula']:>7} {r['amenaza'][:34]:<34} técnicas {r['tecnicas']:3d} "
              f"(realized {r['realized']:2d}) · casos {r['casos']:2d} "
              f"(incidentes {r['incidentes']:2d}) · mitig {r['mitigaciones']:2d} "
              f"· sensib.: técnicas {r2['tecnicas']:3d}, casos {r2['casos']:2d}")


def escribe(nombre_fichero: str, filas: list[dict]) -> None:
    """Escribe un CSV junto al guion."""
    with open(AQUI / nombre_fichero, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


if __name__ == "__main__":
    main()
