# Instantánea de tendencias del vocabulario hacia la AGI en arXiv

Recuentos, no artículos: `cuotas.csv` guarda cuántos resúmenes de cs.LG,
cs.AI, cs.CL y cs.CV contienen cada término por año, el total de artículos de
esas categorías ese año, y la cuota por diez mil. No guarda ningún artículo.

- API: https://export.arxiv.org/api/query
- Extraído: 2026-09-18
- Años: 2018-2026 · el 2026 es parcial, hasta el 2026-09-18
- Categorías del denominador: cs.LG, cs.AI, cs.CL, cs.CV (unión)
- Términos: 14

## Campos de `cuotas.csv`

| Columna | Origen |
|---|---|
| `termino` | nombre visible |
| `consulta` | la consulta exacta enviada, sobre `abs:` |
| `anio`, `anio_parcial` | año de `submittedDate`; 1 si el año no ha terminado |
| `recuento` | `opensearch:totalResults` de la consulta con el rango del año |
| `denominador` | lo mismo, sin término |
| `por_diez_mil` | 10000 · recuento / denominador, cálculo propio |

## `comprobaciones.csv`

Evidencia de dos propiedades del buscador que gobiernan el método, medidas
sobre 2025: lematiza —`agentic` y `agent` devuelven lo mismo, y `reasoning` y
`reason` también—, y el guion crea tokens distintos en `neurosymbolic` frente
a `neuro-symbolic` pero no en `chain-of-thought` frente a `chain of thought`.
Por eso `agentic` y `reasoning` no están en la tabla, y `neurosymbolic` suma
las dos grafías con un OR.
