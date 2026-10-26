# Polars 2.0 y DuckDB 2.0 frente a sus versiones 1.x

Medición del 26-10-2026 (bancos a, b y c, con DuckDB 2.0.0 estable); la guía
de migración (d) y el diagnóstico de páginas enormes son del 15-10-2026, y la
pasada completa de ese día con la pre-versión de DuckDB 2.0 se conserva en
`medicion-2026-10-15/`. En TPC-H a escala 10, Polars 2.0 con su motor
predeterminado resuelve las 22 consultas en 6,62 s en caliente, frente a
13,40 s de la 1.44.2, y el pico mediano de memoria anónima por consulta baja
de 1.171 MB a 424 MB. Su motor de streaming es 1,91 veces más rápido que el
in-memory en el conjunto de las 22 consultas. DuckDB 2.0.0 tarda 9,26 s,
frente a 6,74 s de la 1.5.6 (la pre-versión del 15-10, 9,14 s), y su pico
mediano de memoria por consulta sube de 334 MB a 849 MB. Sobre 21,6 GiB de
Parquet y con 8 GiB de tope, el volcado a disco que Polars 2.0 activa por
defecto no cambia ningún desenlace, y DuckDB 2.0.0 es la única configuración
de once que termina las tres agregaciones (c3 en 72,50 s, volcando 5.905 MB);
la pre-versión fallaba en c3 con 8 GiB. De los 52 apartados de la guía de
migración de Polars, 23 cambian el resultado sin lanzar ningún error.

## Qué se midió

- **a. Repetición del banco del 11-08-2026.** Treinta millones de filas y diez
  columnas, seis maneras de recorrerlas y seis motores para la misma
  agregación, con el código de agosto copiado letra por letra.
- **b. TPC-H SF10.** Las 22 consultas en Polars (tres versiones, dos motores
  cada una) y en DuckDB (tres versiones), sobre Parquet.
- **c. Mayor que el tope de memoria.** Tres agregaciones sobre lineitem a
  SF100 (21,6 GiB de Parquet en 100 ficheros) con 8 GiB de tope y sin swap.
- **d. Cambios silenciosos de Polars 1.x a 2.0.** Un ejemplo mínimo por
  apartado de la guía de migración, en 1.43.1, 1.44.2 y 2.0.0.

## Cómo se midió

Equipo: AMD Ryzen 9 5950X (16 núcleos, 32 hilos) y 60,7 GiB de RAM. Un
entorno de uv por versión, todos con Python 3.11.14 (numpy 2.5 exige 3.12), y
sus versiones exactas en `entornos/*.txt`:

| biblioteca | versiones |
|---|---|
| Polars | 1.43.1 (la de agosto, retirada de PyPI después), 1.44.2, 2.0.0 |
| DuckDB | 1.5.5, 1.5.6, 2.0.0 (estable del 21-10-2026, motor v2.0.0 d54cbbe3df); el 15-10, 2.0.0.dev2610011535 (motor v2.0.0-alpha43763) |
| pandas | 2.3.3, 3.0.6, 3.1.0rc0 |
| pyarrow | 22.0.0 con pandas 2.3.3 y Polars 1.43.1, 26.0.0 en el resto |

Cada medida es un proceso nuevo dentro de un ámbito de cgroup v2 con tope de
memoria (20 GiB en a, b y d; 8 GiB sin swap en c). Antes de cada medida en
frío se expulsan los ficheros de la caché de página con
`posix_fadvise(DONTNEED)`, el método de agosto.

- **a.** Los cuatro ficheros regenerados con la semilla 7 son idénticos byte a
  byte a los de agosto (sha256 en `tamanos.csv`). Tiempo de pared del proceso
  entero y pico de memoria residente, mediana de tres tandas. La memoria del
  equipo estaba fragmentada: numpy y el mimalloc de pyarrow 26 piden páginas
  enormes, el núcleo compacta de forma síncrona en cada petición, y la lectura
  completa del CSV con pandas 2.3.3 pasa a tardar entre 111,71 y 156,80 s
  (`a_diagnostico_thp_numpy.csv`). La tanda principal se midió con
  `NUMPY_MADVISE_HUGEPAGE=0` y `MIMALLOC_ALLOW_THP=0`. Las series anteriores
  se conservan como `a_*_primera.csv` y `a_*_segunda.csv` (configuración
  predeterminada) y `a_*_tercera.csv` (solo numpy sin páginas enormes).
- **b.** Datos de la extensión tpch de DuckDB 1.5.6, con las columnas DECIMAL
  pasadas a DOUBLE (el tipo que obtiene polars-benchmark). Consultas de
  Polars: pola-rs/polars-benchmark, commit `401908a` (licencia Apache-2.0).
  Consultas de DuckDB: las de su extensión (`tpch_queries()`), sin tocar. Se
  cronometra dentro del proceso, desde la lectura de metadatos hasta el
  resultado: una tanda en frío y la mediana de tres en caliente. Los
  resultados se comparan con los de DuckDB 1.5.6 con tolerancia relativa de
  1e-9 (medio céntimo en las nueve consultas que polars-benchmark redondea a
  dos decimales).
- **c.** Consultas c1 (la 1 de TPC-H, cuatro grupos), c2 (suma de
  `l_quantity` por `l_orderkey`, 150 millones de grupos de estado fijo) y c3
  (máximo de `l_comment` por `l_orderkey`, estado de tamaño variable). Tres
  tandas en frío. El cgroup se monta como raíz de `/sys/fs/cgroup`, que es
  como lo ve un contenedor: Polars 2.0 solo detecta el tope así.
- **d.** La guía se contó a mano: 51 subapartados en cinco bloques más el
  bloque de retiradas, que es una tabla y cuenta como uno. El orden de filas se
  prueba con dos millones de filas y cinco tandas.

Los resultados de b y c derivan de TPC-H y no son comparables con resultados
publicados de TPC-H.

## Cifras principales

### a. Agosto, repetido con las versiones de agosto

| prueba | agosto | hoy | pandas 3.0.6 | pandas 3.1.0rc0 |
|---|---|---|---|---|
| CSV completo | 22,14 s · 7.634 MB | 22,86 s · 7.427 MB | 21,14 s · 4.674 MB | 2,91 s · 6.633 MB |
| Parquet completo | 1,47 s · 2.695 MB | 1,51 s · 2.669 MB | 1,50 s · 2.711 MB | 1,47 s · 2.701 MB |
| Parquet en streaming | 1,01 s · 132 MB | 0,99 s · 130 MB | 1,08 s · 257 MB | 1,06 s · 258 MB |
| CSV por trozos | 12,52 s · 134 MB | 12,26 s · 134 MB | 13,48 s · 132 MB | 4,51 s · 126 MB |

Con las versiones de agosto, las seis maneras quedan a menos de un 3,3 % del
tiempo publicado (de −2,1 % a +3,3 %) y a menos de un 3 % de su memoria. Los
seis motores quedan entre −6,2 % y +1,4 % en tiempo y entre −7,5 % y +11,4 %
en memoria, salvo el tiempo de Arrow IPC mapeado (1,58 s frente a 1,23 s).
DuckDB 1.5.5 responde en 0,15 s con 240 MB (agosto: 0,16 s y 259 MB). Pandas
3.1 lee el CSV en paralelo: con un solo hilo tarda 8,29 s.

### b. TPC-H SF10, suma de las 22 consultas

| configuración | caliente | fría | pico anónimo mediano |
|---|---|---|---|
| Polars 1.44.2, predeterminado (in-memory) | 13,40 s | 16,62 s | 1.171 MB |
| Polars 1.44.2, streaming | 9,79 s | 12,97 s | 1.046 MB |
| Polars 2.0.0, predeterminado (streaming) | 6,62 s | 9,57 s | 424 MB |
| Polars 2.0.0, in-memory | 12,65 s | 15,33 s | 1.345 MB |
| DuckDB 1.5.6 | 6,74 s | 9,17 s | 334 MB |
| DuckDB 2.0.0 | 9,26 s | 11,56 s | 849 MB |

Las nueve configuraciones terminan las 22 consultas y coinciden con DuckDB
1.5.6, salvo la 11. La extensión de DuckDB fija su fracción en 0,0001, el valor
de SF1, y polars-benchmark usa 0,0001/SF; con la fracción ajustada, las 8.685
filas coinciden (`b_tpch_q11_ajustada.csv`). DuckDB 2.0.0 es más de un 10 % más
lento en 19 de las 22 consultas, y en ninguna es más de un 10 % más rápido;
la pre-versión del 15-10 daba 9,14 s con el mismo reparto.

### c. 21,6 GiB de Parquet con 8 GiB de tope (tandas que terminan, de 3)

| configuración | c1 | c2 | c3 |
|---|---|---|---|
| Polars 1.43.1 y 1.44.2, predeterminado o streaming | 0 | 0 (1.44.2 streaming: 1) | 0 |
| Polars 1.44.2, streaming con volcado activado a mano | 0 | 3 (9,33 s) | 0 |
| Polars 2.0.0, predeterminado | 3 (7,18 s) | 3 (7,31 s) | 0 |
| Polars 2.0.0, streaming sin volcado | 3 (7,24 s) | 3 (7,26 s) | 0 |
| DuckDB 1.5.5 / 1.5.6 / 2.0.0 | 3 / 3 / 3 | 3 / 3 / 3 | 0 / 0 / 3 (72,50 s, 5.905 MB volcados) |

Para c1, Polars 1.44.2 en streaming necesita 14.025 MB de memoria anónima
(tope de 14 GiB, `c_referencia_14gib.csv`), Polars 2.0 5.696 MB y DuckDB entre
468 y 579 MB. Con 14 GiB, c3 solo termina en DuckDB 2.0.0 (19,27 s y 1.470 MB
volcados); la pre-versión del 15-10 la terminaba con 14 GiB (18,30 s) y no
con 8.

### d. Guía de migración de Polars 2.0 (1.44.2 frente a 2.0.0)

De 52 apartados, 23 cambian el resultado sin error, 22 pasan a lanzar un
error, en 4 desaparece un error y 3 quedan igual. Los 16 apartados que la guía
marca con «Danger» se reparten en 13 silenciosos y 3 con error; otros 10
apartados sin esa marca también cambian en silencio. En 5 de los 23, la 1.44.2
ya avisaba con un aviso de Python. El apartado 4 solo cambia el dibujo del
plan. El orden de `group_by` sin `maintain_order` no cambia: ya variaba de una
tanda a otra en la 1.x.

## Límites

Un solo equipo. Los bancos a, b y c son del 26-10-2026; d y el diagnóstico de
páginas enormes, del 15-10. Las cifras de a
están tomadas con las páginas enormes desactivadas en numpy y mimalloc. En la
segunda serie de diagnóstico, el sistema terminó por presión de memoria las
tres lecturas con la configuración predeterminada de pandas 2.3.3, que solo
constan en la primera. El banco c usa tres consultas y un tope, y deja sin
medir otras operaciones (ordenaciones, joins). El banco d prueba un ejemplo
por apartado, que no agota todos los casos de cada uno. La diferencia de Arrow
IPC mapeado con agosto (+29 %) queda sin explicar.

## Repetir la medición

```
python generar.py --datos DIR_DATOS --entornos DIR_ENTORNOS \
    --derrame DIR_VOLCADO --sin-thp --duckdb2 2.0.0
```

Sin `--duckdb2`, el guion mide la pre-versión del 1 de octubre (la pasada de
`medicion-2026-10-15/`). Los datos
ocupan unos 40 GB, y el volcado del banco c pide un disco con más de 64 GB
libres. `generar.py --prueba` ejecuta todo a escala reducida.

## Ficheros

`a_resumen.csv` y `a_tandas.csv` (a), `a_diagnostico_thp*.csv` (páginas
enormes), `b_tpch_*.csv` (b), `c_resumen.csv`, `c_mayor_que_ram.csv` y
`c_referencia_14gib.csv` (c), `d_cambios_apartados.csv` y
`d_cambios_casos.csv` (d), `afirmaciones.csv` (afirmaciones de los fabricantes
frente a lo medido), `tamanos.csv` y `entorno.json`. En `medicion-2026-10-15/`,
los mismos ficheros de a, b y c de la pasada del 15-10 con la pre-versión de
DuckDB 2.0, con su propio LEEME.
