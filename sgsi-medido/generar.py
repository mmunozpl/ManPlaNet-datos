#!/usr/bin/env python3
"""Mapa de controles entre seis marcos (ISO/IEC 27001:2022, ENS, NIST CSF 2.0
y SP 800-53, NIS2, DORA y PCI DSS v4.0.1) y sus comparativas, construido
desde las fuentes públicas y desde cuatro tablas propias declaradas.

Descarga (o lee de la caché local ``descargas/``):
  - el núcleo del CSF 2.0 con sus referencias informativas, tal como lo
    exporta el CPRT del NIST (xlsx): de ahí salen las correspondencias
    oficiales CSF ↔ SP 800-53 Rev. 5, CSF ↔ ISO/IEC 27001:2022 (anexo A y
    cláusulas) y CSF ↔ PCI DSS v4.0;
  - el texto consolidado del RD 311/2022 (ENS) en el BOE: las 73 medidas del
    anexo II;
  - NIS2 (Directiva 2022/2555) y DORA (Reglamento 2022/2554) en EUR-Lex: el
    artículo 21.2 y los artículos 5 a 16;
  - el Libro II de MAGERIT v3 (catálogo de elementos): las amenazas.

Las tablas propias viven en ``fuentes/`` y son lectura del autor, no
documentos oficiales: el mapa ENS → categorías del CSF, el mapa NIS2 y
DORA → categorías del CSF, los títulos del anexo A de ISO/IEC 27001:2022 y
los doce requisitos de PCI DSS v4.0.1 con su categoría del CSF.

Escribe junto a sí mismo: csf_core.csv, csf_referencias.csv,
ens_medidas.csv, nis2_art21.csv, dora_cap2.csv, magerit_amenazas.csv,
mapa_controles.csv, cobertura_csf.csv, comparativa_pares.csv,
iso_sin_csf.csv, ens_iso_candidatos.csv, exigencias_por_marco.csv e
INSTANTANEA_mapa.md.
"""
import collections
import csv
import html
import itertools
import json
import os
import re
import subprocess
import sys
import urllib.request
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
DESC = os.path.join(AQUI, "descargas")
FUENTES = os.path.join(AQUI, "fuentes")
UA = "ManPlaNet-datos/1.0 (https://manpla.net; mmunozpl@uoc.edu)"
URLS = {
    "csf.xlsx": "https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all",
    "ens.html": "https://www.boe.es/buscar/act.php?id=BOE-A-2022-7191",
    "nis2.html": "https://eur-lex.europa.eu/legal-content/ES/TXT/HTML/?uri=CELEX:32022L2555",
    "dora.html": "https://eur-lex.europa.eu/legal-content/ES/TXT/HTML/?uri=CELEX:32022R2554",
    "magerit_libro2.pdf": "https://administracionelectronica.gob.es/ctt/resources/Soluciones/184/Descargas/Libro-II-Catalogo-de-Elementos.pdf",
}
FUNCIONES = {"GV": "Gobernar", "ID": "Identificar", "PR": "Proteger", "DE": "Detectar", "RS": "Responder", "RC": "Recuperar"}


def descargar(nombre: str) -> str:
    """Devuelve la ruta local del fichero, descargándolo si no está."""
    os.makedirs(DESC, exist_ok=True)
    ruta = os.path.join(DESC, nombre)
    if not os.path.exists(ruta):
        req = urllib.request.Request(URLS[nombre], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r, open(ruta, "wb") as f:
            f.write(r.read())
        print(f"descargado {nombre}")
    return ruta


def texto_html(ruta: str) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", open(ruta, encoding="utf-8", errors="replace").read()))
    return re.sub(r"\s+", " ", t)


def escribir(nombre: str, filas: list[dict], campos: list[str]) -> None:
    with open(os.path.join(AQUI, nombre), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader(); w.writerows(filas)


def leer_fuente(nombre: str) -> list[dict]:
    return list(csv.DictReader(open(os.path.join(FUENTES, nombre), encoding="utf-8")))


# ------------------------------------------------------------------ CSF 2.0
def csf() -> tuple[list[dict], list[dict]]:
    """El núcleo vivo del CSF 2.0 (106 subcategorías) y sus referencias
    informativas, una fila por (subcategoría, fuente, referencia)."""
    z = zipfile.ZipFile(descargar("csf.xlsx"))
    ss = re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8"), flags=re.S)
    strings = [html.unescape(re.sub(r"<[^>]+>", "", s)) for s in ss]
    hoja = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet")]
    filas: dict[int, dict] = {}
    for n in hoja:
        xml = z.read(n).decode("utf-8")
        if "Informative References" not in xml and "Subcategory" not in "".join(strings[:50]):
            pass
        for m in re.finditer(r'<c r="([A-Z]+)(\d+)"([^>]*)>(?:<v>(.*?)</v>|<is><t[^>]*>(.*?)</t></is>)?', xml, flags=re.S):
            col, fila, attrs, v, t = m.groups()
            if v is None and t is None:
                continue
            val = strings[int(v)] if 't="s"' in attrs and v is not None else (html.unescape(t) if t else v)
            filas.setdefault((n, int(fila)), {})[col] = val
    func = cat = None
    core: dict[str, dict] = {}
    refs: set[tuple[str, str, str]] = set()
    for clave in sorted(filas):
        r = filas[clave]
        func = r.get("A", func); cat = r.get("B", cat)
        m = re.match(r"\s*([A-Z]{2}\.[A-Z]{2}-\d{2})\s*:\s*(.*)", r.get("C") or "", flags=re.S)
        if not m:
            continue
        sid, texto = m.group(1), " ".join(m.group(2).split())
        if re.search(r"(?i)withdrawn", texto):
            continue
        core.setdefault(sid, dict(funcion=FUNCIONES[sid[:2]], categoria=sid[:5], categoria_nombre=" ".join((cat or "").split()).split(":")[0],
                                  subcategoria=sid, texto=texto))
        for linea in (r.get("E") or "").split("\n"):
            linea = linea.strip()
            mm = re.match(r"(SP 800-53 Rev 5\.2\.0|SP 800-53 Rev 5\.1\.1|ISO/IEC 27001:2022: (?:Annex A Controls|Mandatory Clause)|PCI DSS|CIS Controls(?: v[\d.]+)?|SP 800-171 Rev 3|CCMv4\.0|CRI Profile v2\.0|SCF|NICE Framework|SDOS|OWASP Top 10 LLM Applications|SP-800-37 Rev 2|CSF v1\.1)\s*:\s*(.+)$", linea)
            if mm and mm.group(2).strip() not in ("None", ""):
                refs.add((sid, mm.group(1).strip(), mm.group(2).strip().rstrip(",")))
    nucleo = sorted(core.values(), key=lambda r: r["subcategoria"])
    referencias = [dict(subcategoria=s, categoria=s[:5], fuente=f, referencia=r) for s, f, r in sorted(refs)]
    escribir("csf_core.csv", nucleo, ["funcion", "categoria", "categoria_nombre", "subcategoria", "texto"])
    escribir("csf_referencias.csv", referencias, ["subcategoria", "categoria", "fuente", "referencia"])
    return nucleo, referencias


# ---------------------------------------------------------------------- ENS
def ens() -> list[dict]:
    t = texto_html(descargar("ens.html"))
    med = re.findall(r"\b(org\.\d|(?:op|mp)\.[a-z]+\.\d+) ([A-ZÁÉÍÓÚ][^\n]{3,90}?) (Categoría|[CIDAT ]{1,9}) (aplica|n\.a\.|\+ ?R\d|\+ ?\[R\d(?: o R\d)*\])", t)
    vistos, filas = set(), []
    for cod, nombre, dim, _ in med:
        if cod in vistos:
            continue
        vistos.add(cod)
        grupo = {"org": "marco organizativo", "op": "marco operacional", "mp": "medidas de protección"}[cod.split(".")[0]]
        filas.append(dict(codigo=cod, medida=nombre.strip(), grupo=grupo, dimension_o_categoria=dim.strip()))
    assert len(filas) == 73, len(filas)
    escribir("ens_medidas.csv", filas, ["codigo", "medida", "grupo", "dimension_o_categoria"])
    return filas


# ---------------------------------------------------------------- NIS2, DORA
def nis2_dora() -> tuple[list[dict], list[dict]]:
    t = texto_html(descargar("nis2.html"))
    i = t.find("Artículo 21 Medidas para la gestión de riesgos")
    seg = t[i:i + 5000]
    j = seg.find("incluirán al menos los siguientes elementos:")
    items = re.findall(r"\b([a-j])\) (.+?)(?=;\s*[a-j]\)|\.\s*3\.|$)", seg[j:])
    n2 = [dict(letra=l, medida=m.strip(" ;.")) for l, m in items]
    assert len(n2) == 10, len(n2)
    escribir("nis2_art21.csv", n2, ["letra", "medida"])
    t = texto_html(descargar("dora.html"))
    arts = []
    for n in range(5, 17):
        i = t.find(f"Artículo {n} ")
        trozo = t[i + len(f"Artículo {n} "):i + 260]
        m = re.match(r"([A-ZÁÉÍÓÚ][^.]{3,180}?)(?= 1\. | Las entidades | Con el fin | A fin | Las Autoridades | Los artículos | Como parte )", trozo)
        arts.append(dict(articulo=n, titulo=(m.group(1) if m else trozo[:120]).strip()))
    escribir("dora_cap2.csv", arts, ["articulo", "titulo"])
    return n2, arts


# ------------------------------------------------------------------ MAGERIT
def magerit() -> list[dict]:
    ruta = descargar("magerit_libro2.pdf")
    try:
        txt = subprocess.run(["pdftotext", "-layout", ruta, "-"], capture_output=True, text=True, check=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("sin pdftotext: se omite el catálogo de amenazas"); return []
    grupos = {"N": "desastres naturales", "I": "de origen industrial", "E": "errores y fallos no intencionados", "A": "ataques intencionados"}
    filas, vistos = [], set()
    for m in re.finditer(r"^\s*\[([NIEA])\.(\d+)\]\s+(.+?)\s*$", txt, flags=re.M):
        cod = f"[{m.group(1)}.{m.group(2)}]"
        if cod in vistos:
            continue
        vistos.add(cod); filas.append(dict(codigo=cod, grupo=grupos[m.group(1)], amenaza=m.group(3).strip()))
    escribir("magerit_amenazas.csv", filas, ["codigo", "grupo", "amenaza"])
    return filas


# ------------------------------------------------------- el mapa y las cuentas
def mapa(nucleo, referencias, medidas_ens, n2, dora_arts):
    cats = sorted({r["categoria"] for r in nucleo})
    nombre_cat = {r["categoria"]: r["categoria_nombre"] for r in nucleo}
    # por marco: conjunto de (categoría CSF, identificador del control del marco)
    por_marco: dict[str, set[tuple[str, str]]] = collections.defaultdict(set)
    for r in referencias:
        if r["fuente"] == "ISO/IEC 27001:2022: Annex A Controls":
            por_marco["ISO/IEC 27001:2022 (anexo A)"].add((r["categoria"], r["referencia"]))
        elif r["fuente"] == "SP 800-53 Rev 5.2.0":
            por_marco["NIST SP 800-53 Rev. 5"].add((r["categoria"], r["referencia"]))
        elif r["fuente"] == "PCI DSS":
            por_marco["PCI DSS v4.0"].add((r["categoria"], r["referencia"].split(".")[0]))
    for r in leer_fuente("mapa_ens_csf.csv"):
        for c in r["csf_categorias"].split(";"):
            por_marco["ENS (RD 311/2022)"].add((c.strip(), r["codigo"]))
    for r in leer_fuente("mapa_nis2_dora_csf.csv"):
        for c in r["csf_categorias"].split(";"):
            por_marco[r["norma"]].add((c.strip(), r["referencia"]))
    # el propio CSF, como cuenta de subcategorías por categoría
    for r in nucleo:
        por_marco["NIST CSF 2.0"].add((r["categoria"], r["subcategoria"]))
    marcos = ["ISO/IEC 27001:2022 (anexo A)", "ENS (RD 311/2022)", "NIST CSF 2.0", "NIST SP 800-53 Rev. 5", "NIS2", "DORA", "PCI DSS v4.0"]
    # cobertura: por categoría, cuántos controles de cada marco
    cob = []
    for c in cats:
        fila = dict(funcion=FUNCIONES[c[:2]], categoria=c, categoria_nombre=nombre_cat[c])
        for m in marcos:
            fila[m] = len({ident for cat, ident in por_marco[m] if cat == c})
        cob.append(fila)
    escribir("cobertura_csf.csv", cob, ["funcion", "categoria", "categoria_nombre"] + marcos)
    # el mapa largo: una fila por (marco, control, categoría)
    largo = sorted({(m, ident, cat) for m in marcos for cat, ident in por_marco[m]})
    escribir("mapa_controles.csv", [dict(marco=m, control=i, categoria_csf=c, funcion=FUNCIONES[c[:2]]) for m, i, c in largo], ["marco", "control", "categoria_csf", "funcion"])
    # comparativa por pares: categorías que cubre cada marco, comunes y propias
    cubre = {m: {cat for cat, _ in por_marco[m]} for m in marcos}
    pares = []
    for a, b in itertools.combinations(marcos, 2):
        comunes = cubre[a] & cubre[b]
        pares.append(dict(marco_a=a, marco_b=b, categorias_a=len(cubre[a]), categorias_b=len(cubre[b]), comunes=len(comunes),
                          solo_a=len(cubre[a] - cubre[b]), solo_b=len(cubre[b] - cubre[a]),
                          jaccard=round(len(comunes) / len(cubre[a] | cubre[b]), 3) if (cubre[a] | cubre[b]) else 0,
                          categorias_solo_a=" ".join(sorted(cubre[a] - cubre[b])), categorias_solo_b=" ".join(sorted(cubre[b] - cubre[a]))))
    escribir("comparativa_pares.csv", pares, ["marco_a", "marco_b", "categorias_a", "categorias_b", "comunes", "solo_a", "solo_b", "jaccard", "categorias_solo_a", "categorias_solo_b"])
    # anexo A sin referencia en el CSF (según el propio NIST)
    anexo = leer_fuente("iso27001_anexoA.csv")
    con_ref = {ident for _, ident in por_marco["ISO/IEC 27001:2022 (anexo A)"]}
    sin = [dict(control=r["control"], tema=r["tema"], titulo_es=r["titulo_es"]) for r in anexo if r["control"] not in con_ref]
    escribir("iso_sin_csf.csv", sin, ["control", "tema", "titulo_es"])
    # candidatos ENS ↔ ISO por categoría compartida (derivado, no oficial)
    iso_por_cat = collections.defaultdict(set)
    for cat, ident in por_marco["ISO/IEC 27001:2022 (anexo A)"]:
        iso_por_cat[cat].add(ident)
    titulo = {r["control"]: r["titulo_es"] for r in anexo}
    nombre_med = {r["codigo"]: r["medida"] for r in medidas_ens}
    cand = []
    for r in leer_fuente("mapa_ens_csf.csv"):
        cs = [c.strip() for c in r["csf_categorias"].split(";")]
        isos = sorted(set().union(*[iso_por_cat[c] for c in cs]), key=lambda x: [int(p) for p in x.split(".")])
        cand.append(dict(codigo=r["codigo"], medida=nombre_med.get(r["codigo"], ""), csf_categorias=" ".join(cs), n_controles_iso=len(isos),
                         controles_iso=" ".join(isos)))
    escribir("ens_iso_candidatos.csv", cand, ["codigo", "medida", "csf_categorias", "n_controles_iso", "controles_iso"])
    # exigencias por marco: categorías del CSF que cubre un solo marco de los seis (sin contar al propio CSF ni a SP 800-53)
    seis = ["ISO/IEC 27001:2022 (anexo A)", "ENS (RD 311/2022)", "NIS2", "DORA", "PCI DSS v4.0"]
    ex = []
    for c in cats:
        quienes = [m for m in seis if c in cubre[m]]
        ex.append(dict(categoria=c, categoria_nombre=nombre_cat[c], marcos_que_la_cubren=len(quienes), marcos=" | ".join(quienes),
                       faltan=" | ".join(m for m in seis if m not in quienes)))
    escribir("exigencias_por_marco.csv", ex, ["categoria", "categoria_nombre", "marcos_que_la_cubren", "marcos", "faltan"])
    # instantánea
    L = ["# Mapa de controles: instantánea", "", f"CSF 2.0: {len(nucleo)} subcategorías en {len(cats)} categorías. Referencias informativas del NIST: "
         f"{len(referencias)} filas; controles distintos de SP 800-53 Rev. 5 {len({i for _, i in por_marco['NIST SP 800-53 Rev. 5']})}, "
         f"del anexo A de ISO/IEC 27001:2022 {len(con_ref)} de {len(anexo)}, requisitos principales de PCI DSS {len({i for _, i in por_marco['PCI DSS v4.0']})} de 12.", "",
         f"ENS: {len(medidas_ens)} medidas, todas con categoría del CSF (lectura propia). NIS2: {len(n2)} medidas del artículo 21.2. DORA: {len(dora_arts)} artículos del capítulo II.", "",
         "Categorías del CSF que cubre cada marco:"]
    L += [f"- {m}: {len(cubre[m])} de {len(cats)}" for m in marcos]
    L += ["", "Anexo A sin referencia en el CSF según el NIST: " + ", ".join(r["control"] for r in sin)]
    L += ["", "Pares con menor solape (Jaccard de categorías):"] + [f"- {p['marco_a']} / {p['marco_b']}: {p['jaccard']}" for p in sorted(pares, key=lambda p: p["jaccard"])[:5]]
    open(os.path.join(AQUI, "INSTANTANEA_mapa.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))


def resumen_sgsi() -> None:
    """Los resúmenes del sistema de gestión (declaración de aplicabilidad por
    tema y estado; amenazas de ISO/IEC 27090 con sus mitigaciones de ATLAS;
    plan director por prioridad) y la INSTANTANEA.md que imprime el cuaderno."""
    def filas(*ruta):
        return list(csv.DictReader(open(os.path.join(*ruta), encoding="utf-8")))
    F = os.path.join(AQUI, "fuentes")
    # SoA por tema del anexo A (5 organizativo, 6 personas, 7 físico, 8 tecnológico) y estado
    soa = filas(F, "soa_laboratorios.csv")
    anexo = {r["control"]: r for r in filas(F, "iso27001_anexoA.csv")}
    temas = {"5": "organizativos", "6": "de personas", "7": "físicos", "8": "tecnológicos"}
    res = []
    for t, nombre in temas.items():
        sub = [r for r in soa if r["control"].split(".")[0] == t]
        res.append(dict(tema=f"{t} {nombre}", controles=len(sub), aplican=sum(1 for r in sub if r["aplica"] == "sí"),
                        implantado=sum(1 for r in sub if r["estado"] == "implantado"), parcial=sum(1 for r in sub if r["estado"] == "parcial"),
                        no_implantado=sum(1 for r in sub if r["estado"] == "no implantado"), no_aplica=sum(1 for r in sub if r["aplica"] == "no")))
    res.append(dict(tema="total", **{k: sum(r[k] for r in res) for k in ("controles", "aplican", "implantado", "parcial", "no_implantado", "no_aplica")}))
    escribir("soa_resumen.csv", res, list(res[0].keys()))
    # SoA con el título de cada control, para la tabla de la entrada
    escribir("soa_controles.csv", [dict(control=r["control"], titulo=anexo.get(r["control"], {}).get("titulo_es", ""), **{k: r[k] for k in ("aplica", "estado", "justificacion", "evidencia", "ens")}) for r in soa],
             ["control", "titulo", "aplica", "estado", "justificacion", "evidencia", "ens"])
    # 27090: cada amenaza con las mitigaciones de ATLAS que la medición de octubre le asoció
    mit = collections.defaultdict(list)
    for r in filas(DATA_ISO27090, "atlas_mitigaciones_27090.csv"):
        for cl in r["clausulas"].split(";"):
            mit[cl.strip()].append(r["mitigacion"])
    det = []
    for r in filas(F, "soa_27090.csv"):
        ms = mit.get(r["clausula"], [])
        det.append(dict(**r, mitigaciones_atlas=len(ms), mitigaciones=" ".join(ms)))
    escribir("soa_27090_detalle.csv", det, list(det[0].keys()))
    # plan director: horas y número de iniciativas por prioridad y trimestre
    plan = filas(F, "plan_director.csv")
    pr = []
    for p in ("alta", "media", "baja"):
        sub = [r for r in plan if r["prioridad"] == p]
        pr.append(dict(prioridad=p, iniciativas=len(sub), horas=sum(int(r["horas_estimadas"]) for r in sub), trimestres=" ".join(sorted({t.strip() for r in sub for t in r["trimestre"].split(";")}))))
    escribir("plan_director_resumen.csv", pr, ["prioridad", "iniciativas", "horas", "trimestres"])
    # instantánea
    rr = {r["laboratorio"]: r for r in filas(AQUI, "riesgos_resumen.csv")}
    ar = {r["sistema"]: r for r in filas(AQUI, "auditoria_resumen.csv")}
    am = filas(AQUI, "auditoria_marcos.csv")
    k = filas(AQUI, "kpis.csv"); ok = filas(AQUI, "okr_resumen.csv")
    sim = filas(AQUI, "simulacro.csv"); rto = {r["laboratorio"]: r["segundos_acumulados"] for r in sim if r["fase"] == "tiempo real de recuperación"}
    cob = filas(AQUI, "cobertura_csf.csv"); pares = filas(AQUI, "comparativa_pares.csv")
    tot = res[-1]; s90 = det
    L = ["# Un SGSI medido: instantánea", "",
         "Alcance: tres sistemas publicados con su código y sus mediciones (pam-minimo, datamart-wikipedia y rag-sintetico, este último el sistema de IA). "
         "Ninguno trata datos personales. Política en fuentes/politica.md.", "",
         "## Mapa de marcos", "",
         "Categorías de NIST CSF 2.0 (22) que cubre cada marco: " + "; ".join(
             f"{m} {sum(1 for r in cob if int(r[m]) > 0)}" for m in cob[0].keys() if m not in ("funcion", "categoria", "categoria_nombre")) + ".",
         "Pares con menor solape (Jaccard): " + "; ".join(f"{p['marco_a']} / {p['marco_b']} {p['jaccard']}" for p in sorted(pares, key=lambda p: float(p["jaccard"]))[:3]) + ".", "",
         "## Riesgos (MAGERIT v3 simplificado, apetito 12 sobre 50)", ""]
    L += [f"- {lab}: {r['riesgos']} riesgos; promedio {r['riesgo_promedio']} → residual {r['residual_promedio']} ({r['reduccion_pct']} % menos); {r['sobre_apetito']} sobre el apetito" for lab, r in rr.items()]
    L += ["", "## Declaración de aplicabilidad (anexo A de ISO/IEC 27001:2022)", "",
          f"{tot['controles']} controles: {tot['aplican']} aplican ({tot['implantado']} implantados, {tot['parcial']} parciales, {tot['no_implantado']} sin implantar) y {tot['no_aplica']} no aplican."]
    L += ["", "## Sistema de IA (ISO/IEC 27090:2026)", "",
          f"{len(s90)} elementos declarados (las nueve amenazas de la cláusula 6 y el anexo B): {sum(1 for r in s90 if r['aplica'] == 'sí')} aplican ({sum(1 for r in s90 if r['estado'] == 'implantado')} implantadas, {sum(1 for r in s90 if r['estado'] == 'parcial')} parciales); "
          f"mitigaciones de ATLAS asociadas a las aplicables: {sum(r['mitigaciones_atlas'] for r in s90 if r['aplica'] == 'sí')}."]
    L += ["", "## Auditoría interna", ""]
    L += [f"- {s}: {r['comprobaciones']} comprobaciones; {r['conforme']} conformes, {r['no_conforme']} no conformes, {r['observación']} observaciones; conformidad {r['conformidad_pct']} %" for s, r in ar.items()]
    L += ["- por marco: " + "; ".join(f"{m['marco']} {m['comprobaciones']} comprobaciones y {m['referencias_distintas']} referencias" for m in am)]
    L += ["", "## Indicadores (OKR)", ""]
    L += [f"- {r['objetivo']} {r['objetivo_texto']}: {r['cumplen']} cumplen, {r['no_cumplen']} no cumplen, {r['sin_meta']} sin meta" for r in ok]
    L += ["", "## Simulacro de continuidad (tiempo real de recuperación, segundos)", ""]
    L += [f"- {lab}: {s} s" for lab, s in rto.items()]
    L += ["", "## Plan director", ""]
    L += [f"- {r['prioridad']}: {r['iniciativas']} iniciativas, {r['horas']} horas ({r['trimestres']})" for r in pr]
    L += ["", f"Serie ISO/IEC 27000 y normas hermanas identificadas: {len(filas(F, 'serie_27000.csv'))}, con su edición vigente en fuentes/serie_27000.csv."]
    open(os.path.join(AQUI, "INSTANTANEA.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


DATA_ISO27090 = os.path.join(os.path.dirname(AQUI), "iso-27090")

if __name__ == "__main__":
    nucleo, referencias = csf()
    medidas = ens()
    n2, arts = nis2_dora()
    magerit()
    mapa(nucleo, referencias, medidas, n2, arts)
    # el sistema de gestión sobre el mapa: riesgos, auditoría interna,
    # indicadores y los resúmenes que lee la entrada
    import riesgo
    import auditoria
    import kpis
    riesgo.principal()
    auditoria.principal()
    kpis.principal()
    resumen_sgsi()
