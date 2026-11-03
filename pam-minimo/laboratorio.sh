#!/usr/bin/env bash
# Laboratorio «un PAM mínimo con software libre»: inicializa, mide y limpia.
#
#   ./laboratorio.sh init     levanta la bóveda, la base de datos, el servidor
#                             SSH y el bastión, y los configura entre sí
#   ./laboratorio.sh medir    ejecuta las pruebas (medidor/medir.py) y resume
#                             los registros; escribe los CSV y la INSTANTANEA
#   ./laboratorio.sh datos    vuelve a descargar la tabla del INE y da su huella
#   ./laboratorio.sh estado   qué corre y cómo está
#   ./laboratorio.sh parar    detiene los contenedores y conserva los datos
#   ./laboratorio.sh limpiar  borra contenedores, volúmenes, secretos y TLS
#
# Requisitos: docker con el plugin compose, openssl, jq, python3 y curl.
# Todo lo secreto (contraseñas, token, claves de desprecinto, TLS) nace en
# secretos/ y openbao/tls/, que no viajan con el repositorio.
set -euo pipefail
cd "$(dirname "$0")"
export UID GID
GID="$(id -g)"
DC="docker compose"
S=secretos
T=openbao/tls
WG=https://127.0.0.1:8888/@warpgate/admin/api
IMAGENES="openbao/openbao:2.7.2 postgres:17.11 ghcr.io/warp-tech/warpgate:0.30.2 pam-minimo-objetivo-ssh pam-minimo-medidor"

aleatorio() { openssl rand -hex 16; }
bao() { $DC exec -T -e BAO_TOKEN="${BAO_TOKEN:-}" openbao bao "$@"; }
wg() { curl -ksS --fail-with-body -H "X-Warpgate-Token: $WG_TOKEN" \
            -H 'Content-Type: application/json' "$@"; }

esperar_bao() {
  # bao status devuelve 1 si no responde, 2 sellado, 0 abierto
  local rc i
  for i in $(seq 1 60); do
    if $DC exec -T openbao bao status >/dev/null 2>&1; then rc=0; else rc=$?; fi
    [ "$rc" -ne 1 ] && return 0
    sleep 2
  done
  echo "OpenBao no responde" >&2; exit 1
}

esperar_url() {
  local i
  for i in $(seq 1 60); do
    curl -ksf "$1" >/dev/null 2>&1 && return 0
    sleep 2
  done
  echo "sin respuesta de $1" >&2; exit 1
}

fase() { echo "$1,$(( $(date +%s) - T0 ))" >> "$S/fases.csv"; }

init() {
  if [ -e "$S/openbao-init.json" ]; then
    echo "ya hay un laboratorio inicializado; ./laboratorio.sh limpiar primero" >&2
    exit 1
  fi
  T0=$(date +%s)
  mkdir -p "$S" "$T"
  : > "$S/fases.csv"

  # 1. secretos del laboratorio
  aleatorio > "$S/pg_admin.txt"
  WG_ADMIN=$(aleatorio); WG_TOKEN=$(aleatorio)
  printf 'WARPGATE_ADMIN_PASSWORD=%s\nWARPGATE_ADMIN_TOKEN=%s\n' \
         "$WG_ADMIN" "$WG_TOKEN" > "$S/warpgate.env"
  ANA_BASTION=$(aleatorio); ANA_BAO=$(aleatorio); BASTION_BD=$(aleatorio)
  ANA_TOTP=$(python3 -c 'import base64,os;print(base64.b32encode(os.urandom(20)).decode())')

  # 2. TLS de laboratorio: una CA propia y un certificado para «openbao»
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
      -keyout "$T/ca-clave.pem" -out "$T/ca.pem" -days 365 \
      -subj "/CN=CA del laboratorio PAM" 2>/dev/null
  openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
      -keyout "$T/openbao-clave.pem" -out "$T/openbao.csr" \
      -subj "/CN=openbao" 2>/dev/null
  openssl x509 -req -in "$T/openbao.csr" -CA "$T/ca.pem" \
      -CAkey "$T/ca-clave.pem" -CAcreateserial -out "$T/openbao.pem" \
      -days 365 -extfile <(printf 'subjectAltName=DNS:openbao,DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n') 2>/dev/null
  rm -f "$T/openbao.csr" "$T/ca.srl"
  # la imagen de OpenBao corre con otro usuario: clave legible, solo aquí
  chmod 644 "$T"/*.pem
  fase "secretos y TLS"

  # 3. imágenes
  $DC build objetivo-ssh medidor
  $DC pull openbao postgres warpgate
  fase "imágenes"

  # 4. bóveda: inicio, desprecinto, auditoría
  $DC up -d openbao postgres
  esperar_bao
  bao operator init -key-shares=1 -key-threshold=1 -format=json > "$S/openbao-init.json"
  export BAO_TOKEN
  BAO_TOKEN=$(jq -r .root_token "$S/openbao-init.json")
  bao operator unseal "$(jq -r '.unseal_keys_b64[0]' "$S/openbao-init.json")" > /dev/null
  # el diario de auditoría viene declarado en openbao/config.hcl
  fase "bóveda iniciada"

  # 5. autoridad de certificados SSH y rol de «operador»
  bao secrets enable -path=ssh-ca ssh
  bao write ssh-ca/config/ca generate_signing_key=true key_type=ed25519 > /dev/null
  bao write ssh-ca/roles/operador - < openbao/rol-ssh-operador.json

  # 6. políticas y formas de entrar: AppRole para el bastión, userpass para ana
  bao policy write bastion - < openbao/politicas/bastion.hcl
  bao policy write operador - < openbao/politicas/operador.hcl
  bao auth enable approle
  bao write auth/approle/role/bastion token_policies=bastion token_ttl=1h \
      token_max_ttl=24h secret_id_num_uses=0 secret_id_ttl=0 > /dev/null
  ROLE_ID=$(bao read -field=role_id auth/approle/role/bastion/role-id)
  SECRET_ID=$(bao write -f -field=secret_id auth/approle/role/bastion/secret-id)
  bao auth enable userpass
  bao write auth/userpass/users/ana password="$ANA_BAO" \
      token_policies=operador token_ttl=30m > /dev/null

  # 7. la contraseña con la que el bastión entra en la base de datos vive en
  #    el KV de la bóveda; el bastión solo guarda la referencia
  until $DC exec -T postgres pg_isready -U admin_bd -d salarios >/dev/null 2>&1; do sleep 2; done
  $DC exec -T postgres psql -U admin_bd -d salarios -qc \
      "ALTER ROLE bastion_lectura PASSWORD '$BASTION_BD';"
  bao secrets enable -path=secret -version=2 kv
  bao kv put -mount=secret bastion/salarios password="$BASTION_BD" > /dev/null

  # 8. credenciales dinámicas: la bóveda crea y destruye cuentas de lectura,
  #    y rota la contraseña del administrador para que solo ella la sepa
  bao secrets enable database
  bao write database/config/salarios plugin_name=postgresql-database-plugin \
      allowed_roles=lectura \
      connection_url="postgresql://{{username}}:{{password}}@postgres:5432/salarios?sslmode=disable" \
      username=admin_bd password="$(cat "$S/pg_admin.txt")"
  bao write database/roles/lectura db_name=salarios default_ttl=3m max_ttl=1h \
      creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}' IN ROLE lectura_salarios;"
  bao write -f database/rotate-root/salarios
  fase "bóveda configurada"

  # 9. el servidor SSH (toma la clave pública de la CA al arrancar)
  $DC up -d objetivo-ssh
  fase "servidor SSH"

  # 10. el bastión: alta desatendida y arranque
  $DC run --rm --no-deps warpgate unattended-setup --data-path /data \
      --http-port 8888 --ssh-port 2222 --postgres-port 55432 \
      --record-sessions --host-key-verification auto-accept \
      --external-host localhost --if-config-exists skip
  $DC up -d warpgate
  esperar_url "https://127.0.0.1:8888/@warpgate/api/info"
  fase "bastión arrancado"

  # 11. alta en el bastión: la bóveda como backend, un rol, dos objetivos y ana
  wg -X POST "$WG/secret-backends" -d "$(jq -n --arg r "$ROLE_ID" --arg s "$SECRET_ID" \
      '{name:"openbao", backend_type:"openbao", address:"https://openbao:8200",
        auth:{method:"AppRole", role_id:$r, secret_id:$s},
        tls_skip_verify:true, allowed_paths:["ssh-ca/sign/operador","secret/bastion/salarios"]}')" > /dev/null
  ROL=$(wg -X POST "$WG/roles" \
      -d '{"name":"operaciones","description":"quienes operan el servidor y leen la tabla de salarios"}' | jq -r .id)
  SRV=$(wg -X POST "$WG/targets" -d '{
      "name":"servidor","description":"servidor SSH: solo certificados de la bóveda",
      "options":{"kind":"Ssh","host":"objetivo-ssh","port":22,"username":"operador",
                 "allow_insecure_algos":false,
                 "auth":{"kind":"Certificate","backend":"openbao","mount":"ssh-ca","role":"operador"}},
      "ticket_requests_disabled":false,"ticket_require_approval":false,"require_approval":false}' | jq -r .id)
  BD=$(wg -X POST "$WG/targets" -d '{
      "name":"salarios","description":"PostgreSQL con la tabla de salarios del INE: la contraseña vive en la bóveda",
      "options":{"kind":"Postgres","host":"postgres","port":5432,"username":"bastion_lectura",
                 "auth":{"kind":"Password","password":"secret://openbao/secret/bastion/salarios#password"},
                 "tls":{"mode":"Disabled","verify":false},"default_database_name":"salarios","protocol_version":"3.0"},
      "ticket_requests_disabled":false,"ticket_require_approval":false,"require_approval":false}' | jq -r .id)
  wg -X POST "$WG/targets/$SRV/roles/$ROL" > /dev/null
  wg -X POST "$WG/targets/$BD/roles/$ROL" > /dev/null
  ANA=$(wg -X POST "$WG/users" -d '{"username":"ana","description":"operadora de sistemas"}' | jq -r .id)
  wg -X POST "$WG/users/$ANA/credentials/passwords" \
      -d "$(jq -n --arg p "$ANA_BASTION" '{password:$p}')" > /dev/null
  wg -X POST "$WG/users/$ANA/credentials/otp" \
      -d "$(python3 -c "import base64,json;print(json.dumps({'secret_key': list(base64.b32decode('$ANA_TOTP'))}))")" > /dev/null
  wg -X POST "$WG/users/$ANA/roles/$ROL" -d '{}' > /dev/null
  # la política de credenciales se fija después de las credenciales: SSH y
  # consola con contraseña y TOTP, PostgreSQL con contraseña
  wg -X PUT "$WG/users/$ANA" -d '{"username":"ana","description":"operadora de sistemas",
      "credential_policy":{"ssh":["Password","Totp"],"http":["Password","Totp"],"postgres":["Password"]}}' > /dev/null
  fase "bastión configurado"

  # 12. lo que necesita el medidor
  cat > "$S/medidor.env" <<EOF
BAO_ADDR=https://openbao:8200
BAO_CACERT=/etc/ssl/lab/ca.pem
WARPGATE_URL=https://warpgate:8888
WARPGATE_ADMIN_TOKEN=$WG_TOKEN
ANA_USUARIO=ana
ANA_CLAVE_BASTION=$ANA_BASTION
ANA_TOTP_B32=$ANA_TOTP
ANA_CLAVE_BAO=$ANA_BAO
BASTION_ROLE_ID=$ROLE_ID
BASTION_SECRET_ID=$SECRET_ID
PG_ADMIN_ORIGINAL=$(cat "$S/pg_admin.txt")
TTL_CERT_DIRECTO=2m
EOF
  chmod 600 "$S"/*
  fase "listo"
  echo "laboratorio listo en $(( $(date +%s) - T0 )) s"
  echo "consola del bastión: https://127.0.0.1:8888 (admin, contraseña en $S/warpgate.env)"
  echo "SSH por el bastión:  ssh -p 2223 ana:servidor@127.0.0.1 (contraseña y TOTP en $S/medidor.env)"
}

medir() {
  [ -e "$S/medidor.env" ] || { echo "primero ./laboratorio.sh init" >&2; exit 1; }
  $DC run --build --rm medidor
  mkdir -p "$S/registros"
  $DC exec -T openbao cat /openbao/logs/auditoria.log > "$S/registros/openbao-auditoria.jsonl"
  $DC logs --no-color --no-log-prefix objetivo-ssh > "$S/registros/sshd.log" 2>&1
  $DC logs --no-color --no-log-prefix warpgate > "$S/registros/warpgate.log" 2>&1
  docker stats --no-stream --format '{{.Name}},{{.MemUsage}}' > "$S/registros/recursos.txt"
  : > "$S/registros/imagenes.txt"
  for img in $IMAGENES; do
    docker images --format '{{.Repository}}:{{.Tag}},{{.Size}}' "$img" >> "$S/registros/imagenes.txt"
  done
  python3 medidor/registros.py "$S/registros" "$S/fases.csv" .
}

datos() {
  # la tabla 28193 del INE (EAES: ganancia media anual por comunidad,
  # ocupación, sexo y año), tal como la sirve su API; se versiona con el
  # laboratorio para que init no dependa de la red
  curl -sSf -m 120 -o datos/ine_28193_salarios.csv \
      "https://servicios.ine.es/wstempus/csv/ES/DATOS_TABLA/28193"
  echo "descargada $(date -u +%Y-%m-%d) · $(wc -l < datos/ine_28193_salarios.csv) líneas · sha256 $(sha256sum datos/ine_28193_salarios.csv | cut -c1-64)"
}

estado() { $DC ps; }
parar() { $DC down; }
limpiar() {
  $DC --profile medir down -v --remove-orphans
  rm -rf "$S" "$T"
  echo "laboratorio borrado"
}

case "${1:-}" in
  init|medir|datos|estado|parar|limpiar) "$1" ;;
  *) sed -n '2,14p' "$0"; exit 1 ;;
esac
