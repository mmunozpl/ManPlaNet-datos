# Sondeo de configuraciones de transformers

Metadatos de arquitectura de los 600 modelos más descargados de Hugging Face,
leídos de su `config.json` público. No contiene pesos ni código: solo los
números que definen la forma del apilamiento.

- Fecha del sondeo: **07-09-2026**
- Modelos listados: 600 (los más descargados, `sort=downloads`)
- Con `config.json` legible: **495**
- Con recuento real de parámetros (`safetensors.total` de la API): **392**

## Campos

| Columna | Origen |
|---|---|
| `capas`, `ancho`, `cabezas`, `ffn` | los cuatro números del bloque, con sus alias por familia (`n_layer`/`n_embd`/`n_head`/`n_inner`) |
| `kv` | `num_key_value_heads`; igual a `cabezas` si no hay atención agrupada |
| `rope`, `rmsnorm`, `glu`, `gqa`, `moe` | presencia de cada componente |
| `params_entrada` | la parte de la predicción que corresponde a la entrada: tabla de vocabulario, tablas de posición o proyección de parches |
| `params_bloque` | la parte del apilamiento: `L` veces la suma de atención, perceptrón y normalizaciones |
| `params_predichos` | la suma de las dos anteriores: fórmula del bloque de 2017 más tres términos declarados |
| `params_reales` | `safetensors.total` de la API de Hugging Face |

## El reparto entre entrada y bloque

Sobre los modelos con predicción, la entrada pesa una mediana del 14,31 % en
los de lenguaje denso, del 0,86 % en los de visión pura (ViT, DeiT, BEiT,
DINOv2) y del 16,13 % en CLIP y SigLIP, que llevan las dos torres. La tercera
cifra sitúa el coste en la tabla de vocabulario y no en la modalidad.

## Dos fallos de detección que conviene conocer

Ambos se corrigieron antes de publicar, y ambos habrían producido cifras
plausibles y falsas.

1. **Las posiciones rotatorias se declaran de tres maneras.** Los modelos de
   2023 usan `rope_theta`; los de 2026, un diccionario anidado
   `rope_parameters`. Un detector que solo mire la primera forma da 24,6 % de
   adopción donde hay 41,0 %: mide la edad del detector, no la de los modelos.
2. **La parte de visión anidada es una torre; en la raíz es el mismo
   apilamiento.** En CLIP, `vision_config` describe una torre aparte que suma
   entera. En un ViT puro, `patch_size` está en la raíz y el apilamiento ya
   está contado. Sumar las dos cosas duplica, y el error salta al 98,9 %.

## Sesgo del muestreo, declarado

«Más descargado» no significa «más reciente» ni «mejor». El orden está
dominado por modelos pequeños de incrustación —la primera posición supera los
250 millones de descargas—, de modo que la muestra retrata **lo que se
ejecuta**, no lo que se publica. Las cifras de adopción de cada componente se
leen con esa salvedad.
