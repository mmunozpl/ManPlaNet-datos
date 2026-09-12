#!/usr/bin/env python3
"""Medición del RAG sintético: permisos aplicados después de recuperar frente
a permisos aplicados dentro de la consulta.

Monta un corpus sintético de 600 fragmentos en tres ámbitos —público,
finanzas y salud laboral— con vectores de 64 dimensiones agrupados por ámbito
alrededor de un centroide, y un usuario autorizado solo al ámbito público que
lanza 300 consultas aleatorias —uniformes en la esfera, sin sesgo hacia su
ámbito— con k = 10. Con el permiso aplicado después de recuperar,
cuenta cuántos fragmentos ajenos lee el sistema y cuántos útiles entrega; con
el permiso dentro de la consulta, cuenta lo mismo. El índice es Qdrant en el
modo local de su cliente, con la misma API de filtro que el servidor.

No interviene ningún dato real de ninguna persona: los vectores son ruido con
semilla. Se guardan el corpus, las consultas con su resultado y el resumen, y
se escribe la ficha de procedencia al lado.
"""
import csv
import datetime
import json
from pathlib import Path

import numpy as np
from importlib.metadata import version as _version
from qdrant_client import QdrantClient
from qdrant_client.models import (Distance, FieldCondition, Filter, MatchAny,
                                  PointStruct, VectorParams)

SEMILLA = 20260825
DIM = 64
AMBITOS = ["público", "finanzas", "salud laboral"]
POR_AMBITO = 200
K = 10
N_CONSULTAS = 300
SIGMA_FRAGMENTO = 0.15    # dispersión por dimensión alrededor del centroide: con 64
                          # dimensiones deja el coseno dentro de un ámbito en torno a
                          # 0,4 y entre ámbitos en torno a 0, como los embeddings de
                          # texto de tres temas distintos
USUARIO_ACL = ["grupo-publico"]
DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo


def unidad(x: np.ndarray) -> np.ndarray:
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def corpus(rng) -> tuple[np.ndarray, list[str]]:
    """un centroide por ámbito y 200 fragmentos alrededor de cada uno."""
    centroides = unidad(rng.standard_normal((len(AMBITOS), DIM)))
    vecs, ambs = [], []
    for c, nombre in zip(centroides, AMBITOS):
        vecs.append(unidad(c + SIGMA_FRAGMENTO * rng.standard_normal((POR_AMBITO, DIM))))
        ambs += [nombre] * POR_AMBITO
    return np.vstack(vecs), ambs, centroides


def acl_de(ambito: str) -> list[str]:
    return ["grupo-" + ambito.replace("salud laboral", "salud").replace("público", "publico")]


def montar():
    """corpus, consultas e índice en memoria; lo usa la medición y la demo."""
    rng = np.random.default_rng(SEMILLA)
    vecs, ambs, centroides = corpus(rng)
    consultas = unidad(rng.standard_normal((N_CONSULTAS, DIM)))
    cli = QdrantClient(":memory:")
    cli.create_collection("fragmentos", vectors_config=VectorParams(size=DIM, distance=Distance.COSINE))
    cli.upsert("fragmentos", points=[
        PointStruct(id=i, vector=v.tolist(), payload={"ambito": a, "acl": acl_de(a)})
        for i, (v, a) in enumerate(zip(vecs, ambs))])
    return cli, vecs, ambs, consultas


def filtro_de(acl: list[str]) -> Filter:
    return Filter(must=[FieldCondition(key="acl", match=MatchAny(any=acl))])


def main() -> None:
    cli, vecs, ambs, consultas = montar()
    filtro = filtro_de(USUARIO_ACL)

    filas = []
    for i, q in enumerate(consultas):
        # permiso después de recuperar: se recupera todo y se descarta lo ajeno
        post = cli.query_points("fragmentos", query=q.tolist(), limit=K).points
        utiles = [p for p in post if set(p.payload["acl"]) & set(USUARIO_ACL)]
        # permiso dentro de la consulta: el índice no devuelve lo ajeno
        pre = cli.query_points("fragmentos", query=q.tolist(), limit=K, query_filter=filtro).points
        filas.append({"consulta": i, "post_utiles": len(utiles), "post_expuestos": K - len(utiles),
                      "post_vacia": int(len(utiles) == 0), "pre_utiles": len(pre),
                      "pre_expuestos": sum(1 for p in pre if not set(p.payload["acl"]) & set(USUARIO_ACL))})

    DESTINO.mkdir(parents=True, exist_ok=True)
    with (DESTINO / "corpus.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["id", "ambito", "acl"] + [f"v{j}" for j in range(DIM)])
        for i, (v, a) in enumerate(zip(vecs, ambs)):
            w.writerow([i, a, "|".join(acl_de(a))] + [f"{x:.5f}" for x in v])
    with (DESTINO / "consultas.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]) + [f"q{j}" for j in range(DIM)])
        w.writeheader()
        for r, q in zip(filas, consultas):
            w.writerow({**r, **{f"q{j}": f"{x:.5f}" for j, x in enumerate(q)}})

    exp = np.array([r["post_expuestos"] for r in filas]); ut = np.array([r["post_utiles"] for r in filas])
    G = vecs @ vecs.T; mismo = np.equal.outer(ambs, ambs); np.fill_diagonal(mismo, False)
    cos_dentro = round(float(G[mismo].mean()), 3); cos_entre = round(float(G[~np.equal.outer(ambs, ambs)].mean()), 3)
    res = {
        "semilla": SEMILLA, "dim": DIM, "ambitos": AMBITOS, "por_ambito": POR_AMBITO, "corpus": len(ambs),
        "k": K, "n_consultas": N_CONSULTAS, "sigma_fragmento": SIGMA_FRAGMENTO, "consultas": "uniformes en la esfera",
        "usuario_acl": USUARIO_ACL, "cos_dentro_ambito": cos_dentro, "cos_entre_ambitos": cos_entre, "motor": f"qdrant-client {_version('qdrant-client')}, modo local (:memory:)",
        "post_exp_media": round(float(exp.mean()), 2), "post_exp_total": int(exp.sum()), "post_exp_max": int(exp.max()),
        "post_con_exposicion": int((exp > 0).sum()), "post_utiles_media": round(float(ut.mean()), 2),
        "post_vacias": int((ut == 0).sum()),
        "pre_exp_total": int(sum(r["pre_expuestos"] for r in filas)), "pre_utiles_media": round(float(np.mean([r["pre_utiles"] for r in filas])), 2),
        "extraido": datetime.date.today().isoformat(),
    }
    (DESTINO / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (DESTINO / "INSTANTANEA.md").write_text(f"""# Medición del RAG sintético: el permiso antes o después de recuperar

Corpus sintético, no documentos: `corpus.csv` guarda 600 vectores de {DIM}
dimensiones generados con semilla fija, agrupados en tres ámbitos alrededor de
un centroide, con la lista de autorizados de cada fragmento. `consultas.csv`
guarda las {N_CONSULTAS} consultas de un usuario autorizado solo al ámbito
público y, para cada una, cuántos fragmentos ajenos leyó el sistema y cuántos
útiles entregó en cada variante. No interviene ningún dato de ninguna persona.

- Motor: {res['motor']} — misma API de filtro que el servidor
- Semilla: {SEMILLA} · dimensiones: {DIM} · fragmentos: {len(ambs)} ({POR_AMBITO} por ámbito) · k = {K}
- Dispersión de los fragmentos alrededor de su centroide: {SIGMA_FRAGMENTO} por dimensión, que deja el coseno medio en {cos_dentro} dentro de un ámbito y {cos_entre} entre ámbitos · consultas uniformes en la esfera
- Extraído: {res['extraido']}

## Resultado

| | permiso después de recuperar | permiso dentro de la consulta |
|---|---|---|
| fragmentos ajenos leídos, media por consulta | {res['post_exp_media']} | 0 |
| fragmentos ajenos leídos, total | {res['post_exp_total']} | {res['pre_exp_total']} |
| consultas con al menos uno ajeno | {res['post_con_exposicion']} de {N_CONSULTAS} | 0 |
| resultados útiles entregados, media de {K} | {res['post_utiles_media']} | {res['pre_utiles_media']} |
| consultas sin ningún resultado útil | {res['post_vacias']} | 0 |

## Campos

| Columna | Origen |
|---|---|
| `ambito`, `acl` | ámbito del fragmento y su lista de autorizados |
| `v0`…`v{DIM-1}`, `q0`…`q{DIM-1}` | el vector, normalizado |
| `post_utiles`, `post_expuestos`, `post_vacia` | recuperar k y descartar lo ajeno después |
| `pre_utiles`, `pre_expuestos` | filtro de `acl` dentro de la consulta |

La dispersión de los ámbitos es una decisión del diseño, no un dato: con más
solapamiento entre ámbitos se lee más material ajeno, y con menos, menos. Se
declara aquí para que se pueda discutir o rehacer con otro valor.
""", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("post_exp_media", "post_exp_total", "post_con_exposicion",
                                          "post_utiles_media", "post_vacias", "pre_exp_total", "pre_utiles_media")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
