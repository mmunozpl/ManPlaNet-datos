# Instantánea del catálogo KEV

Recuentos y una lista corta, no el catálogo: `altas.csv` y
`ventanas-mensuales.csv` no contienen identificadores de vulnerabilidad,
productos ni descripciones; `triaje-forense.csv` lleva solo el identificador
público, el proveedor, el producto y las fechas de las entradas que el
catálogo marca con `forensicTriage = Yes`. El catálogo íntegro lo publica
CISA y se consulta en la fuente.

- Feed: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
- Versión del catálogo: `2026.09.18`
- Publicado por CISA: 2026-09-18T19:00:05.0974Z
- Extraído: 2026-09-21
- Entradas del catálogo: 1716
- Días con altas: 472
- Primer día: 2021-11-03 · último: 2026-09-18
- Entradas dadas de alta en sábado o domingo: 1
- Entradas con marca de triaje forense: 58 (la primera, el
  2026-07-01; la última, el 2026-09-18)
- Altas desde la BOD 26-04 (2026-06-10): 99 —
  58 con ventana de tres días y marca,
  18 con tres días sin marca, 23
  con catorce días—

## Campos

### `altas.csv`

| Columna | Origen |
|---|---|
| `fecha` | `dateAdded` de las entradas, agrupado |
| `dia_semana` | derivado de `fecha`, en huso local del catálogo |
| `altas` | número de entradas con esa `dateAdded` |

### `ventanas-mensuales.csv`

| Columna | Origen |
|---|---|
| `mes` | `dateAdded`, año y mes |
| `altas` | entradas dadas de alta ese mes |
| `ventana_3`, `ventana_14`, `ventana_21`, `ventana_otra` | entradas
  según los días naturales entre `dateAdded` y `dueDate` |
| `triaje_forense` | entradas del mes con `forensicTriage = Yes` |

### `triaje-forense.csv`

| Columna | Origen |
|---|---|
| `cve`, `proveedor`, `producto` | `cveID`, `vendorProject`, `product` |
| `fecha_alta`, `vencimiento` | `dateAdded`, `dueDate` |
| `ventana_dias` | días naturales entre ambas |
| `ransomware` | `knownRansomwareCampaignUse` |
| `cwe` | `cwes`, separados por punto y coma |
| `componente_compartido` | si `notes` dice que afecta a un componente
  de código abierto o protocolo usado por distintos productos |

El día de la semana es cálculo propio sobre la fecha que publica CISA, que
no incluye hora: una alta de última hora del viernes y otra de primera hora
del lunes se distinguen por su fecha, no por su marca de tiempo. El
significado de la marca de triaje no lo define el feed: lo fija la tabla de
plazos de la BOD 26-04 («& forensic triage» en el escalón de tres días) y su
guía de implantación.
