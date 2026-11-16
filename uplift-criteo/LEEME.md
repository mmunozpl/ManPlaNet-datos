# Incrementalidad publicitaria con el dato abierto de Criteo

Medición sobre el *Criteo Uplift Prediction Dataset*, versión 2.1: un
experimento publicitario aleatorizado, reunido por Criteo AI Lab a partir de
varias pruebas de incrementalidad, con 13.979.592 filas (una por usuario), doce
atributos anonimizados y las columnas `treatment`, `exposure`, `visit` y
`conversion`. El guion `generar.py` lo descarga, comprueba su huella y escribe
aquí solo agregados pequeños: el fichero original no se redistribuye.

## Procedencia y licencia

- Página oficial: <https://ailab.criteo.com/criteo-uplift-prediction-dataset/>.
  Su enlace de descarga (`go.criteo.net/criteo-research-uplift-v2.1.csv.gz`)
  redirigía el 16-11-2026 a un almacén que ya no resolvía.
- Copia usada: la de la organización verificada de Criteo en Hugging Face,
  `criteo/criteo-uplift`, fijada a la revisión
  `2424920019e49d52d72c13ac1143ec5d53af276b`. Fichero
  `criteo-research-uplift-v2.1.csv.gz`, 311.422.618 octetos, SHA-256
  `2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc`. Las
  cifras clave que publica Criteo (filas, tasas de visita y de conversión,
  proporción de tratamiento) se reproducen exactas.
- Licencia del dato: CC BY-NC-SA 4.0. El fichero bruto no se redistribuye: se
  descarga con su revisión y su huella fijadas. Los CSV y `resumen.json` de esta
  carpeta son resultados calculados sobre él, con atribución a Criteo, y se
  ofrecen con la misma licencia para uso no comercial; el guion va con la
  Apache-2.0 del repositorio.
- Cita: Diemert, Betlei, Renaudin y Amini, «A Large Scale Benchmark for Uplift
  Modeling», AdKDD 2018; y la versión ampliada, arXiv:2111.10106.
- Privacidad: según Criteo, el dato se submuestreó de forma no uniforme para
  que no se pueda deducir el nivel original de incrementalidad, y los
  atributos se proyectaron al azar para que no se puedan recuperar. Cada fila
  corresponde a un usuario identificado por una cookie en el momento de la
  recogida. Esta medición no intenta ninguna reidentificación y solo publica
  agregados.

## Reproducir

Desde la raíz del repositorio de datos, con su entorno fijado:

```bash
uv sync --frozen --group generadores
uv run python uplift-criteo/generar.py                  # todas las etapas
uv run python uplift-criteo/generar.py --etapa modelos  # una sola
```

El crudo (CSV comprimido, su copia en Parquet y las predicciones de la
prueba) queda en `crudo/`, que no se versiona. Hacen falta unos 300 MB de
descarga y 12 GB de memoria (pico medido de 12,2 GB); la ejecución completa
tardó 17 minutos y medio en un ordenador de sobremesa de 32 hilos, y dos
ejecuciones con la misma semilla dan los mismos CSV salvo los tiempos. La semilla está fijada (`SEMILLA = 2026`).

## Ficheros

| Fichero | Qué contiene |
|---|---|
| `grupos.csv` | usuarios, visitas y conversiones por tratamiento y exposición |
| `balance.csv` | diferencia estandarizada de medias de cada atributo: tratamiento frente a control y expuestos frente a no expuestos |
| `c2st.csv` | prueba de dos muestras con clasificador para el grupo, y su placebo |
| `contrastes.csv` | z, t de Welch, Mann-Whitney, permutación y bootstrap sobre el fichero completo |
| `contrastes_dispersion.csv` | errores típicos y dispersión de la permutación y del bootstrap |
| `cobertura.csv` | cobertura y error de tipo I de las pruebas en submuestras |
| `potencia.csv`, `tamano_muestra.csv` | potencia analítica frente a Monte Carlo, y tamaño de muestra |
| `encuesta.csv` | efecto mínimo detectable de una encuesta de brand lift, con tasas supuestas |
| `modelos.csv` | siete modelos de uplift: área Qini, captura, calibración y tiempos |
| `qini_curvas.csv`, `qini_bootstrap*.csv` | curvas Qini y réplicas del bootstrap de Poisson |
| `calibracion.csv` | uplift predicho frente a observado por decil |
| `separabilidad.csv` | intervalos del área Qini según el tamaño de la prueba |
| `siluetas.csv`, `segmentos.csv`, `deciles_uplift.csv` | segmentación por k-medias y por deciles |
| `escala.csv`, `consulta_central.sql`, `consulta_central.csv` | el cálculo central en DuckDB, en CSV y en Parquet, frente a pandas |
| `resumen.json` | procedencia, versiones, semilla y cifras centrales |
