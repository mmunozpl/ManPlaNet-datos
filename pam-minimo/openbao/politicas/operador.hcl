# La persona (o el proceso) que opera: puede pedir un certificado SSH para
# «operador», unas credenciales de lectura de la base de datos que caducan
# solas, y revocar antes de tiempo solo las credenciales de ese rol.
path "ssh-ca/sign/operador" {
  capabilities = ["update"]
}

path "database/creds/lectura" {
  capabilities = ["read"]
}

path "sys/leases/revoke/database/creds/lectura/*" {
  capabilities = ["update"]
}
