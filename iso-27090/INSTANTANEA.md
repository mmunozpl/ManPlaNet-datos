# Las nueve amenazas de ISO/IEC 27090:2026 frente a lo que ya se cataloga

Medición del 27-10-2026. De las 208 técnicas que cataloga MITRE ATLAS en su
publicación 2026.09 (del 15 de septiembre de 2026, formato 6.0.0), 68 caen
dentro de las nueve amenazas que ISO/IEC 27090:2026 describe en su cláusula 6,
22 en las versiones para IA de ataques convencionales de su anexo B y 118
fuera de las dos (reconocimiento, preparación, acceso, recolección, movimiento
e impacto genérico, y la IA usada por el atacante, que la norma remite a
ISO/IEC 27002 sin tratar). De los 73 casos de estudio de ATLAS (23 incidentes
reales y 50 ejercicios), 67 tocan al menos una de las nueve amenazas y 6
ninguna. Las dos amenazas de privacidad, inferencia de pertenencia (6.4) e
inversión del modelo (6.6), tienen una técnica cada una en ATLAS y ningún
caso de estudio; la inyección de prompt (6.9), la salida con ataques de
inyección (6.10) y la evasión (6.3) aparecen en 35, 31 y 24 casos. De las 40
mitigaciones de ATLAS, 35 cubren al menos una técnica de las nueve amenazas;
la que más cubre es el equipo rojo de IA (AML.M0035), con 25 técnicas en las
nueve amenazas y el anexo B, y las dos de privacidad tienen 4 mitigaciones
cada una. Repetido el reparto con las 17 decisiones dudosas cambiadas de
sitio, las técnicas dentro de las nueve pasan de 68 a 62 y los casos que
tocan alguna, de 67 a 66. De los 17 elementos de la taxonomía de NIST AI
100-2 E2025, los 17 encajan en alguna de las nueve; de los 10 de OWASP Top 10
para LLM (2025), 7; de los 5 ataques que nombra el artículo 15.5 del
Reglamento (UE) 2024/1689, 4.

## Qué se midió

- **a. MITRE ATLAS repartido entre las nueve amenazas.** Cada una de las 208
  técnicas (120 raíz y 88 subtécnicas, en 16 tácticas) recibe una cláusula de
  la 27090 (6.2 a 6.10), el anexo B o «fuera», por una regla escrita por
  técnica en `generar.py` (`MAPA` y `MOTIVOS`); una subtécnica hereda la de
  su raíz salvo regla propia. Cada caso de estudio se reparte según las
  técnicas de su procedimiento. La madurez (`realized`, `demonstrated`,
  `feasible`) es la que declara ATLAS.
- **b. Mitigaciones.** Cada una de las 40 mitigaciones de ATLAS declara las
  técnicas que trata; hereda las cláusulas de esas técnicas, y se cuenta
  cuántas mitigaciones cubren al menos una técnica de cada cláusula.
- **c. Sensibilidad del reparto.** El reparto se repite con las 17 decisiones
  dudosas cambiadas de sitio (`MAPA_ALT`): el jailbreak como evasión; la
  invocación de herramientas, la exfiltración, la destrucción y los comandos
  generados por un agente como efecto de la inyección (6.9) en vez de salida
  con inyección (6.10); el envenenamiento del RAG y del contexto del agente
  como inyección indirecta; el disparador de puerta trasera y los
  disparadores multimodales como parte del modelo envenenado; y la
  configuración del agente, la lógica de construcción del prompt, el sesgo de
  respuestas, el contenido servido al agente, la cosecha de credenciales en
  el RAG y el descubrimiento de capacidades del agente, fuera de las nueve.
- **d. Correspondencias.** Los 17 apartados de ataque del índice de NIST AI
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
suministro, denegación de servicio y consumo de recursos van al anexo B. Los
recuentos de casos y de mitigaciones heredan el reparto de técnicas, de modo
que no son una comprobación independiente de él; la prueba de sensibilidad
mide cuánto se mueven al cambiarlo.

ATLAS se descarga del fichero `dist/v6/ATLAS-2026.09.yaml` de la etiqueta
`v2026.09` del repositorio público `mitre-atlas/atlas-data` (licencia
Apache-2.0) y se guarda al lado del guion para que la medición sea repetible
sobre la misma publicación. El fichero `dist/ATLAS.yaml` de la raíz de ese
repositorio es una copia en el formato heredado (5.6.0, 170 técnicas y 57
casos) que no se actualiza desde mayo de 2026; la publicación vigente la dice
`dist/manifest.yaml`. La primera pasada de esta medición, del 26-10-2026, usó
esa copia; se repitió el 27 sobre la 2026.09.

## Cifras principales

| | técnicas | de ellas realized | casos | incidentes | mitigaciones | técnicas (alt.) | casos (alt.) |
|---|---|---|---|---|---|---|---|
| 6.2 envenenamiento de datos | 10 | 4 | 13 | 3 | 14 | 5 | 3 |
| 6.3 evasión | 8 | 4 | 24 | 8 | 13 | 8 | 33 |
| 6.4 inferencia de pertenencia | 1 | 0 | 0 | 0 | 4 | 1 | 0 |
| 6.5 exfiltración del modelo | 3 | 2 | 7 | 1 | 7 | 3 | 7 |
| 6.6 inversión del modelo | 1 | 0 | 0 | 0 | 4 | 1 | 0 |
| 6.7 envenenamiento directo del modelo | 9 | 5 | 11 | 2 | 9 | 9 | 8 |
| 6.8 salida sensible del modelo | 12 | 1 | 12 | 0 | 15 | 10 | 11 |
| 6.9 inyección de prompt | 17 | 7 | 35 | 6 | 8 | 22 | 38 |
| 6.10 salida con ataques de inyección | 7 | 3 | 31 | 5 | 12 | 3 | 8 |
| anexo B | 22 | 10 | 13 | 5 | 13 | 22 | 13 |
| fuera de la norma | 118 | 65 | 71 | 23 | 26 | 124 | 71 |

Un caso cuenta en cada cláusula que toca y una mitigación en cada cláusula
que cubre, así que esas columnas no suman 73 ni 40. Los casos van del 23 de
marzo de 2016 al 8 de julio de 2026; 34 son de 2025 y 2026, y de esos, 28
tocan la inyección de prompt o la salida con ataques de inyección.

## Límites

Una sola lectura del reparto, sin segundo codificador; la prueba de
sensibilidad mide cuánto cambian las cifras con otra lectura de las
decisiones dudosas, no si existe una lectura mejor. ATLAS cataloga lo
publicado y lo ejercitado, no la frecuencia real de cada ataque; sus 50
ejercicios son demostraciones de equipos rojos, no incidentes. La norma se
lee por su índice y por lecturas publicadas tras su salida, no por su texto.

## Repetir la medición

```
python generar.py            # descarga ATLAS-2026.09.yaml y escribe los CSV
```

## Ficheros

`atlas_tecnicas_27090.csv` (una fila por técnica, con cláusula y motivo),
`atlas_casos_27090.csv` (una fila por caso de estudio, con las cláusulas que
toca), `atlas_casos_anio.csv`, `resumen_27090.csv` (por cláusula),
`resumen_27090_sensibilidad.csv` (el mismo resumen con las 17 decisiones
cambiadas, y las columnas del reparto principal al lado),
`atlas_mitigaciones_27090.csv` (una fila por mitigación, con las cláusulas
que cubre), `correspondencias_27090.csv` (NIST, OWASP y Reglamento de IA),
`volumenes.json` y `ATLAS-2026.09.yaml` (la copia medida).
