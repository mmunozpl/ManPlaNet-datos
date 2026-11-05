# Un DataMart de Kimball con software libre: el laboratorio y su medición

Plataforma analítica mínima, reproducible en Docker Compose, con las cuatro
piezas de un DataMart: una zona cruda en un almacén de objetos compatible
con S3, un almacén analítico en PostgreSQL, un orquestador (Airflow) y una
capa de modelado con tests y documentación (dbt). El dato es real y público:
los mil artículos más vistos de cada día en la Wikipedia en español, por
tipo de acceso, desde enero de 2024, tal como los sirve la API de analítica
de Wikimedia.

| Pieza | Software | Versión | Papel |
|---|---|---|---|
| zona cruda y preparada | RustFS (Apache-2.0) | 1.0.4 | almacén de objetos compatible con S3: los JSON de la API tal cual y un Parquet por acceso y mes |
| almacén analítico | PostgreSQL | 17.11 | la tabla de aterrizaje (`crudo`), las vistas de preparación y el modelo en estrella (`marts`) |
| orquestador | Apache Airflow (Apache-2.0) | 3.3.2 | un DAG mensual con relleno histórico, reintentos y aviso de fallo |
| modelado | dbt-core y dbt-postgres (Apache-2.0) | 1.12.6 y 1.11.0 | dimensiones, hechos, snapshot con historia, tests y documentación |
| ingesta | Python, boto3, pyarrow, psycopg | 3.12, 1.43.123, 26.0.1, 3.3.7 | descarga, subida al S3, Parquet y COPY |

## Reproducir

Requisitos: Docker con el plugin Compose, `openssl`, `jq`, `python3` y
`curl`. La zona cruda son unas 4.140 peticiones a la API (unos veinte
minutos, más 34 listas mensuales) y se guarda en una caché fuera del
repositorio.

```bash
./laboratorio.sh datos    # la zona cruda a la caché (CACHE_CRUDO, por defecto ./cache)
./laboratorio.sh init     # secretos, imágenes, arranque y el DAG en marcha
./laboratorio.sh estado   # cuántos de los 34 runs mensuales han terminado
./laboratorio.sh medir    # el banco de pruebas, cuando el relleno acabe
./laboratorio.sh limpiar  # borra contenedores, volúmenes y secretos
```

## Ficheros

| Fichero | Qué es |
|---|---|
| `compose.yaml` | los cuatro servicios y el medidor, la red interna y los volúmenes |
| `laboratorio.sh` | `datos`, `init`, `estado`, `medir`, `parar`, `limpiar` |
| `postgres/init.sh` | usuarios, bases de datos, esquemas y la tabla de aterrizaje |
| `airflow/Dockerfile` | la imagen oficial con las bibliotecas de ingesta y dbt en su propio entorno |
| `airflow/dags/visualizaciones.py` | el DAG mensual: descargar, subir, preparar, cargar, dbt seed, dbt run, dbt test, dbt snapshot; con el parámetro `fallos_simulados` la primera tarea falla a propósito |
| `ingesta/descargar.py` | la zona cruda: un JSON por día y acceso, con los días sin datos anotados, y la lista mensual oficial (`all-days`) de all-access, para comparar |
| `ingesta/s3.py`, `ingesta/preparar.py` | el almacén S3, el Parquet por mes y el COPY idempotente |
| `dbt/` | el proyecto: staging, dimensiones, hechos, snapshot, tests y seeds |
| `medidor/medir.py` | el banco de pruebas, desde la red interna |
| `medidor/registros.py` | el resumen de los registros, desde el anfitrión |

## Lo que mide

| CSV | Contenido |
|---|---|
| `cargas.csv` | un año de filas cargado con COPY, INSERT por lotes, INSERT multifila, upsert y COPY con índice |
| `consultas.csv` | diez consultas de BI sobre tres modelos (plano, estrella, copo de nieve), con y sin índices, mediana de cinco |
| `estrategias.csv` | las tres estrategias incrementales de dbt sobre la ventana de tres días, y la reconstrucción completa |
| `tests_dbt.csv` | cada test de dbt con su estado y sus filas |
| `runs_airflow.csv`, `tareas_airflow.csv` | los runs del relleno histórico y sus tareas, con duración e intentos, y los dos runs con fallo simulado (uno que el reintento recupera y otro que agota los reintentos) |
| `tamanos.csv` | filas y octetos de cada tabla y de cada zona del S3 |
| `planes.csv`, `planes/*.json` | EXPLAIN (ANALYZE, BUFFERS) de la consulta de los diez más vistos sobre la estrella y el copo, con y sin índices: tiempos, nodo raíz, el nodo con la peor estimación de filas y los accesos a bloques compartidos (en caché y leídos de disco) |
| `snapshot.csv`, `snapshot_versiones.csv`, `snapshot_ejemplo.csv` | la dimensión con historia: versiones, la hora de observación de dbt frente a la fecha de negocio de cada versión, y el artículo con más cambios de tramo |
| `ranking_oficial.csv` | el ranking mensual derivado de las listas diarias frente a la lista mensual oficial de la API (`all-days`), mes a mes: coincidencias en el top 10, 100 y 1000, ausentes, y el cociente de visitas del top 100 como mediana por artículo y como suma sobre suma |
| `idempotencia.csv` | las tablas antes y después de volver a cargar octubre de 2026 entero: filas, claves duplicadas y huella md5 del contenido (sin las columnas técnicas de auditoría) |
| `pruebas.csv` | cada paso del banco con su resultado y su duración |
| `avisos_airflow.csv`, `esfuerzo.csv`, `configuracion.csv`, `imagenes.csv`, `recursos.csv` | los avisos en los registros de las tareas, las fases del arranque, las líneas de configuración, las imágenes y la memoria |
| `INSTANTANEA.md` | el resumen legible de la última medición |

## Límites

- Una máquina y una ejecución: los tiempos son de un ordenador con Docker.
- Sin AWS: S3, Aurora, MWAA y Terraform se describen en la entrada y no se
  miden; el laboratorio usa sus equivalentes libres.
- Un solo proyecto de Wikipedia y las listas de mil: la API no sirve el
  detalle completo de cada artículo, y tiene días sin datos, que el
  laboratorio anota y los tests de dbt sacan a la luz.
