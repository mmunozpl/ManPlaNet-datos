#!/usr/bin/env python3
"""Lectura agregada del conjunto de resultados de la órbita de gauge.

El dato crudo lo publica su autor en Hugging Face con DOI —177 000 medidas
del barrido principal y 642 000 del de condicionamiento controlado—, así que
aquí no se redistribuye: se descargan las tablas de lectura, se agregan las
cifras que sostienen las figuras del artículo y se escribe la ficha de
procedencia al lado.

Se guarda en csv y json, junto a este guion.
"""
import csv
import datetime
import io
import json
import urllib.request
from pathlib import Path

BASE = ("https://huggingface.co/datasets/ManPla/"
        "gauge-orbit-quantization-results/resolve/main/artifacts")
DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo
MODELOS = ("pythia", "vitb")
ESCALAS = (32.0, 8.0, 2.0)                  # de gauge suave a gauge fuerte


def leer(ruta: str) -> list[dict]:
    """una tabla del conjunto publicado, como lista de diccionarios."""
    req = urllib.request.Request(f"{BASE}/{ruta}",
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        texto = r.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(texto)))


def num(x: str) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def cuantil(valores: list[float], q: float) -> float:
    """cuantil por interpolación lineal, sin dependencias."""
    v = sorted(valores)
    if not v:
        return float("nan")
    i = (len(v) - 1) * q
    b, t = int(i), min(int(i) + 1, len(v) - 1)
    return v[b] + (v[t] - v[b]) * (i - b)


def llanura() -> list[dict]:
    """rango del error dentro del subgrupo ortogonal, celda a celda.

    `ratio_q1` es el cociente entre el peor error ortogonal muestreado y el
    de la identidad en esa celda (capa, cabeza, anchura); `ratio_q2`, el de
    la identidad contra el mejor punto muestreado. El listón preregistrado
    llama «estrecha» a la celda que queda bajo ×1,25.
    """
    filas = []
    for m in MODELOS:
        for q in (1, 2):
            datos = leer(f"tables/lectura_fria_{m}_q{q}.csv")
            for bits in (4, 8):
                r = [num(d[f"ratio_q{q}"]) for d in datos
                     if int(d["bits"]) == bits]
                r = [x for x in r if x is not None]
                filas.append({
                    "modelo": m, "pregunta": f"q{q}", "bits": bits,
                    "celdas": len(r), "p05": round(cuantil(r, .05), 4),
                    "p50": round(cuantil(r, .50), 4),
                    "p95": round(cuantil(r, .95), 4),
                    "min": round(min(r), 4), "max": round(max(r), 4),
                    "estrechas": sum(1 for x in r if x < 1.25),
                })
    return filas


def por_cabeza() -> list[dict]:
    """qué compra la rotación por cabeza frente a la compartida por capa.

    `mejora_relativa` es la ganancia de la libertad por cabeza sobre la
    mejor rotación compartida de la capa; `mejora_implementacion_vieja`
    conserva la lectura anterior a la corrección, para que se audite.
    """
    filas = []
    for m in MODELOS:
        datos = leer(f"tables/lectura_fria_{m}_q3.csv")
        for bits in (4, 8):
            r = [num(d["mejora_relativa"]) for d in datos
                 if int(d["bits"]) == bits]
            v = [num(d["mejora_implementacion_vieja"]) for d in datos
                 if int(d["bits"]) == bits]
            filas.append({
                "modelo": m, "bits": bits, "celdas": len(r),
                "mejora_p10": round(cuantil(r, .10) * 100, 3),
                "mejora_p50": round(cuantil(r, .50) * 100, 3),
                "mejora_p90": round(cuantil(r, .90) * 100, 3),
                "mejora_vieja_p50": round(cuantil(v, .50) * 100, 3),
            })
    return filas


def cola() -> list[dict]:
    """percentiles del error en la familia GL, por fuerza del gauge."""
    filas = []
    for m in MODELOS:
        for d in leer(f"tables/lectura_fria_{m}_gl.csv"):
            filas.append({
                "modelo": m, "escala": num(d["escala"]),
                "bits": int(d["bits"]),
                "mediana": round(num(d["median"]), 4),
                "media": round(num(d["mean"]), 4),
                "maximo": round(num(d["max"]), 2),
            })
    return sorted(filas, key=lambda r: (r["modelo"], -r["escala"], r["bits"]))


def producto() -> tuple[list[dict], dict]:
    """la variable de la cota, celda a celda, desde el barrido de familias.

    p es el cociente entre el producto de las normas de los factores
    transformados y el mismo producto en la identidad; e/e0, el cociente de
    errores del circuito. La cota predice exponente uno entre ambos.
    """
    filas = leer("logs/quant_kappa/quant_familia.csv")
    base: dict[tuple, dict] = {}
    for d in filas:
        if d["regimen"] != "identidad":
            continue
        base[(d["modelo"], d["capa"], d["cabeza"], d["bits"])] = {
            "e": num(d["err_circuito"]), "nv": num(d["norma_wv"]),
            "no": num(d["norma_wo"])}
    puntos = []
    for d in filas:
        if d["regimen"] == "identidad":
            continue
        b = base.get((d["modelo"], d["capa"], d["cabeza"], d["bits"]))
        e = num(d["err_circuito"])
        nv, no = num(d["norma_wv"]), num(d["norma_wo"])
        if not b or not e or not b["e"]:
            continue
        p = (nv * no) / (b["nv"] * b["no"])
        puntos.append({"modelo": d["modelo"], "bits": int(d["bits"]),
                       "regimen": d["regimen"], "kappa": num(d["kappa"]),
                       "p": p, "ratio": e / b["e"]})
    # la nube se resume en deciles de p: una fila por bin, no 100 000 puntos
    binned = []
    for bits in (4, 8):
        sub = [x for x in puntos if x["bits"] == bits]
        ps = sorted(x["p"] for x in sub)
        cortes = [cuantil(ps, i / 12) for i in range(13)]
        for i in range(12):
            lo, hi = cortes[i], cortes[i + 1]
            grupo = [x for x in sub if lo <= x["p"] <= hi]
            if len(grupo) < 30:
                continue
            binned.append({
                "bits": bits, "p_inf": round(lo, 5), "p_sup": round(hi, 5),
                "p_mediano": round(
                    cuantil([x["p"] for x in grupo], .5), 5),
                "ratio_mediano": round(
                    cuantil([x["ratio"] for x in grupo], .5), 5),
                "kappa_mediano": round(
                    cuantil([x["kappa"] for x in grupo], .5), 3),
                "medidas": len(grupo)})
    resumen = {"medidas_usadas": len(puntos),
               "p_minimo": round(min(x["p"] for x in puntos), 4),
               "p_maximo": round(max(x["p"] for x in puntos), 2)}
    return binned, resumen


def contraste() -> list[dict]:
    """la validación extremo a extremo, tal como la publica su tabla."""
    filas = []
    for d in leer("tables/contraste_e2e.csv"):
        filas.append({
            "condicion_a": d["condicion_a"], "condicion_b": d["condicion_b"],
            "top1_a": round(num(d["top1_a"]) * 100, 2),
            "top1_b": round(num(d["top1_b"]) * 100, 2),
            "dif_pp": round(num(d["dif_pp"]), 2),
            "discordantes_a": int(d["discordantes_a"]),
            "discordantes_b": int(d["discordantes_b"]),
            "mcnemar_p": round(num(d["mcnemar_p"]), 4),
            "acuerdo_argmax": round(num(d["acuerdo_argmax"]), 4),
            "indistinguibles": d["indistinguibles"] == "True"})
    return filas


def escribir_csv(nombre: str, filas: list[dict]) -> None:
    with (DESTINO / nombre).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def main() -> None:
    lla, gl, ctr, pc = llanura(), cola(), contraste(), por_cabeza()
    bins, prod = producto()
    colapso = leer("tables/colapso_producto.csv")
    bal = leer("tables/punto_balanceado.csv")
    escribir_csv("orbita-ortogonal.csv", lla)
    escribir_csv("cola-gl.csv", gl)
    escribir_csv("cota-producto.csv", bins)
    escribir_csv("contraste-e2e.csv", ctr)
    escribir_csv("por-cabeza.csv", pc)

    e2e = {f'{r["condicion_a"]}|{r["condicion_b"]}': r for r in ctr}
    resumen = {
        "fuente": "ManPla/gauge-orbit-quantization-results (Hugging Face)",
        "deposito": "10.5281/zenodo.22904208",
        "extraido": datetime.date.today().isoformat(),
        "imagenes_validacion": 5000,
        "llanura": {
            f'{r["modelo"]}_{r["pregunta"]}_{r["bits"]}': {
                "celdas": r["celdas"], "estrechas": r["estrechas"],
                "p50": r["p50"], "min": r["min"], "max": r["max"]}
            for r in lla if r["bits"] == 4},
        "cola_int4": {
            f'{r["modelo"]}_escala{r["escala"]:g}': {
                "mediana": r["mediana"], "maximo": r["maximo"]}
            for r in gl if r["bits"] == 4},
        "cota": {
            "exponente_producto": round(num(
                [c for c in colapso
                 if c["variable"] == "producto" and c["bits"] == "4"][0]
                ["exponente"]), 4),
            "r2_producto": round(num(
                [c for c in colapso
                 if c["variable"] == "producto" and c["bits"] == "4"][0]
                ["r2"]), 4),
            "exponente_kappa": round(num(
                [c for c in colapso
                 if c["variable"] == "kappa" and c["bits"] == "4"][0]
                ["exponente"]), 4),
            "r2_kappa": round(num(
                [c for c in colapso
                 if c["variable"] == "kappa" and c["bits"] == "4"][0]
                ["r2"]), 4),
            **prod},
        "por_cabeza_int4": {
            r["modelo"]: {"mediana_pct": r["mejora_p50"],
                          "p10_pct": r["mejora_p10"],
                          "p90_pct": r["mejora_p90"],
                          "con_la_implementacion_anterior_pct":
                              r["mejora_vieja_p50"]}
            for r in pc if r["bits"] == 4},
        "punto_balanceado": {
            r["modelo"]: {"p_mediano": round(num(r["p_bal_mediano"]), 4),
                          "ratio_medido": round(
                              num(r["ratio_medido_mediano"]), 4),
                          "veredicto": r["l1_veredicto"]}
            for r in bal if r["bits"] == "4"},
        "e2e": {
            "identidad_int4_top1": e2e["identidad|gl_escala2"]["top1_a"],
            "gl_escala2_int4_top1": e2e["identidad|gl_escala2"]["top1_b"],
            "caida_pp": e2e["identidad|gl_escala2"]["dif_pp"],
            "acuerdo_int4": e2e["identidad|gl_escala2"]["acuerdo_argmax"],
            "acuerdo_fp32":
                e2e["identidad_fp32|gl_escala2_fp32"]["acuerdo_argmax"],
            "discordantes_fp32":
                e2e["identidad_fp32|gl_escala2_fp32"]["discordantes_a"],
            "coste_de_cuantizar_pp":
                e2e["identidad_fp32|identidad"]["dif_pp"],
            "rango_ortogonal_pp":
                e2e["mejor_orto_muestreado|peor_orto_muestreado"]["dif_pp"],
            "mcnemar_ortogonal":
                e2e["mejor_orto_muestreado|peor_orto_muestreado"]["mcnemar_p"],
        },
    }
    resumen["e2e"]["imagenes_de_acuerdo_int4"] = round(
        resumen["e2e"]["acuerdo_int4"] * resumen["imagenes_validacion"])
    (DESTINO / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    ficha = f"""# Instantánea de la órbita de gauge bajo cuantización

Agregados, no el dato crudo: las tablas de este directorio resumen el
conjunto de resultados que acompaña al depósito
[10.5281/zenodo.22904208](https://doi.org/10.5281/zenodo.22904208), publicado
por su autor en Hugging Face. El barrido completo —170 016 medidas del
principal y 642 048 del de condicionamiento controlado— se consulta en la
fuente; aquí van los percentiles, los bins y la tabla de contraste que
sostienen las figuras del artículo.

- Fuente: {BASE}
- Depósito: 10.5281/zenodo.22904208 (v1.0, 22-09-2026, Apache-2.0)
- Extraído: {resumen['extraido']}
- Medidas usadas para la cota: {prod['medidas_usadas']}
- Imágenes de la validación extremo a extremo: 5 000

## Ficheros

| Fichero | Qué contiene |
|---|---|
| `orbita-ortogonal.csv` | por modelo, pregunta y anchura: celdas, percentiles y mínimo/máximo del cociente entre el peor error ortogonal muestreado y el de la identidad, y cuántas celdas quedan bajo el listón de ×1,25 |
| `cola-gl.csv` | mediana, media y máximo del error del circuito en la familia GL, por fuerza del gauge (escala 32, 8 y 2) y anchura |
| `cota-producto.csv` | doce bins del factor p de la cota: p mediano, cociente de errores mediano, κ mediano y medidas por bin |
| `por-cabeza.csv` | mejora relativa de la rotación por cabeza sobre la compartida por capa, en percentiles, con la columna que conserva la implementación anterior a su corrección |
| `contraste-e2e.csv` | las siete comparaciones pareadas de la validación extremo a extremo, con top-1, diferencia, discordancias, McNemar y acuerdo de clase predicha |
| `resumen.json` | las cifras que el artículo cita en prosa |

`p` se recalcula aquí desde las normas que publica el barrido:
p = ‖W_O R⁻ᵀ‖·‖Rᵀ W_v‖ / (‖W_O‖·‖W_v‖), normalizado por la identidad de la
misma celda. El cociente de errores es e(R)/e(I) en esa misma celda.
"""
    (DESTINO / "INSTANTANEA.md").write_text(ficha, encoding="utf-8")
    print(f"[gauge] {len(lla)} filas de órbita · {len(gl)} de cola · "
          f"{len(bins)} bins de la cota · {prod['medidas_usadas']} medidas")


if __name__ == "__main__":
    main()
