# Competencias de GRC más allá del SGSI, medidas sobre datos reales

Medición del 12-11-2026. El trabajo de gobierno, riesgo y cumplimiento (GRC)
se mide aquí en seis bloques, cada uno sobre una fuente pública: los roles del
marco NICE del NIST, los requisitos por categoría del ENS y de SP 800-53B, los
incidentes de la base comunitaria VERIS, el muestreo de pruebas de control, la
vigencia de los certificados del registro del ENS y los artículos de seguridad
en las resoluciones de la AEPD.

Los ocho roles GRC del marco NICE (componentes v2.2.0) suman 609 enunciados
distintos de tarea, conocimiento y destreza; 36 los comparten cuatro roles o
más (30 de ellos son conocimientos) y 420 pertenecen a un solo rol. Los
requisitos crecen de 57 a 155 entre las categorías básica y alta del ENS
(medidas del anexo II más refuerzos) y de 149 a 370 entre las líneas base baja
y alta de SP 800-53B. De los 10.047 incidentes de VERIS, 324 traen importe y
175 en dólares; excluido uno de un billón por inverosímil, los 174 restantes
tienen una mediana de 307.500 dólares. Una lognormal ajustada a ellos es una hipótesis que la prueba de
Kolmogórov-Smirnov calibrada por simulación rechaza al 5 % (p = 0,029). Con ese
modelo y una frecuencia supuesta de 0,3 incidentes al año, el percentil 95 de
la pérdida anual es de 6,6 millones de dólares (entre 3,6 y 12,0 al reajustar
el modelo en 400 remuestreos), y cambia de 3,6 a 8,9 millones según la regla de
exclusión y el modelo: es un escenario ilustrativo, no una predicción. Para
afirmar menos de un 5 % de fallos con un 95 % de confianza hacen falta 59 casos
sin fallos; sobre la población real de VERIS (3,74 % de incidentes con un socio
o proveedor), ese plan aprueba el 10,3 % de 10.000 auditorías simuladas. El
15-10-2026, 253 de los 2.967 certificados del ENS por categoría vencían en 90
días y 6 seguían listados ya vencidos. De 780 resoluciones de la AEPD, 240
(30,8 %) citan un artículo de seguridad del RGPD y suman el 60,5 % de los
importes.

## Qué se midió

- **a. Competencias.** `nice_roles.csv`, `nice_solapes.csv` y
  `nice_enunciados.csv`: enunciados por rol y tipo, índice de Jaccard entre los
  28 pares de roles, y cada enunciado con los roles que lo tienen.
- **b. Requisitos.** `requisitos_categoria.csv` y `ens_medidas_categoria.csv`:
  controles y mejoras de las líneas base baja, moderada, alta y de privacidad de
  SP 800-53B (catálogo OSCAL) y, para las 73 medidas del anexo II del ENS, si
  aplican y cuántos refuerzos piden en cada categoría, leídos de la tabla de cada
  medida en el BOE consolidado.
- **c. Incidentes.** `veris_reparto.csv`, `veris_por_anio.csv`,
  `veris_importes_usd.csv`, `perdida_excedencia.csv` y `perdida_sensibilidad.csv`:
  acciones y actores de VCDB, importes en dólares, la curva de excedencia de una
  simulación de Monte Carlo de 100.000 años y su sensibilidad a la regla de
  exclusión y al modelo de cuantía.
- **d. Muestreo.** `muestras_atributos.csv` y `muestreo_simulado.csv`: tamaños
  mínimos de muestra por confianza, tasa tolerable y fallos admitidos, y 10.000
  auditorías simuladas por plan sobre la población de VCDB.
- **e. Proveedores.** `ens_vigencia.csv` y `ens_vencimientos_mes.csv`: estado de
  los certificados del ENS por categoría a la fecha de lectura del registro y
  vencimientos por mes, desde la medición `ens-certificados`.
- **f. Privacidad.** `aepd_articulos_seguridad.csv`: resoluciones e importes que
  citan los artículos 5.1.f, 25, 32, 33, 34 y 35 del RGPD, desde la medición
  `aepd-correctivos`.
- `resumen.json`: las cifras principales.

## Cómo se midió

Los ocho roles son los de la categoría de supervisión y gobierno que forman el
GRC (OG-WRL-002, 006, 007, 008, 012, 013, 016 y 017). Las medidas del ENS que
dependen del nivel de una dimensión se cuentan al nivel de la categoría; un
refuerzo a elegir entre varios cuenta como uno. Los importes de VERIS se usan en
dólares, sin convertir, y se excluye todo importe superior a 10.000 millones. La
frecuencia de la simulación (0,3 incidentes al año) es una hipótesis: VERIS no
tiene denominador. Los tamaños de muestra salen de la binomial (menor n con
P(X ≤ k | p tolerable) ≤ 1 − confianza). La semilla es 20261112. El corte de
vigencia del ENS es la fecha de lectura de su registro (15-10-2026).

## Licencias

Los agregados derivados de VCDB (`veris_*.csv` y `perdida_*.csv`) se
publican con la licencia de su fuente, CC BY-SA 4.0. NICE y el catálogo OSCAL
del NIST son de dominio público; el BOE es reutilizable con cita de la fuente.

## Límites

VERIS recoge incidentes publicados, sobre todo de Estados Unidos y anteriores a
2021, con importes que mezclan multas, acuerdos y costes estimados. Una medida
del ENS y un control del NIST no tienen el mismo tamaño: las series se comparan
en proporción. El registro del ENS y las resoluciones de la AEPD son los de sus
mediciones. Ningún dato de ninguna persona interviene y no se nombra a ninguna
organización: los resultados se presentan en forma agregada, sin identificadores
personales.

## Fuentes

- NICE Framework Components v2.2.0 (JSON):
  https://csrc.nist.gov/csrc/media/Projects/cprt/documents/nice/v2-2-0_nf_components.json
- Líneas base de SP 800-53B en OSCAL: https://github.com/usnistgov/oscal-content
- RD 311/2022, texto consolidado: https://www.boe.es/buscar/act.php?id=BOE-A-2022-7191
- VERIS Community Database (CC BY-SA 4.0): https://github.com/vz-risk/VCDB

## Repetir

```bash
cd grc-extendido
uv run generar.py               # unos 10 MB de descarga, con caché en descargas/
```
