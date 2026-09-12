#!/usr/bin/env python3
"""La caché KV global por token en cuatro generaciones de DeepSeek, contada
desde sus ficheros de configuración.

Descarga el `config.json` público de cada modelo, cuenta cuántas capas
guardan caché global y cuántas entradas de caché produce cada token —según
las razones de compresión declaradas—, y deduce los bytes por entrada que
implica la cifra que publica la ficha de DeepSeek-V4.1-Flash. Después
contrasta esa cifra implícita con los formatos de caché que documenta el
repositorio FlashMLA de DeepSeek, a los que suma una clave de indexador
cuando el modelo la tiene.

No descarga pesos ni ejecuta modelos: solo lee configuraciones. Se guarda en
csv y se escribe la ficha de procedencia al lado.
"""
import csv
import datetime
import json
import urllib.request
from pathlib import Path

DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo
HF = "https://huggingface.co/deepseek-ai/{}/raw/main/config.json"

V1 = "deepseek-llm-67b-base"
V32 = "DeepSeek-V3.2"
V4 = "DeepSeek-V4-Flash"
V41 = "DeepSeek-V4.1-Flash"

# bytes por token que publica la ficha de V4.1-Flash (figura 1b)
FICHA = {V1: 389120, V32: 48068, V4: 3514, V41: 890}
FECHA = {V1: "2023-11", V32: "2025-12", V4: "2026-04", V41: "2026-09"}
# formatos de la caché principal documentados por FlashMLA (README,
# 10-09-2026): bytes por entrada, con sus escalas
FLASHMLA = {
    V32: 656,   # 512 nope FP8 + 4 escalas float32 + 64 RoPE bf16
    V4: 584,    # 448 nope FP8 + 64 RoPE bf16 + 8 bytes de escala
    V41: 288,   # 512 valores E2M1 (4 bits) + 32 escalas E4M3
}
# clave del indexador (DSA/CSA), por entrada: 128 valores, FP8 en V3.2
# y 4 bits después
INDEXADOR = {V32: 128, V4: 64, V41: 64}
CAMPOS_INSTANTANEA = """\
| Columna | Origen |
|---|---|
| `capas`, `capas_kv` | capas totales y capas que guardan caché global, del config |
| `entradas_por_token` | suma de 1/razón sobre las capas con caché, del config |
| `latente`, `bits` | dimensión de la entrada y precisión de almacenamiento |
| `bytes_token_ficha` | lo que publica la ficha de V4.1-Flash para cada generación |
| `bytes_entrada_implicitos` | `bytes_token_ficha` / `entradas_por_token`, cálculo propio |
| `bytes_entrada_declarados` | formato de FlashMLA más la clave del indexador, cuando la hay |
| `residuo_por_entrada` | implícitos − declarados: lo que el config y FlashMLA no fijan |
| `contexto_1M_MiB` | caché global para un millón de tokens, a la cifra de la ficha |
"""


def config(modelo: str) -> dict:
    """descarga el config.json del modelo, lo guarda y devuelve su texto."""
    with urllib.request.urlopen(HF.format(modelo), timeout=60) as r:
        c = json.load(r)
    (DESTINO / "configs").mkdir(exist_ok=True)
    (DESTINO / "configs" / f"{modelo}.json").write_text(
        json.dumps(c, indent=1), encoding="utf-8")
    return c.get("text_config", c)


def cuenta(modelo: str, t: dict) -> dict:
    """capas con caché global, entradas por token y bytes por entrada."""
    capas = t["num_hidden_layers"]
    if modelo == V1:
        # atención por grupos: K y V enteros, por cabeza de clave-valor,
        # en bf16
        d_cab = t["hidden_size"] // t["num_attention_heads"]
        latente = 2 * t["num_key_value_heads"] * d_cab
        return dict(capas=capas, capas_kv=capas, entradas_por_token=capas,
                    latente=latente, bits="16",
                    bytes_entrada_declarados=latente * 2, indexador=0,
                    bytes_token_config=capas * latente * 2)
    if modelo == V32:
        # MLA: un latente de 512 + 64 por capa, más la clave del indexador
        # DSA con su escala float32
        decl = FLASHMLA[modelo] + INDEXADOR[modelo] + 4
        return dict(capas=capas, capas_kv=capas, entradas_por_token=capas,
                    latente=t["kv_lora_rank"] + t["qk_rope_head_dim"],
                    bits="8 + RoPE en 16", bytes_entrada_declarados=decl,
                    indexador=INDEXADOR[modelo],
                    bytes_token_config=capas * decl)
    # V4 y V4.1: cada capa declara su razón de compresión; 0 = solo
    # ventana local
    razones = t["compress_ratios"][:capas]
    if modelo == V41:
        # solo las capas fuente guardan caché global
        fuentes = t["kv_source_layer_ids"]
        entradas = sum(1 / razones[i] for i in fuentes)
        capas_kv = len(fuentes)
    else:
        capas_kv = sum(1 for r in razones if r)
        entradas = sum(1 / r for r in razones if r)
    decl = FLASHMLA[modelo] + INDEXADOR[modelo]
    return dict(capas=capas, capas_kv=capas_kv,
                entradas_por_token=round(entradas, 5),
                latente=t["head_dim"],
                bits="8 + RoPE en 16" if modelo == V4 else "4",
                bytes_entrada_declarados=decl, indexador=INDEXADOR[modelo],
                bytes_token_config=round(entradas * decl, 1))


def main() -> None:
    filas = []
    for modelo in FICHA:
        f = cuenta(modelo, config(modelo))
        implicito = FICHA[modelo] / f["entradas_por_token"]
        residuo = implicito - f["bytes_entrada_declarados"]
        filas.append({
            "modelo": modelo, "fecha": FECHA[modelo], **f,
            "bytes_token_ficha": FICHA[modelo],
            "bytes_entrada_implicitos": round(implicito, 1),
            "residuo_por_entrada": round(residuo, 1),
            "contexto_1M_MiB": round(FICHA[modelo] * 1048576 / 2**20, 1)})
        print(f"[kv] {modelo:<22} capas {f['capas']:>3} · con caché global "
              f"{f['capas_kv']:>3} · entradas/token "
              f"{f['entradas_por_token']:>8} · ficha {FICHA[modelo]:>7} · "
              f"implícito/entrada {implicito:7.1f} · declarado "
              f"{f['bytes_entrada_declarados']:>4} · residuo {residuo:+.1f}")
    ruta = DESTINO / "generaciones.csv"
    with ruta.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    hoy = datetime.date.today().isoformat()
    (DESTINO / "INSTANTANEA.md").write_text(f"""\
# La caché KV global por token en cuatro generaciones de DeepSeek

Configuraciones, no pesos: `configs/` guarda el `config.json` público de cada
modelo tal como estaba en Hugging Face el {hoy}, y `generaciones.csv` la cuenta
que sale de ellos: cuántas capas guardan caché global, cuántas entradas de
caché produce cada token según las razones de compresión, los bytes por
entrada que implica la cifra publicada en la ficha de DeepSeek-V4.1-Flash, y
los que resultan de los formatos documentados por FlashMLA. No interviene
ningún dato de ninguna persona.

- Ficha con las cifras por token: https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash (figura 1b)
- Formatos de caché: https://github.com/deepseek-ai/FlashMLA (README, versión del 10-09-2026)
- Extraído: {hoy}

## Campos de `generaciones.csv`

{CAMPOS_INSTANTANEA}
La clave del indexador se cuenta a 128 valores por entrada —FP8 en V3.2, cuatro
bits después—; sus bytes de escala son el residuo, y se declaran como tal.
""", encoding="utf-8")


if __name__ == "__main__":
    main()
