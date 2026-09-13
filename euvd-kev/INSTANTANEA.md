# Las dos listas de vulnerabilidades explotadas

Recuento comparado del catálogo KEV de CISA y de las vulnerabilidades que la
EUVD de ENISA marca como explotadas, con la fuente de cada marca. No se
redistribuye ninguno de los dos catálogos: `eu-kev.csv` lleva solo las
entradas que la EUVD atribuye a su lista propia, el «EU KEV», y el resto son
agregados. No interviene ningún dato de ninguna persona.

- KEV: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json — versión `2026.09.11`, publicada
  2026-09-11T19:32:16.8993Z, 1709 entradas
- EUVD: `https://euvdservices.enisa.europa.eu/api/search?exploited=true`, más `kevEntries/batch` y
  `honeypotObservations/batch` — 1721 entradas explotadas
- Extraído: 2026-09-13

## Ficheros

| Fichero | Contenido |
|---|---|
| `resumen.json` | recuentos: entradas, fuentes de la marca, intersección, fechas, honeypot |
| `eu-kev.csv` | una fila por entrada del EU KEV: CVE, id EUVD, fecha de alta en el EU KEV y en el KEV de CISA, diferencia en días, asignador del CVE, proveedor, si tiene observación de honeypot |
| `ventanas-kev.csv` | entradas del KEV por año de alta y ventana entre el alta y la fecha límite |
| `antiguedad-kev.csv` | entradas del KEV por años entre el año del CVE y el del alta (10 = diez o más) |
| `altas-mensuales.csv` | altas por mes desde enero de 2025 en el KEV de CISA y en el EU KEV |

## Cómo se cuenta

La EUVD sirve, para cada entrada explotada, una lista de fuentes con código
`CISA` o `EUKEV` y la fecha de alta en cada una; la marca «explotada» de una
entrada puede venir de una fuente, de la otra o de las dos. La fecha del KEV
de CISA se toma del JSON de CISA, no de la copia de la EUVD, salvo para
comprobar que coinciden. Las ventanas del KEV son `dueDate` menos
`dateAdded`, en días naturales. La antigüedad al entrar es el año del alta
menos el año del identificador CVE, que es el de su asignación y no el del
descubrimiento.
