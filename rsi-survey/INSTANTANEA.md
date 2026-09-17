# El survey de automejora recursiva, codificado

Transcripción del arXiv 2609.11873v2 (15-09-2026) generada el 2026-09-18. No interviene ningún dato de ninguna persona ni ninguna consulta a la red: las cifras son las publicadas y la codificación es propia y explícita.

## `l5-sistemas.csv` — los ocho mecanismos L5 de la tabla 7

| Columna | Origen |
|---|---|
| `sistema`, `fuente` | tabla 7 del survey y la fuente primaria leída |
| `cierra_en`, `estado_heredado`, `controles_externos` | las tres columnas de la tabla 7, traducidas |
| `estructural` | codificación propia: el mecanismo revisado persiste y gobierna una ronda posterior (sí / parcial / no) |
| `efectivo` | codificación propia: evidencia de sucesores mejores con presupuesto comparable y evaluación independiente, con significación (sí / parcial / no) |
| `evidencia` | la frase del survey o de la fuente primaria en la que se apoya la codificación |

## `hci-eq4.csv` — la figura 3 y la ecuación 4

| Columna | Origen |
|---|---|
| `dominio`, `hci_2026` | sección 2.1 del survey, observaciones 1 y 2 |
| `margen_restante` | 100 − HCI |
| `proyeccion_eq4` | R = 100 − 0.22·(100 − T), ecuación 4 |
| `ganancia_ilustrativa` | R − T |
| `fraccion_del_margen_cerrada` | (R − T) / (100 − T): la misma en todos los dominios por construcción |
