# Instantánea del laboratorio del DataMart

Medido el 2026-11-05. PostgreSQL 17.11, Airflow 3.3.2, dbt-core 1.12.6 con dbt-postgres 1.11.0, RustFS 1.0.4 como S3; todo en Docker Compose en una sola máquina. Dato real: los mil artículos más vistos de cada día en es.wikipedia por tipo de acceso (API de Wikimedia), de enero de 2024 a octubre de 2026.

## Tamaños

- crudo.visualizaciones_top: 3949643 filas u objetos, 439.6 MB
- marts.accesos: 4 filas u objetos, 0.0 MB
- marts.dim_acceso: 4 filas u objetos, 0.0 MB
- marts.dim_articulo: 109711 filas u objetos, 16.1 MB
- marts.dim_fecha: 1096 filas u objetos, 0.1 MB
- marts.espacios_nombres: 13 filas u objetos, 0.0 MB
- marts.hechos_ranking_mensual: 825662 filas u objetos, 97.1 MB
- marts.hechos_visualizaciones: 3949643 filas u objetos, 499.3 MB
- marts.snap_articulo_tramo: 66331 filas u objetos, 11.2 MB
- crudo/: 4026 filas u objetos, 55.5 MB
- preparado/: 136 filas u objetos, 23.9 MB

## Cargas

- COPY desde CSV: 1390375 filas en 1.1 s (1219715 filas/s)
- INSERT por lotes de 1.000 (executemany): 1390375 filas en 23.7 s (58667 filas/s)
- INSERT multifila de 1.000: 1390375 filas en 32.8 s (42337 filas/s)
- upsert multifila (ON CONFLICT DO UPDATE), todas chocan: 1390375 filas en 44.8 s (31065 filas/s)
- COPY con índice único ya creado: 1390375 filas en 4.2 s (332485 filas/s)

## Consultas (mediana de 5, ms)

- plano, sin índices: mediana 156.5 ms, suma 3269 ms en 10 consultas
- estrella, sin índices: mediana 217.9 ms, suma 2747 ms en 10 consultas
- copo, sin índices: mediana 225.8 ms, suma 2822 ms en 10 consultas
- plano, con índices: mediana 98.0 ms, suma 2411 ms en 10 consultas
- estrella, con índices: mediana 212.9 ms, suma 2967 ms en 10 consultas
- copo, con índices: mediana 273.8 ms, suma 4304 ms en 10 consultas

## Estrategias de dbt

- delete+insert: 5.8 s, 3949643 filas, 0 claves duplicadas
- merge: 10.7 s, 3949643 filas, 0 claves duplicadas
- append: 4.6 s, 3965353 filas, 15710 claves duplicadas
- reconstrucción completa (--full-refresh, todos los modelos): 20.4 s, 3949643 filas, 0 claves duplicadas
- run incremental de todos los modelos (sin datos nuevos): 8.3 s, 3949643 filas, 0 claves duplicadas

## Tests de dbt

- 27 tests: {'pass': 26, 'warn': 1}
- dias_contiguos: warn, 34 filas

## Airflow

- 34 runs programados, 34 con éxito; mediana 26.0 s por run, suma 886 s
- cargar: mediana 0.9 s (34 ejecuciones)
- dbt_run: mediana 7.1 s (34 ejecuciones)
- dbt_seed: mediana 2.8 s (34 ejecuciones)
- dbt_snapshot: mediana 3.2 s (34 ejecuciones)
- dbt_test: mediana 4.2 s (34 ejecuciones)
- descargar: mediana 0.5 s (34 ejecuciones)
- preparar: mediana 1.7 s (34 ejecuciones)
- subir: mediana 1.7 s (34 ejecuciones)
- fallos_simulados_1: run en success a los 80 s, «descargar» con 2 intento(s)
- fallos_simulados_4: run en failed a los 371 s, «descargar» con 4 intento(s)
- registro: 1 aviso de fallo definitivo, 5 fallo simulado

## Idempotencia (octubre de 2026 cargado dos veces)

- marts.hechos_visualizaciones: 3949643 → 3949643 (igual)
- crudo.visualizaciones_top: 3949643 → 3949643 (igual)
- crudo.visualizaciones_top (2026-10): 120716 → 120716 (igual)
- marts.dim_articulo: 109711 → 109711 (igual)
- marts.hechos_ranking_mensual: 825662 → 825662 (igual)
- marts.snap_articulo_tramo: 66331 → 66331 (igual)
- claves duplicadas en los hechos: 0 → 0 (igual)
- huella crudo.visualizaciones_top (2026-10): fe082c483614 → fe082c483614 (igual)
- huella marts.hechos_visualizaciones (2026-10): 9a6ba3b7b22d → 9a6ba3b7b22d (igual)
- huella marts.dim_articulo: dd30dc5922f5 → dd30dc5922f5 (igual)
- huella marts.hechos_ranking_mensual (2026-10): 90cfdcd9f5d8 → 90cfdcd9f5d8 (igual)
- huella marts.snap_articulo_tramo: ffa7d35f06b4 → ffa7d35f06b4 (igual)

## Planes de la consulta 2 (los diez más vistos de un mes)

- estrella, sin índices: 194.5 ms, raíz Limit, peor estimación en Seq Scan (dim_articulo): 62608 filas estimadas frente a 35475 reales, 47972 bloques
- copo, sin índices: 224.9 ms, raíz Limit, peor estimación en Hash Join (copo_hechos ⋈ copo_fechas ⋈ copo_articulos ⋈ copo_espacios ⋈ copo_accesos): 970 filas estimadas frente a 10120 reales, 46572 bloques
- estrella, con índices: 71.2 ms, raíz Limit, peor estimación en Hash Join (dim_fecha ⋈ hechos_visualizaciones ⋈ dim_acceso ⋈ dim_articulo): 27044 filas estimadas frente a 30360 reales, 3712 bloques
- copo, con índices: 1334.8 ms, raíz Limit, peor estimación en Hash Join (copo_articulos ⋈ copo_espacios ⋈ copo_hechos ⋈ copo_fechas ⋈ copo_accesos): 1368 filas estimadas frente a 15180 reales, 4160951 bloques

## Dimensión con historia (snapshot de dbt)

- 66331 versiones de 58712 artículos, 58712 vigentes; dbt_valid_from entre 2026-11-05T12:55:38 y 2026-11-05T13:10:25 (14.8 minutos: hora de observación); fecha_datos con 34 valores, de 2024-01-31 a 2026-10-31 (fecha de negocio)
- artículo con más versiones: 13 (top 1000 desde 2024-01-31 → top 100 desde 2024-02-29 → top 1000 desde 2024-03-31 → top 100 desde 2024-05-31 → top 1000 desde 2024-06-30 → top 100 desde 2024-08-31 → top 1000 desde 2024-09-30 → top 100 desde 2024-10-31 → top 1000 desde 2024-12-31 → top 100 desde 2025-02-28 → top 1000 desde 2025-03-31 → top 100 desde 2026-05-31 → top 1000 desde 2026-06-30)

## Ranking mensual derivado frente a la lista mensual oficial (all-access)

- 34 meses; coincidencias, mediana: top 10 10, top 100 97, top 1000 915; artículos del top 1000 oficial ausentes del derivado, mediana 0; cociente visitas derivadas/oficiales en el top 100: mediana por artículo 0.970, suma sobre suma 0.968

## Esfuerzo

- `init` en 79 s: secretos a los 0 s; imágenes a los 55 s; plataforma arrancada a los 76 s; DAG en marcha a los 79 s
- 879 líneas de configuración, modelos y guiones en 26 ficheros, sin comentarios ni líneas en blanco
- imágenes: postgres:17.11 454MB; rustfs/rustfs:1.0.4 300MB; datamart-wikipedia-airflow:latest 2.94GB; datamart-wikipedia-medidor:latest 700MB
- memoria en reposo: airflow 1.842GiB; postgres 1.181GiB; rustfs 220.7MiB
