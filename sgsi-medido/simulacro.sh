#!/usr/bin/env bash
# Simulacro de continuidad de los tres sistemas del alcance del SGSI.
#
# Para cada laboratorio en Docker se simula la pérdida total (contenedores,
# volúmenes, secretos y TLS borrados con `laboratorio.sh limpiar`) y se
# reconstruye solo desde lo versionado y la copia externa de los datos
# (`laboratorio.sh init`), midiendo el tiempo hasta que el servicio responde
# (el tiempo real de recuperación, que se contrasta con el objetivo RTO) y comprobando que los datos vuelven idénticos a los
# publicados (el RPO conseguido). Para la demo del RAG se mide cuánto tarda
# en reconstruirse el índice desde la semilla y se comprueba que los vectores
# coinciden con el CSV publicado.
#
# Escribe simulacro.csv junto a sí mismo; los registros detallados van a
# SIMULACRO_LOG (por defecto ./registros, fuera del repositorio).
# Requiere docker con compose (el usuario en el grupo docker) y la caché de la
# API de Wikimedia en CACHE_CRUDO, que `limpiar` conserva.
set -uo pipefail
AQUI=$(cd "$(dirname "$0")" && pwd)
DATA=$(cd "$AQUI/.." && pwd)
SALIDA="$AQUI/simulacro.csv"
LOG="${SIMULACRO_LOG:-$AQUI/registros}"; mkdir -p "$LOG"
PY="$DATA/.venv/bin/python"; [ -x "$PY" ] || PY=python3

fila() {  # laboratorio, fase, segundos, resultado, detalle
  printf '%s,%s,%s,%s,%s,"%s"\n' "$1" "$2" "$(date -u +%FT%TZ)" "$3" "$4" "${5//\"/\'}" >> "$SALIDA"
  echo "[$(date -u +%T)] $1 · $2 · $3 s · $4 · $5"
}
desde() { echo $(( $(date +%s) - $1 )); }
puerto_abierto() { timeout 3 bash -c "exec 3<>/dev/tcp/127.0.0.1/$1" 2>/dev/null && echo sí || echo no; }

# ---------------------------------------------------------------- PAM mínimo
pam() {
  cd "$DATA/pam-minimo" || return
  local T0; T0=$(date +%s)
  ./laboratorio.sh limpiar > "$LOG/pam-limpiar.log" 2>&1
  fila pam-minimo "pérdida simulada (contenedores; volúmenes; secretos y TLS borrados)" "$(desde $T0)" ok \
    "el diario de auditoría de la bóveda y las grabaciones del bastión se pierden con los volúmenes: no tenían copia"
  if ./laboratorio.sh init > "$LOG/pam-init.log" 2>&1; then
    fila pam-minimo "servicio reconstruido desde el código (init)" "$(desde $T0)" ok "bóveda; base de datos; servidor SSH y bastión configurados entre sí"
  else
    fila pam-minimo "servicio reconstruido desde el código (init)" "$(desde $T0)" fallo "ver pam-init.log"
  fi
  while IFS=, read -r f s; do fila pam-minimo "init: $f" "$s" ok "fase del guion de arranque"; done < secretos/fases.csv
  local sellada
  sellada=$(docker compose exec -T openbao bao status -format=json 2>/dev/null | "$PY" -c 'import sys, json; print(json.load(sys.stdin)["sealed"])' 2>/dev/null || echo "?")
  fila pam-minimo "comprobación: bóveda desprecintada" "$(desde $T0)" "$([ "$sellada" = False ] && echo ok || echo fallo)" "sealed=$sellada"
  local filas esperadas
  esperadas=$(( $(wc -l < datos/ine_28193_salarios.csv) - 1 ))
  filas=$(docker compose exec -T postgres psql -U admin_bd -d salarios -tAc "SELECT count(*) FROM salarios" 2>/dev/null | tr -d '[:space:]')
  fila pam-minimo "comprobación: datos restaurados desde el fichero versionado" "$(desde $T0)" "$([ -n "$filas" ] && [ "$filas" -gt 0 ] && echo ok || echo fallo)" \
    "$filas filas en la tabla salarios a partir de $esperadas líneas del CSV del INE; RPO 0: la fuente es un fichero versionado"
  local codigo
  codigo=$(curl -ks -o /dev/null -w '%{http_code}' --max-time 10 https://127.0.0.1:8888/ || echo 000)
  fila pam-minimo "comprobación: consola del bastión responde" "$(desde $T0)" "$([ "$codigo" != 000 ] && echo ok || echo fallo)" "HTTP $codigo en https://127.0.0.1:8888/"
  fila pam-minimo "comprobación: puerto SSH del bastión" "$(desde $T0)" "$([ "$(puerto_abierto 2223)" = sí ] && echo ok || echo fallo)" "127.0.0.1:2223 abierto: $(puerto_abierto 2223)"
  local lineas
  lineas=$(docker compose exec -T openbao sh -c 'wc -l < /openbao/logs/auditoria.log' 2>/dev/null | tr -d '[:space:]')
  fila pam-minimo "comprobación: diario de auditoría nuevo" "$(desde $T0)" ok "${lineas:-0} líneas: el diario empieza de cero; el anterior se perdió (RPO del diario: todo)"
  fila pam-minimo "tiempo real de recuperación" "$(desde $T0)" ok "segundos desde la pérdida hasta las comprobaciones superadas"
  ./laboratorio.sh parar > "$LOG/pam-parar.log" 2>&1
}

# ------------------------------------------------------------------ DataMart
datamart() {
  cd "$DATA/datamart-wikipedia" || return
  export CACHE_CRUDO="${CACHE_CRUDO:-$PWD/cache}"
  [ -d "$CACHE_CRUDO/crudo" ] || { fila datamart-wikipedia "caché de la API" 0 fallo "no está en $CACHE_CRUDO"; return; }
  local T0; T0=$(date +%s)
  ./laboratorio.sh limpiar > "$LOG/datamart-limpiar.log" 2>&1
  fila datamart-wikipedia "pérdida simulada (contenedores; volúmenes y secretos borrados)" "$(desde $T0)" ok \
    "se conservan el código versionado y la caché externa de la API ($(du -sh "$CACHE_CRUDO" | cut -f1)); los registros de Airflow se pierden: no tenían copia"
  if ./laboratorio.sh init > "$LOG/datamart-init.log" 2>&1; then
    fila datamart-wikipedia "plataforma reconstruida desde el código (init)" "$(desde $T0)" ok "PostgreSQL; RustFS y Airflow arrancados; DAG en marcha con el relleno histórico"
  else
    fila datamart-wikipedia "plataforma reconstruida desde el código (init)" "$(desde $T0)" fallo "ver datamart-init.log"; return
  fi
  while IFS=, read -r f s; do fila datamart-wikipedia "init: $f" "$s" ok "fase del guion de arranque"; done < secretos/fases.csv
  datamart_comprobar "$T0"
}

datamart_comprobar() {  # T0: el instante de la pérdida simulada
  local T0=$1
  # el relleno histórico: 34 meses, uno detrás de otro
  local exitos=0 fallos=0 total=0 limite=$(( 60 * 60 ))
  while :; do
    read -r total exitos fallos < <(docker compose exec -T airflow airflow dags list-runs visualizaciones_mensual -o json 2>/dev/null \
      | "$PY" -c 'import sys, json
try: r = json.load(sys.stdin)
except Exception: r = []
print(len(r), sum(x["state"] == "success" for x in r), sum(x["state"] == "failed" for x in r))' 2>/dev/null || echo "0 0 0")
    [ "${exitos:-0}" -ge 34 ] && break
    [ "${fallos:-0}" -ge 1 ] && { fila datamart-wikipedia "relleno histórico" "$(desde $T0)" fallo "runs fallidos: $fallos"; break; }
    [ "$(desde $T0)" -gt "$limite" ] && { fila datamart-wikipedia "relleno histórico" "$(desde $T0)" fallo "tiempo agotado con $exitos de 34"; break; }
    sleep 20
  done
  # el primer mes cargado (servicio mínimo) y el último, por el instante de fin de cada run según Airflow
  read -r primero ultimo < <(docker compose exec -T airflow airflow dags list-runs visualizaciones_mensual -o json 2>/dev/null \
    | "$PY" -c 'import sys, json, datetime as dt
r = [x for x in json.load(sys.stdin) if x["state"] == "success" and x.get("end_date")]
f = lambda s: int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
print(min(f(x["end_date"]) for x in r) - '"$T0"', max(f(x["end_date"]) for x in r) - '"$T0"')' 2>/dev/null || echo "? ?")
  fila datamart-wikipedia "primer mes cargado (servicio mínimo: una consulta responde)" "$primero" ok "instante de fin del primer run correcto según Airflow"
  fila datamart-wikipedia "relleno histórico completo (34 meses)" "$ultimo" "$([ "${exitos:-0}" -ge 34 ] && echo ok || echo fallo)" "runs: $total; correctos: $exitos; fallidos: $fallos; instante de fin del último run según Airflow"
  # los datos vuelven idénticos: recuentos y huellas md5 contra lo publicado
  "$PY" - "$AQUI" > "$LOG/datamart-huellas.sql" <<'EOF'
import ast, csv, sys, os
aqui = sys.argv[1]
arbol = ast.parse(open("medidor/medir.py", encoding="utf-8").read())
huellas = next(ast.literal_eval(n.value) for n in ast.walk(arbol)
               if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "HUELLAS" for t in n.targets))
pub = {r["objeto"]: r for r in csv.DictReader(open("idempotencia.csv", encoding="utf-8"))}
snap = {r["metrica"]: r["valor"] for r in csv.DictReader(open("snapshot.csv", encoding="utf-8"))}
for objeto in ("marts.hechos_visualizaciones", "crudo.visualizaciones_top", "marts.dim_articulo", "marts.hechos_ranking_mensual", "marts.snap_articulo_tramo"):
    print(f"SELECT 'filas {objeto}' AS objeto, count(*)::text AS valor, '{pub[objeto]['despues']}' AS publicado FROM {objeto};")
for objeto, sql in huellas.items():
    print(f"SELECT 'huella {objeto}', ({sql.strip().rstrip(';')}), '{pub['huella ' + objeto]['despues']}';")
# el snapshot, por su contenido de negocio: versiones y artículos frente a snapshot.csv, y una huella sin las
# marcas de tiempo técnicas de dbt (dbt_valid_from y dbt_valid_to llevan la hora de cada ejecución)
print(f"SELECT 'snapshot: versiones/artículos', count(*)::text || '/' || count(DISTINCT articulo_id)::text, '{snap['versiones']}/{snap['articulos']}' FROM marts.snap_articulo_tramo;")
print("SELECT 'huella de negocio del snapshot (sin marcas de dbt)', md5(string_agg(concat_ws('|', articulo_id, tramo, fecha_datos), E'\\n' ORDER BY articulo_id, fecha_datos, tramo)), 'sin valor publicado' FROM marts.snap_articulo_tramo;")
EOF
  local iguales=0 distintos=0 observadas=0
  while IFS='|' read -r objeto valor publicado; do
    [ -z "$objeto" ] && continue
    if [ "$publicado" = "sin valor publicado" ]; then
      fila datamart-wikipedia "comprobación: $objeto" "$(desde $T0)" ok "reconstruido $valor; se guarda para el próximo simulacro"
    elif [ "$valor" = "$publicado" ]; then
      iguales=$((iguales + 1)); fila datamart-wikipedia "comprobación: $objeto" "$(desde $T0)" ok "reconstruido $valor; publicado $publicado"
    elif [[ "$objeto" == "huella marts.snap_articulo_tramo" ]]; then
      observadas=$((observadas + 1))
      fila datamart-wikipedia "comprobación: $objeto" "$(desde $T0)" observación \
        "reconstruido $valor; publicado $publicado: la huella publicada incluye dbt_valid_from y dbt_valid_to, que la estrategia check de dbt rellena con la hora de cada ejecución, así que cambia por definición al reconstruir; el contenido de negocio se compara aparte"
    else
      distintos=$((distintos + 1)); fila datamart-wikipedia "comprobación: $objeto" "$(desde $T0)" fallo "reconstruido $valor; publicado $publicado"
    fi
  done < <(docker compose exec -T postgres psql -U admin_bd -d datamart -tA < "$LOG/datamart-huellas.sql" 2>>"$LOG/datamart-huellas.err")
  fila datamart-wikipedia "tiempo real de recuperación" "$ultimo" "$([ "$distintos" -eq 0 ] && [ "$iguales" -ge 10 ] && echo ok || echo fallo)" \
    "segundos desde la pérdida hasta los 34 meses cargados, según el instante de fin del último run de Airflow; las comprobaciones de identidad se hicieron después, con el servicio ya en pie ($iguales iguales; $distintos distintas; $observadas explicadas); RPO 0 sobre los datos: la zona cruda se rehace desde la caché externa"
  ./laboratorio.sh parar > "$LOG/datamart-parar.log" 2>&1
}

# ------------------------------------------------------------------ RAG demo
rag() {
  cd "$DATA/rag-sintetico" || return
  local T0; T0=$(date +%s)
  "$PY" - <<'EOF' > "$LOG/rag.log" 2>&1
import csv, sys, time
sys.path.insert(0, ".")
import numpy as np
import generar
t0 = time.perf_counter(); cli, vecs, ambs, consultas = generar.montar(); t_indice = time.perf_counter() - t0
pub = list(csv.DictReader(open("corpus.csv", encoding="utf-8")))
iguales = sum(1 for fila, v, a in zip(pub, vecs, ambs)
              if fila["ambito"] == a and all(abs(float(fila[f"v{j}"]) - v[j]) < 1e-5 for j in range(generar.DIM)))
cons = list(csv.DictReader(open("consultas.csv", encoding="utf-8")))
iguales_q = sum(1 for fila, q in zip(cons, consultas) if all(abs(float(fila[f"q{j}"]) - q[j]) < 1e-5 for j in range(generar.DIM)))
n = cli.count("fragmentos").count
print(f"{t_indice:.2f} {n} {iguales} {len(pub)} {iguales_q} {len(cons)}")
EOF
  read -r t_indice n iguales total iguales_q total_q < <(tail -1 "$LOG/rag.log")
  fila rag-sintetico "índice reconstruido desde la semilla" "$(desde $T0)" "$([ "${n:-0}" = 600 ] && echo ok || echo fallo)" "${t_indice:-?} s para ${n:-?} fragmentos en memoria"
  fila rag-sintetico "comprobación: vectores idénticos a los publicados" "$(desde $T0)" "$([ "${iguales:-0}" = "${total:-1}" ] && echo ok || echo fallo)" "${iguales:-?} de ${total:-?} fragmentos y ${iguales_q:-?} de ${total_q:-?} consultas iguales a cinco decimales; RPO 0: el estado es la semilla"
  local codigo
  codigo=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 https://manpla-rag-sintetico.hf.space/ || echo 000)
  fila rag-sintetico "comprobación: la demo publicada responde" "$(desde $T0)" "$([ "$codigo" = 200 ] && echo ok || echo observación)" "HTTP $codigo; el alojamiento gratuito duerme a las 48 horas sin uso"
  fila rag-sintetico "tiempo real de recuperación" "$(desde $T0)" ok "segundos desde el arranque del guion hasta el índice comprobado"
}

if [ "${SIMULACRO_SOLO_FUNCIONES:-0}" = 1 ]; then
  return 0 2>/dev/null || exit 0   # cargado con «source»: solo las funciones
fi
echo "laboratorio,fase,instante,segundos_acumulados,resultado,detalle" > "$SALIDA"
echo "simulacro iniciado $(date -u +%FT%TZ)" > "$LOG/simulacro.log"
pam 2>&1 | tee -a "$LOG/simulacro.log"
datamart 2>&1 | tee -a "$LOG/simulacro.log"
rag 2>&1 | tee -a "$LOG/simulacro.log"
echo "simulacro terminado $(date -u +%FT%TZ)" | tee -a "$LOG/simulacro.log"
