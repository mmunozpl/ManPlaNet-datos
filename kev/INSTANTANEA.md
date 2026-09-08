# Instantánea del catálogo KEV

Recuento agregado, no el catálogo: `altas.csv` no contiene identificadores
de vulnerabilidad, productos ni descripciones, solo cuántas entradas se
dieron de alta cada día. El catálogo íntegro lo publica CISA y se consulta
en la fuente.

- Feed: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
- Versión del catálogo: `2026.09.04`
- Publicado por CISA: 2026-09-04T16:47:03.5197Z
- Extraído: 2026-09-08
- Entradas del catálogo: 1695
- Días con altas: 465
- Primer día: 2021-11-03 · último: 2026-09-04
- Entradas dadas de alta en sábado o domingo: 1

## Campos

| Columna | Origen |
|---|---|
| `fecha` | `dateAdded` de las entradas, agrupado |
| `dia_semana` | derivado de `fecha`, en huso local del catálogo |
| `altas` | número de entradas con esa `dateAdded` |

El día de la semana es cálculo propio sobre la fecha que publica CISA, que
no incluye hora: una alta de última hora del viernes y otra de primera hora
del lunes se distinguen por su fecha, no por su marca de tiempo.
