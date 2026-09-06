# Instantánea del catálogo SigmaHQ

Extracto de metadatos, no de reglas: `reglas.csv` no contiene títulos,
descripciones ni lógica de detección, solo el identificador de cada regla y
los campos agregables. Las reglas de SigmaHQ se publican bajo la Detection
Rule License 1.1; aquí no se redistribuye ninguna.

- Repositorio: https://github.com/SigmaHQ/sigma
- Commit: `272daf82bf77fb0bb97f1f0c4d82bc61154772e1`
- Fecha del commit: 2026-09-03
- Extraído: 2026-09-06
- Reglas con bloque `detection`: 3760
- Colecciones: rules, rules-emerging-threats, rules-threat-hunting, rules-compliance, rules-dfir

## Campos

| Columna | Origen |
|---|---|
| `id` | `id` de la regla (UUID), para poder localizarla en el repositorio |
| `coleccion` | directorio de primer nivel |
| `nivel` | `level` |
| `estado` | `status` |
| `producto`, `categoria`, `servicio` | `logsource` |
| `tacticas` | etiquetas `attack.<tactica>`, sin técnicas ni grupos |
| `fp_declarado` | 1 si la regla trae el campo `falsepositives` |
| `fp_sustantivo` | 1 si alguna entrada de ese campo dice algo más que «unknown», «unlikely» y equivalentes, con más de 12 caracteres |

El criterio de `fp_sustantivo` es una decisión del análisis, no del catálogo, y
se declara aquí para que se pueda discutir o rehacer con otro umbral.
