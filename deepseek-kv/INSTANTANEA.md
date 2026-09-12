# La caché KV global por token en cuatro generaciones de DeepSeek

Configuraciones, no pesos: `configs/` guarda el `config.json` público de cada
modelo tal como estaba en Hugging Face el 2026-09-13, y `generaciones.csv` la cuenta
que sale de ellos: cuántas capas guardan caché global, cuántas entradas de
caché produce cada token según las razones de compresión, los bytes por
entrada que implica la cifra publicada en la ficha de DeepSeek-V4.1-Flash, y
los que resultan de los formatos documentados por FlashMLA. No interviene
ningún dato de ninguna persona.

- Ficha con las cifras por token: https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash (figura 1b)
- Formatos de caché: https://github.com/deepseek-ai/FlashMLA (README, versión del 10-09-2026)
- Extraído: 2026-09-13

## Campos de `generaciones.csv`

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

La clave del indexador se cuenta a 128 valores por entrada —FP8 en V3.2, cuatro
bits después—; sus bytes de escala son el residuo, y se declaran como tal.
