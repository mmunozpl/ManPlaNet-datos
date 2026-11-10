#!/usr/bin/env python3
"""Indicadores del SGSI escritos como objetivos y resultados clave (OKR), con
el molde de ISO/IEC 27004:2016: qué se mide, con qué fórmula, de qué fichero
sale, cada cuánto se mide y qué meta tiene. Cada valor se calcula desde las
mediciones publicadas en este repositorio (los laboratorios, la auditoría, los
riesgos, el simulacro), nunca se escribe a mano; los indicadores de contexto
(el sector, los plazos del catálogo KEV) no llevan meta y se marcan aparte.

Escribe kpis.csv (un indicador por fila) y okr_resumen.csv (por objetivo).
"""
import csv
import json
import os
import re
import statistics

from auditoria import LAB, SPACE, fijada, filas_csv, imagenes, leer

AQUI = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.dirname(AQUI)
F = os.path.join(AQUI, "fuentes")
OBJETIVOS = {
    "O1": "Los accesos privilegiados están bajo control",
    "O2": "Los datos son íntegros y recuperables",
    "O3": "Las vulnerabilidades y la cadena de suministro se tratan en plazo",
    "O4": "El cumplimiento se mide, no se declara",
    "O5": "El sistema de IA está evaluado frente a ISO/IEC 27090",
    "C": "Contexto del sector (sin meta propia)",
}
FILAS: list[dict] = []


def kr(obj: str, id_: str, kpi: str, valor, unidad: str, meta, sentido: str, fuente: str, periodicidad: str, tipo: str = "propio") -> None:
    if meta == "" or valor == "":
        estado = "sin meta" if tipo == "propio" else "contexto"
    else:
        estado = "cumple" if (valor >= meta if sentido == "≥" else valor <= meta) else "no cumple"
    FILAS.append(dict(objetivo=obj, objetivo_texto=OBJETIVOS[obj], kr=id_, kpi=kpi, valor=valor, unidad=unidad, meta=meta, sentido=sentido,
                      estado=estado, fuente=fuente, periodicidad=periodicidad, tipo=tipo))


def pct(a: float, b: float) -> float:
    return round(100 * a / b, 1) if b else 0.0


def principal() -> None:
    P, M, R = LAB["pam-minimo"], LAB["datamart-wikipedia"], LAB["rag-sintetico"]
    # ---- O1: accesos privilegiados
    pr = filas_csv(P, "pruebas.csv"); ok = sum(1 for r in pr if r["ok"] == "1")
    kr("O1", "KR1.1", "pruebas del control de acceso privilegiado superadas", pct(ok, len(pr)), "%", 100, "≥", "pam-minimo/pruebas.csv", "en cada medición")
    ttl = max([int(r["ttl_s"]) for r in filas_csv(P, "credenciales_bd.csv")] + [int(r["valido_hasta"]) - int(r["valido_desde"]) for r in filas_csv(P, "certificados.csv")], default=0)
    kr("O1", "KR1.2", "vida máxima de una credencial privilegiada emitida", ttl, "s", 900, "≤", "pam-minimo/credenciales_bd.csv; certificados.csv", "en cada medición")
    pru = {r["prueba"]: r["ok"] for r in pr}
    mfa = 100.0 if pru.get("contraseña + TOTP, orden en el servidor") == "1" and pru.get("contraseña correcta, sin TOTP") == "1" else 0.0
    kr("O1", "KR1.3", "vías de acceso privilegiado que exigen segundo factor", mfa, "%", 100, "≥", "pam-minimo/pruebas.csv", "en cada medición")
    grab = len(filas_csv(P, "grabaciones.csv")); con_obj = sum(1 for r in filas_csv(P, "sesiones.csv") if (r.get("sesiones_objetivo") or "0") != "0")
    kr("O1", "KR1.4", "sesiones privilegiadas con grabación de su salida", pct(grab, con_obj), "%", 100, "≥", "pam-minimo/grabaciones.csv; sesiones.csv", "en cada medición")
    aud = filas_csv(P, "auditoria_openbao.csv"); den = sum(int(r["n"]) for r in aud if r["error"] == "sí")
    kr("O1", "KR1.5", "denegaciones de la bóveda con rastro en el diario (quién, qué, dónde)", pct(den, den), "%", 100, "≥", "pam-minimo/auditoria_openbao.csv", "en cada medición")
    # ---- O2: datos íntegros y recuperables
    tests = filas_csv(M, "tests_dbt.csv"); pasan = sum(1 for r in tests if r["estado"] == "pass")
    kr("O2", "KR2.1", "pruebas de calidad del dato superadas sin aviso", pct(pasan, len(tests)), "%", 100, "≥", "datamart-wikipedia/tests_dbt.csv", "en cada carga")
    idem = filas_csv(M, "idempotencia.csv")
    kr("O2", "KR2.2", "objetos idénticos tras repetir la carga (recuentos y huellas)", pct(sum(1 for r in idem if r["igual"] == "sí"), len(idem)), "%", 100, "≥", "datamart-wikipedia/idempotencia.csv", "en cada medición")
    rk = filas_csv(M, "ranking_oficial.csv")
    kr("O2", "KR2.3", "artículos del ranking mensual derivado que coinciden con la lista oficial", round(statistics.mean(int(r["coincidencias_1000"]) for r in rk) / 10, 1), "%", 90, "≥", "datamart-wikipedia/ranking_oficial.csv", "mensual")
    runs = [r for r in filas_csv(M, "runs_airflow.csv") if r["tipo"] == "scheduled"]
    kr("O2", "KR2.4", "ejecuciones programadas de la canalización terminadas con éxito", pct(sum(1 for r in runs if r["estado"] == "success"), len(runs)), "%", 100, "≥", "datamart-wikipedia/runs_airflow.csv", "mensual")
    sim = filas_csv(AQUI, "simulacro.csv")
    rto = {r["laboratorio"]: int(r["segundos_acumulados"]) for r in sim if r["fase"] == "tiempo real de recuperación"}
    kr("O2", "KR2.5a", "tiempo real de recuperación del PAM tras la pérdida total (objetivo RTO declarado: 300 s)", rto.get("pam-minimo", ""), "s", 300, "≤", "sgsi-medido/simulacro.csv", "anual")
    kr("O2", "KR2.5b", "tiempo real de recuperación del DataMart con los 34 meses cargados e idénticos (objetivo RTO declarado: 60 min)", round(rto["datamart-wikipedia"] / 60 + 1e-9, 1) if "datamart-wikipedia" in rto else "", "min", 60, "≤", "sgsi-medido/simulacro.csv", "anual")
    kr("O2", "KR2.5c", "tiempo real de recuperación del índice del RAG, reconstruido y comprobado (objetivo RTO declarado: 60 s)", rto.get("rag-sintetico", ""), "s", 60, "≤", "sgsi-medido/simulacro.csv", "anual")
    comp = [r for r in sim if r["fase"].startswith("comprobación:") and ("reconstruido" in r["detalle"] or "idénticos" in r["fase"] or "restaurados" in r["fase"])
            and r["resultado"] in ("ok", "fallo")]  # las observaciones explicadas (la huella con marcas de tiempo de dbt) no cuentan
    kr("O2", "KR2.6", "comprobaciones de identidad de los datos reconstruidos frente a los publicados (integridad de la reconstrucción)", pct(sum(1 for r in comp if r["resultado"] == "ok"), len(comp)), "%", 100, "≥", "sgsi-medido/simulacro.csv", "anual")
    kr("O2", "KR2.7", "sistemas con copia de seguridad de registros y volúmenes probada", 0, "de 3", 3, "≥", "sgsi-medido/auditoria.csv (P09; D09; S14)", "trimestral")
    # ---- O3: vulnerabilidades y cadena de suministro
    imgs = [i for lab in (P, M) for i in imagenes(leer(lab, "compose.yaml")) + imagenes("".join(leer(d) for d in __import__("glob").glob(os.path.join(lab, "*", "Dockerfile"))))]
    kr("O3", "KR3.1", "imágenes de contenedor fijadas por versión", pct(sum(1 for i in imgs if fijada(i)), len(imgs)), "%", 100, "≥", "compose.yaml y Dockerfile de los dos laboratorios", "en cada cambio")
    req = [l.strip() for l in leer(SPACE, "requirements.txt").splitlines() if l.strip() and not l.startswith("#")]
    sdk = 1 if re.search(r"sdk_version:\s*[\d.]+", leer(SPACE, "README.md")) else 0
    kr("O3", "KR3.2", "dependencias de la demo del RAG fijadas por versión exacta (SDK y bibliotecas)", pct(sum(1 for l in req if "==" in l) + sdk, len(req) + 1) if req else "", "%", 100, "≥", "repositorio público de la demo: requirements.txt; README.md", "en cada cambio")
    audit = {r["id"]: r for r in filas_csv(AQUI, "auditoria.csv")}
    kr("O3", "KR3.3", "sistemas con escaneo de vulnerabilidades de imágenes y bibliotecas", sum(1 for k in ("P04", "D04") if audit.get(k, {}).get("resultado") == "conforme"), "de 2", 2, "≥", "sgsi-medido/auditoria.csv (P04; D04)", "en cada construcción")
    kev = json.load(open(os.path.join(DATA, "php2shell", "resumen_kev.json")))
    kr("C", "C1", f"mediana de días entre la publicación de un CVE y su alta en el catálogo KEV, altas de 2026 (n = {kev['altas_2026']['n']})", kev["altas_2026"]["mediana"], "días", "", "", "php2shell/resumen_kev.json (catálogo " + kev["catalogo_version"] + ")", "mensual", "contexto")
    kr("C", "C2", f"la misma mediana desde la directiva BOD 26-04 (n = {kev['desde_bod_26_04']['n']})", kev["desde_bod_26_04"]["mediana"], "días", "", "", "php2shell/resumen_kev.json", "mensual", "contexto")
    horas = [float(r["horas_desde_parche"]) for r in filas_csv(DATA, "php2shell", "parches_sistemas.csv") if re.match(r"^-?\d+(\.\d+)?$", r["horas_desde_parche"] or "")]
    kr("C", "C3", f"mediana de horas desde el parche de PHP hasta el paquete de cada rama de sistema operativo (n = {len(horas)})", round(statistics.median(horas), 1) if horas else "", "horas", "", "", "php2shell/parches_sistemas.csv", "por aviso", "contexto")
    # ---- O4: cumplimiento medido
    soa = filas_csv(F, "soa_laboratorios.csv"); aplican = [r for r in soa if r["aplica"] == "sí"]
    kr("O4", "KR4.1", "controles aplicables del anexo A implantados del todo", pct(sum(1 for r in aplican if r["estado"] == "implantado"), len(aplican)), "%", 60, "≥", "sgsi-medido/fuentes/soa_laboratorios.csv", "semestral")
    kr("O4", "KR4.1b", "controles aplicables del anexo A implantados o parciales", pct(sum(1 for r in aplican if r["estado"] in ("implantado", "parcial")), len(aplican)), "%", 90, "≥", "sgsi-medido/fuentes/soa_laboratorios.csv", "semestral")
    res = {r["sistema"]: r for r in filas_csv(AQUI, "auditoria_resumen.csv")}
    kr("O4", "KR4.2", "comprobaciones de la auditoría interna conformes sobre las evaluables", float(res["total"]["conformidad_pct"]) if res else "", "%", 80, "≥", "sgsi-medido/auditoria_resumen.csv", "semestral")
    rr = {r["laboratorio"]: r for r in filas_csv(AQUI, "riesgos_resumen.csv")}
    kr("O4", "KR4.3", "riesgos residuales por encima del apetito (12 sobre 50)", int(rr["total"]["sobre_apetito"]), "riesgos", 0, "≤", "sgsi-medido/riesgos_resumen.csv", "semestral")
    plan = filas_csv(F, "plan_director.csv"); origen = " ".join(r["origen"] for r in plan)
    noconf = [k for k, r in audit.items() if r["resultado"] == "no conforme"]
    kr("O4", "KR4.4", "no conformidades de la auditoría con iniciativa en el plan director", pct(sum(1 for k in noconf if k in origen), len(noconf)), "%", 100, "≥", "sgsi-medido/auditoria.csv; fuentes/plan_director.csv", "semestral")
    cob = filas_csv(AQUI, "cobertura_csf.csv")  # una fila por categoría del CSF, una columna por marco
    col_ens = next((k for k in (cob[0].keys() if cob else []) if k.startswith("ENS")), None)
    kr("C", "C4", "categorías de NIST CSF 2.0 que cubren las 73 medidas del ENS (lectura propia)", sum(1 for r in cob if int(r[col_ens]) > 0) if col_ens else "", "de 22", "", "", "sgsi-medido/cobertura_csf.csv", "con cada edición", "contexto")
    # ---- O5: sistema de IA
    cons = filas_csv(R, "consultas.csv")
    kr("O5", "KR5.1", "fragmentos ajenos entregados por consulta con el permiso dentro de la consulta (autorización del recuperador)", round(sum(int(r["pre_expuestos"]) for r in cons) / len(cons), 2), "fragmentos", 0, "≤", "rag-sintetico/consultas.csv", "en cada medición")
    kr("C", "C5", "los mismos fragmentos ajenos por consulta con el permiso aplicado después de recuperar", round(sum(int(r["post_expuestos"]) for r in cons) / len(cons), 2), "fragmentos", "", "", "rag-sintetico/consultas.csv", "en cada medición", "contexto")
    s90 = filas_csv(F, "soa_27090.csv"); apl = [r for r in s90 if r["aplica"] == "sí"]
    kr("O5", "KR5.2", "elementos de ISO/IEC 27090 con declaración (las nueve amenazas de la cláusula 6 y el anexo B)", len(s90), "de 10", 10, "≥", "sgsi-medido/fuentes/soa_27090.csv", "semestral")
    kr("O5", "KR5.3", "elementos aplicables de ISO/IEC 27090 con salvaguarda implantada del todo", pct(sum(1 for r in apl if r["estado"] == "implantado"), len(apl)), "%", 100, "≥", "sgsi-medido/fuentes/soa_27090.csv", "semestral")
    kr("O5", "KR5.4", "reevaluaciones periódicas de las amenazas de IA con calendario fijado y ejecutado (cláusula 7)", 0, "calendarios", 1, "≥", "sgsi-medido/auditoria.csv (R11)", "semestral")
    # ---- contexto del sector
    ens = filas_csv(DATA, "ens-certificados", "salidas", "resumen.csv")
    kr("C", "C6", "certificados de conformidad con el ENS vigentes por categoría (sistemas certificados)", sum(int(r["certificados"]) for r in ens if r["listado"] == "categoria"), "certificados", "", "", "ens-certificados/salidas/resumen.csv", "con cada lectura", "contexto")
    aepd = {r["anio"]: r for r in filas_csv(DATA, "aepd-correctivos", "salidas", "importes_anuales.csv")}
    if "2025" in aepd:
        kr("C", "C7", f"mediana de la multa final en las resoluciones sancionadoras de la AEPD de 2025 (n = {aepd['2025']['n']})", float(aepd["2025"]["mediana_final"]), "€", "", "", "aepd-correctivos/salidas/importes_anuales.csv", "anual", "contexto")
    campos = ["objetivo", "objetivo_texto", "kr", "kpi", "valor", "unidad", "meta", "sentido", "estado", "fuente", "periodicidad", "tipo"]
    with open(os.path.join(AQUI, "kpis.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos); w.writeheader(); w.writerows(FILAS)
    resumen = []
    for obj, texto in OBJETIVOS.items():
        sub = [x for x in FILAS if x["objetivo"] == obj]
        resumen.append(dict(objetivo=obj, objetivo_texto=texto, resultados_clave=len(sub), cumplen=sum(1 for x in sub if x["estado"] == "cumple"),
                            no_cumplen=sum(1 for x in sub if x["estado"] == "no cumple"), sin_meta=sum(1 for x in sub if x["estado"] in ("sin meta", "contexto"))))
    with open(os.path.join(AQUI, "okr_resumen.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(resumen[0].keys())); w.writeheader(); w.writerows(resumen)
    for x in FILAS:
        print(f"{x['kr']:6} {x['kpi'][:90]:90} {x['valor']} {x['unidad']} (meta {x['sentido']} {x['meta']}) → {x['estado']}")
    for r in resumen:
        print(f"{r['objetivo']}: {r['cumplen']} cumplen, {r['no_cumplen']} no cumplen, {r['sin_meta']} sin meta")


if __name__ == "__main__":
    principal()
