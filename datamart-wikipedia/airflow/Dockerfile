# Airflow del laboratorio: la imagen oficial con lo que necesitan las tareas
# de ingesta (boto3 contra el almacén S3, pyarrow para Parquet, psycopg para
# COPY) y dbt en un entorno virtual aparte, para que sus dependencias no
# choquen con las de Airflow (es la práctica que recomienda el propio dbt).
FROM apache/airflow:3.3.2-python3.12
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    python -m venv /opt/dbt && \
    /opt/dbt/bin/pip install --no-cache-dir dbt-core==1.12.6 dbt-postgres==1.11.0 && \
    chown -R airflow:0 /opt/dbt && \
    mkdir -p /opt/airflow/dbt-destino && chown airflow:0 /opt/airflow/dbt-destino
USER airflow
RUN pip install --no-cache-dir boto3==1.43.123 pyarrow==26.0.1 "psycopg[binary]==3.3.7"
# el proyecto dbt se monta solo lectura: artefactos y registros van al
# volumen dbt-destino, y dbt no escribe su cookie de telemetría
ENV PYTHONPATH=/opt DBT_SEND_ANONYMOUS_USAGE_STATS=false
