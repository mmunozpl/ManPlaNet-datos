#!/usr/bin/env bash
# Laboratorio «un DataMart de Kimball con software libre»: la plataforma
# (RustFS como S3, PostgreSQL, Airflow con dbt), el relleno histórico y el
# banco de pruebas.
#
#   ./laboratorio.sh datos    descarga la zona cruda de la API a la caché
#                             (2024-01-01 a 2026-10-31; unos veinte minutos)
#   ./laboratorio.sh init     secretos, imágenes, arranque y DAG en marcha:
#                             el relleno histórico de 34 meses empieza solo
#   ./laboratorio.sh estado   qué corre y cuántos runs han terminado
#   ./laboratorio.sh medir    ejecuta el banco de pruebas y escribe los CSV
#   ./laboratorio.sh parar    detiene los contenedores y conserva los datos
#   ./laboratorio.sh limpiar  borra contenedores, volúmenes y secretos
#
# Requisitos: docker con el plugin compose, openssl, jq, python3 y curl.
set -euo pipefail
cd "$(dirname "$0")"
export UID GID
GID="$(id -g)"
DC="docker compose"
S=secretos
CACHE="${CACHE_CRUDO:-$(pwd)/cache}"
DAG=visualizaciones_mensual

aleatorio() { openssl rand -hex 16; }
fase() { echo "$1,$(( $(date +%s) - T0 ))" >> "$S/fases.csv"; }

esperar_url() {
  local i
  for i in $(seq 1 120); do
    curl -sf "$1" >/dev/null 2>&1 && return 0
    sleep 5
  done
  echo "sin respuesta de $1" >&2; exit 1
}

datos() {
  mkdir -p "$CACHE"
  # cuatro hilos: con ocho, la API devolvió errores de red en un 4 % de las
  # peticiones; lo que falle se repide al volver a lanzar «datos»
  python3 ingesta/descargar.py --desde 2024-01-01 --hasta 2026-10-31 --salida "$CACHE" --hilos 4
}

init() {
  if [ -e "$S/airflow.env" ]; then
    echo "ya hay un laboratorio inicializado; ./laboratorio.sh limpiar primero" >&2
    exit 1
  fi
  T0=$(date +%s)
  mkdir -p "$S" "$CACHE"
  : > "$S/fases.csv"

  # 1. secretos del laboratorio
  aleatorio > "$S/pg_admin.txt"
  AF=$(aleatorio); DBT=$(aleatorio); S3K=$(aleatorio); ADMIN=$(aleatorio)
  echo "$AF" > "$S/pg_airflow.txt"; echo "$DBT" > "$S/pg_dbt.txt"
  printf 'RUSTFS_ACCESS_KEY=laboratorio\nRUSTFS_SECRET_KEY=%s\n' "$S3K" > "$S/rustfs.env"
  cat > "$S/airflow.env" <<EOF
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:$AF@postgres:5432/airflow
AIRFLOW__API_AUTH__JWT_SECRET=$(aleatorio)
DATAMART_DSN=postgresql://dbt:$DBT@postgres:5432/datamart
DBT_PASSWORD=$DBT
S3_ACCESS_KEY=laboratorio
S3_SECRET_KEY=$S3K
DBT_ESTRATEGIA=${DBT_ESTRATEGIA:-delete+insert}
EOF
  printf '{"admin": "%s"}\n' "$ADMIN" > "$S/airflow-contrasenas.json"
  cat > "$S/medidor.env" <<EOF
DATAMART_DSN=postgresql://dbt:$DBT@postgres:5432/datamart
ADMIN_DSN=postgresql://admin_bd:$(cat "$S/pg_admin.txt")@postgres:5432/datamart
DBT_PASSWORD=$DBT
DBT_HOST=postgres
S3_ENDPOINT=http://rustfs:9000
S3_ACCESS_KEY=laboratorio
S3_SECRET_KEY=$S3K
S3_BUCKET=datalake
AIRFLOW_URL=http://airflow:8080
AIRFLOW_USUARIO=admin
AIRFLOW_CONTRASENA=$ADMIN
EOF
  printf 'CACHE_CRUDO=%s\n' "$CACHE" > .env
  chmod 600 "$S"/* .env
  # el contenedor de Airflow corre como su usuario (uid 50000) y tiene que
  # leer el fichero de contraseñas y la caché; el guion de arranque de
  # PostgreSQL corre como postgres (uid 999) y lee las tres contraseñas
  chmod 644 "$S/airflow-contrasenas.json" "$S"/pg_*.txt
  fase "secretos"

  [ -d "$CACHE/crudo" ] || { echo "la zona cruda no está en $CACHE: primero ./laboratorio.sh datos" >&2; exit 1; }

  # 2. imágenes
  $DC build airflow medidor
  $DC pull postgres rustfs
  fase "imágenes"

  # 3. arranque
  $DC up -d postgres rustfs airflow
  esperar_url "http://127.0.0.1:8080/api/v2/monitor/health"
  fase "plataforma arrancada"

  # 4. el DAG se despierta y el scheduler crea los 34 runs del relleno
  #    histórico (catchup), uno detrás de otro
  $DC exec -T airflow airflow dags unpause "$DAG" > /dev/null
  fase "DAG en marcha"
  echo "laboratorio en marcha en $(( $(date +%s) - T0 )) s"
  echo "consola de Airflow: http://127.0.0.1:8080 (admin, contraseña en $S/airflow-contrasenas.json)"
  echo "consola de RustFS:  http://127.0.0.1:9001 (laboratorio, clave en $S/rustfs.env)"
  echo "PostgreSQL:         127.0.0.1:5434, base datamart (usuarios admin_bd y dbt)"
}

estado() {
  $DC ps
  $DC exec -T airflow airflow dags list-runs "$DAG" -o json 2>/dev/null \
    | python3 -c "import sys, json, collections; r = json.load(sys.stdin); c = collections.Counter(x['state'] for x in r); print(len(r), 'runs:', dict(c))"
}

medir() {
  [ -e "$S/medidor.env" ] || { echo "primero ./laboratorio.sh init" >&2; exit 1; }
  $DC run --build --rm medidor
  mkdir -p "$S/registros"
  $DC logs --no-color --no-log-prefix airflow > "$S/registros/airflow.log" 2>&1
  docker stats --no-stream --format '{{.Name}},{{.MemUsage}}' > "$S/registros/recursos.txt"
  : > "$S/registros/imagenes.txt"
  for img in postgres:17.11 rustfs/rustfs:1.0.4 datamart-wikipedia-airflow datamart-wikipedia-medidor; do
    docker images --format '{{.Repository}}:{{.Tag}},{{.Size}}' "$img" >> "$S/registros/imagenes.txt"
  done
  python3 medidor/registros.py "$S/registros" "$S/fases.csv" .
}

parar() { $DC down; }
limpiar() {
  $DC --profile medir down -v --remove-orphans
  rm -rf "$S" .env
  echo "laboratorio borrado (la caché de la API se conserva en $CACHE)"
}

case "${1:-}" in
  datos|init|estado|medir|parar|limpiar) "$1" ;;
  *) sed -n '2,15p' "$0"; exit 1 ;;
esac
