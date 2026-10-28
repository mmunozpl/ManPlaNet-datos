# PHP2Shell: los avisos, los parches y las ramas sin soporte

Medición del 27-10-2026 sobre las dos vulnerabilidades de PHP publicadas el
21 de octubre de 2026, CVE-2026-109618 (ejecución remota de código por
corrupción de memoria al agotarse el límite) y CVE-2026-109619 (ejecución
remota de código por estado global residual entre peticiones), que el
proyecto PHP corrigió en 8.5.12, 8.4.27, 8.3.36 y 8.2.35 a las 14:00 UTC de
ese día. El NVD las puntúa 9,8 y 8,1 (CVSS v3.1) y 9,2 las dos (v4.0); los
avisos de GitHub del proyecto son de las 13:34 UTC, la EUVD de ENISA las
publicó a las 13:48 y las marca como explotadas desde el 26, y CISA las
añadió al catálogo KEV el 26 con plazo el 29 (tres días) y triaje forense
obligatorio. Esa demora de 5 días del CVE al KEV está en el percentil 23 de
las 1.758 entradas del catálogo (mediana 237 días) y en el 40 de las 274
altas de 2026 (mediana 13,5); desde la BOD 26-04 (10-06-2026) la mediana es
de 8 días. Entre los sistemas, Debian (13:45 UTC) y Ubuntu (13:56) publicaron
antes de la hora de PHP; Red Hat el mismo día; Alpine entre 18 y 32 horas
después; la imagen oficial de Docker entre 50 y 62 horas después. De los
WordPress que informan de su versión de PHP a WordPress.org, el 66,4 % corre
una rama con parche binario (8.2 a 8.5), el 28,2 % una rama con parche solo
de fuente (7.4, 8.0 y 8.1) y el 5,5 % una rama sin parche. La lista TLP:CLEAR
del NCSC de los Países Bajos reunía ese día 757 productos de 464 proveedores
que dependen de PHP: 219 vulnerables, 132 con corrección, 365 en
investigación y 40 no vulnerables.

## Qué se midió

- **a. Cronología.** `cronologia.csv`, a mano, con la fuente de cada hito:
  los indicios de 2024 y los informes de los tres descubridores (fundación
  PHP), el intento de
  explotación del 17 de octubre (Amazon), las filtraciones del 20 (fundación
  PHP), las reglas de Cloudflare, las imágenes de Chainguard, los avisos de
  GitHub, Debian, ENISA y Ubuntu, la publicación de PHP, el NVD, Red Hat,
  CISA, la declaración conjunta de la UE, Alpine, Docker y el KEV.
- **b. Demora del CVE al KEV.** `kev_demoras.csv`: las 1.758 entradas del
  KEV (versión 2026.10.26) con la fecha de publicación de su CVE en el NVD
  (API 2.0, filtro `hasKev`), la demora en días, el plazo y el triaje
  forense. `resumen_kev.json` resume la distribución entera, la de 2026 y la
  posterior a la BOD 26-04, y sitúa a PHP2Shell.
- **c. Parche por sistema.** `parches_sistemas.csv`: Ubuntu (API de CVE,
  fecha del primer USN), Red Hat (API de datos de seguridad, fecha de cada
  RHSA), Debian (rastreador y anuncios DSA/DLA), Alpine (commits de aports
  por rama) y la imagen oficial `php` de Docker Hub (`tag_last_pushed`), con
  las horas desde las 14:00 UTC del 21.
- **d. Versiones de PHP en WordPress.** `wordpress_php.csv`: la cuota de
  cada versión según `api.wordpress.org/stats/php/1.0/`, agrupada en ramas
  con parche binario, solo de fuente y sin parche; `resumen_wordpress.json`.
- **e. Productos afectados.** `ncsc_productos.csv`: la lista del NCSC-NL
  (`github.com/NCSC-NL/php2shell`, revisión 1d605e33 del 27-10-2026 a las
  14:51 UTC), una fila por producto con su estado para cada CVE; uno de los
  757, el propio motor de PHP, va sin estado; `resumen_ncsc.json`.
- **f. Fichas.** `fichas.csv`: NVD, EUVD y GitHub Security Advisories de
  las dos CVE.

## Cómo se midió

Las fechas de la cronología son las que da cada fuente, en UTC (el hito de
2024 no tiene fecha y va solo con el año); las del
NVD, la EUVD, GitHub, Ubuntu y Docker Hub llevan hora; las de Red Hat,
Debian y el KEV, solo día. La demora del CVE al KEV es la diferencia de días
entre la fecha de publicación en el NVD y la de alta en el KEV; para las
entradas cuyo CVE se publicó después de su alta la demora es negativa y se
conserva. Las horas desde el parche se cuentan desde las 14:00 UTC del 21 de
octubre, la hora anunciada por PHP; las etiquetas de php-src llevan de las
14:06 a las 14:09. La cuota de versiones de WordPress es la que la API
devolvía el 27-10-2026; WordPress.org no publica la fecha de la toma. La
lista del NCSC-NL se cuenta por el estado de CVE-2026-109618.

## Cifras principales

| | valor |
|---|---|
| entradas del KEV (2026.10.26) | 1.758 |
| demora CVE → KEV, mediana (todas / 2026 / desde la BOD 26-04) | 237 / 13,5 / 8 días |
| PHP2Shell: demora y percentil (todas / 2026) | 5 días; 23 / 40 |
| entradas con plazo de 3 días / con triaje forense | 146 / 93 |
| WordPress: parche binario / solo fuente / sin parche | 66,4 % / 28,2 % / 5,5 % |
| NCSC-NL: productos / proveedores | 757 / 464 |
| NCSC-NL: vulnerables / corregidos / en investigación / no vulnerables / sin estado | 219 / 132 / 365 / 40 / 1 |
| repositorios de GitHub con «php2shell» / con el CVE (27-10) | 1.083 / 730 |

## Límites

La cronología depende de lo que cada actor ha publicado y de la hora que
da; el intento del 17 de octubre lo afirma Amazon sobre su propia red de
señuelos. La demora al KEV se mide contra la publicación en el NVD, no
contra la del parche. Las fechas de Red Hat y Debian no llevan hora. La
cuota de WordPress solo cubre los sitios que informan a WordPress.org. La
lista del NCSC-NL es un inventario abierto que cambia a diario y sus estados
son los que sus editores han podido confirmar. El recuento de repositorios
de GitHub mezcla exploits, escáneres y mitigaciones.

## Repetir la medición

```
python generar.py                 # kev, fichas, sistemas, wordpress y ncsc
```

Las etapas `sistemas` y `ncsc` usan `gh` (GitHub CLI) para los commits de
aports y los avisos de seguridad de php-src.

## Ficheros

`cronologia.csv`, `kev_demoras.csv`, `resumen_kev.json`, `fichas.csv`,
`parches_sistemas.csv`, `wordpress_php.csv`, `resumen_wordpress.json`,
`ncsc_productos.csv`, `resumen_ncsc.json`.
