# Las nueve amenazas de ISO/IEC 27090:2026 frente a lo que ya se cataloga

Medición del 26-10-2026. De las 170 técnicas que cataloga MITRE ATLAS (versión
5.6.0), 62 caen dentro de las nueve amenazas que ISO/IEC 27090:2026 describe en
su cláusula 6, 17 en las versiones para IA de ataques convencionales de su
anexo B y 91 fuera de las dos (reconocimiento, preparación, acceso,
recolección, movimiento e impacto genérico, que la norma deja a ISO/IEC
27002). De los 57 casos de estudio de ATLAS (17 incidentes reales y 40
ejercicios), 52 tocan al menos una de las nueve amenazas y 5 ninguna. Las dos
amenazas de privacidad, inferencia de pertenencia (6.4) e inversión del modelo
(6.6), tienen una técnica cada una en ATLAS y ningún caso de estudio; la
inyección de prompt (6.9), la evasión (6.3) y la salida con ataques de
inyección (6.10) aparecen en 24, 22 y 21 casos. De las 35 mitigaciones de ATLAS, 31
cubren al menos una técnica de las nueve amenazas; la que más cubre es el
registro de telemetría de la IA (AML.M0024), con 15 técnicas en seis
amenazas, y las dos de privacidad tienen 3 mitigaciones cada una. De los 17
elementos de la taxonomía de NIST AI 100-2 E2025, los 17 encajan en alguna de
las nueve; de los 10 de OWASP Top 10 para LLM (2025), 7; de los 5 ataques que
nombra el artículo 15.5 del Reglamento (UE) 2024/1689, 4.

## Qué se midió

- **a. MITRE ATLAS repartido entre las nueve amenazas.** Cada una de las 170
  técnicas (101 raíz y 69 subtécnicas, en 16 tácticas) recibe una cláusula de
  la 27090 (6.2 a 6.10), el anexo B o «fuera», por una regla escrita por
  técnica en `generar.py` (`MAPA` y `MOTIVOS`); una subtécnica hereda la de
  su raíz salvo regla propia. Cada caso de estudio se reparte según las
  técnicas de su procedimiento. La madurez (`realized`, `demonstrated`,
  `feasible`) es la que declara ATLAS.
- **b. Mitigaciones.** Cada una de las 35 mitigaciones de ATLAS declara las
  técnicas que trata; hereda las cláusulas de esas técnicas, y se cuenta
  cuántas mitigaciones cubren al menos una técnica de cada cláusula.
- **c. Correspondencias.** Los 17 apartados de ataque del índice de NIST AI
  100-2 E2025 (2.2 a 2.4 y 3.2 a 3.5, con su página), los 10 elementos de
  OWASP Top 10 for LLM Applications 2025 y los 5 ataques del artículo 15.5
  del Reglamento de IA, cada uno con la cláusula o cláusulas de la 27090 que
  lo recogen, o «fuera» si ninguna.

## Cómo se midió

La norma ISO/IEC 27090:2026 no es pública: las nueve amenazas se nombran por
el título de las cláusulas 6.2 a 6.10 de su índice, y el contenido del anexo B
(cadena de suministro, denegación de servicio y puertas traseras) por el mismo
índice. El reparto es una lectura de quien mide, y por eso va técnica a
técnica en `atlas_tecnicas_27090.csv`, con el motivo de cada decisión que no
es la obvia: el jailbreak va a inyección de prompt porque entra por el prompt
directo y la norma no le da cláusula propia; insertar el disparador de una
puerta trasera va a envenenamiento de datos; alterar la configuración de un
agente, a envenenamiento directo del modelo; la invocación de herramientas
por un agente, a salida con ataques de inyección. Las técnicas de cadena de
suministro, denegación de servicio y consumo de recursos van al anexo B.

ATLAS se descarga de `dist/ATLAS.yaml` del repositorio público
`mitre-atlas/atlas-data` (licencia Apache-2.0) y se guarda al lado del guion
para que la medición sea repetible sobre la misma versión.

## Cifras principales

| | técnicas | de ellas realized | casos | incidentes | mitigaciones |
|---|---|---|---|---|---|
| 6.2 envenenamiento de datos | 10 | 2 | 9 | 2 | 12 |
| 6.3 evasión | 7 | 4 | 22 | 8 | 12 |
| 6.4 inferencia de pertenencia | 1 | 0 | 0 | 0 | 3 |
| 6.5 exfiltración del modelo | 3 | 2 | 6 | 1 | 6 |
| 6.6 inversión del modelo | 1 | 0 | 0 | 0 | 3 |
| 6.7 envenenamiento directo del modelo | 8 | 5 | 9 | 2 | 8 |
| 6.8 salida sensible del modelo | 11 | 1 | 8 | 0 | 11 |
| 6.9 inyección de prompt | 14 | 3 | 24 | 3 | 6 |
| 6.10 salida con ataques de inyección | 7 | 3 | 21 | 3 | 11 |
| anexo B | 17 | 7 | 12 | 4 | 8 |
| fuera de la norma | 91 | 37 | 55 | 17 | 22 |

Un caso cuenta en cada cláusula que toca y una mitigación en cada cláusula
que cubre, así que esas columnas no suman 57 ni 35. Los casos van de marzo de 2016 a febrero de 2026.

## Límites

Una sola lectura del reparto, sin segundo codificador. ATLAS cataloga lo
publicado y lo ejercitado, no la frecuencia real de cada ataque; sus 40
ejercicios son demostraciones de equipos rojos, no incidentes. La norma se
lee por su índice y por lecturas publicadas tras su salida, no por su texto.

## Repetir la medición

```
python generar.py            # descarga ATLAS.yaml y escribe los CSV
```

## Ficheros

`atlas_tecnicas_27090.csv` (una fila por técnica, con cláusula y motivo),
`atlas_casos_27090.csv` (una fila por caso de estudio, con las cláusulas que
toca), `atlas_casos_anio.csv`, `resumen_27090.csv` (por cláusula),
`atlas_mitigaciones_27090.csv` (una fila por mitigación, con las cláusulas
que cubre), `correspondencias_27090.csv` (NIST, OWASP y Reglamento de IA),
`volumenes.json` y `ATLAS.yaml` (la copia medida, 5.6.0).
