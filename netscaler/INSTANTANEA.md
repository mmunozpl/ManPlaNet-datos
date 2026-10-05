# NetScaler ADC y Gateway en las listas de explotadas

Las entradas de NetScaler ADC y NetScaler Gateway (con su nombre anterior,
Citrix ADC y Gateway; fuera las de SD-WAN) del catálogo KEV de CISA,
cruzadas con la fecha de publicación de cada CVE en el NVD y con la EUVD de
ENISA: fuente y fecha de la marca de explotada, y observaciones de honeypot
de Shadowserver. No se redistribuye ningún catálogo. No interviene ningún
dato de ninguna persona.

- KEV: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json, versión `2026.10.04`, publicada
  2026-10-04T18:52:56.0635Z, 1734 entradas
- NVD: API 2.0, `https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=<CVE>`, campo `published`
- EUVD: `https://euvdservices.enisa.europa.eu/api/search?text=<CVE>`, `kevEntries/batch` y
  `honeypotObservations/batch`
- Extraído: 2026-10-05

## Ficheros

| Fichero | Contenido |
|---|---|
| `altas.csv` | una fila por CVE: id EUVD, publicación en el NVD, alta en el KEV, días entre las dos, si coinciden, plazo y triaje forense del KEV, uso conocido en ransomware, alta en el EU KEV y su diferencia con CISA, CVSS de la CNA, CWE, y primera y última observación de honeypot con las conexiones y las IP del último día |
| `por-anio.csv` | altas por año desde la carga inicial y cuántas entraron el mismo día de la publicación |
| `informes-ajenos.csv` | fechas de inicio de explotación que solo constan en informes de terceros, con su fuente; no son medición |
| `resumen.json` | los recuentos de arriba |

## Cómo se cuenta

Las 4 entradas con alta del 2021-11-03 son la
carga inicial del catálogo y su fecha no dice cuándo se supo de la
explotación: se listan, pero no entran en los recuentos por año ni en la
coincidencia de fechas. «Mismo día» compara la fecha `published` del NVD
con `dateAdded` del KEV; en NetScaler la CNA es Citrix y publica el CVE el
día de su boletín. La fecha del EU KEV y la de honeypot son las que sirve
la EUVD; la de honeypot es la primera vez que los sensores de Shadowserver
reconocen un intento, y solo puede existir después de que haya una firma que
lo reconozca. Las conexiones y las IP son las del último día observado, no
un promedio.
