#!/bin/bash
# primer arranque de PostgreSQL: los dos usuarios de servicio (Airflow para
# su base de metadatos, dbt para el DataMart), sus bases de datos y los tres
# esquemas de la plataforma (crudo, preparado y marts), con las contraseñas
# que laboratorio.sh dejó en los secretos del compose
set -e
AIRFLOW_PW=$(cat /run/secrets/pg_airflow)
DBT_PW=$(cat /run/secrets/pg_dbt)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOF
CREATE ROLE airflow LOGIN PASSWORD '$AIRFLOW_PW';
CREATE DATABASE airflow OWNER airflow;
CREATE ROLE dbt LOGIN PASSWORD '$DBT_PW';
-- el DataMart: tres zonas como esquemas, propiedad del usuario de dbt
CREATE SCHEMA crudo AUTHORIZATION dbt;
CREATE SCHEMA preparado AUTHORIZATION dbt;
CREATE SCHEMA marts AUTHORIZATION dbt;
CREATE SCHEMA banco AUTHORIZATION dbt;
GRANT CONNECT ON DATABASE datamart TO dbt;
-- la tabla de aterrizaje de la zona cruda: lo que sirve la API, fila a fila
CREATE TABLE crudo.visualizaciones_top (
    proyecto    text        NOT NULL,
    acceso      text        NOT NULL,
    fecha       date        NOT NULL,
    articulo    text        NOT NULL,
    visitas     bigint      NOT NULL,
    posicion    integer     NOT NULL,
    cargado_en  timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE crudo.visualizaciones_top OWNER TO dbt;
CREATE INDEX visualizaciones_top_fecha ON crudo.visualizaciones_top (fecha, acceso);
EOF
