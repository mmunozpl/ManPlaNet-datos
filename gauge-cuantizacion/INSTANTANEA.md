# Instantánea de la órbita de gauge bajo cuantización

Agregados, no el dato crudo: las tablas de este directorio resumen el
conjunto de resultados que acompaña al depósito
[10.5281/zenodo.22904208](https://doi.org/10.5281/zenodo.22904208), publicado
por su autor en Hugging Face. El barrido completo —170 016 medidas del
principal y 642 048 del de condicionamiento controlado— se consulta en la
fuente; aquí van los percentiles, los bins y la tabla de contraste que
sostienen las figuras del artículo.

- Fuente: https://huggingface.co/datasets/ManPla/gauge-orbit-quantization-results/resolve/main/artifacts
- Depósito: 10.5281/zenodo.22904208 (v1.0, 22-09-2026, Apache-2.0)
- Extraído: 2026-09-23
- Medidas usadas para la cota: 101376
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
