# Instantánea — estado de enriquecimiento de los CVE en el NVD

- Extracción: 16-09-2026, contra la API 2.0 del NVD (`https://services.nvd.nist.gov/rest/json/cves/2.0`), sin clave.
- Periodo: CVE publicados desde el 01-01-2023 hasta el 2026-09-15, sin los rechazados (`noRejected`).
- Catálogo de explotadas de CISA en el momento de la extracción: 1710 entradas.
- Con ficha completa se cuentan los estados `Analyzed` y `Modified`, que son los que llevan puntuación y lista de productos afectados puestas por el NVD.

| año | publicados | ficha completa | aplazados | explotados |
|---|---|---|---|---|
| 2023 | 28816 | 100.0 % | 0.0 % | 165 |
| 2024 | 39953 | 80.54 % | 19.45 % | 160 |
| 2025 | 48153 | 62.65 % | 37.33 % | 195 |
| 2026 | 65786 | 49.68 % | 34.91 % | 156 |

Aplazados de 2026 por mes de publicación:

- 2026-01: 1732 de 4302 (40.26 %)
- 2026-02: 1568 de 4616 (33.97 %)
- 2026-03: 1590 de 6234 (25.51 %)
- 2026-04: 1610 de 5810 (27.71 %)
- 2026-05: 2642 de 6939 (38.07 %)
- 2026-06: 3235 de 7943 (40.73 %)
- 2026-07: 3745 de 9770 (38.33 %)
- 2026-08: 4811 de 12260 (39.24 %)
- 2026-09: 2031 de 7912 (25.67 %)

## Columnas de `cve-estados.csv.gz`

| columna | origen |
|---|---|
| `cve` | `cve.id` de la API |
| `publicado` | `cve.published`, fecha |
| `estado` | `cve.vulnStatus` |
| `en_kev` | 1 si el identificador está en el catálogo |
| `kev_alta` | `dateAdded` del catálogo, si está |

No interviene ningún dato de ninguna persona.
