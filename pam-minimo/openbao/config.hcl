# OpenBao, configuración mínima del laboratorio: almacén integrado (raft, un
# solo nodo; OpenBao 2.x no trae el almacén «file» de Vault) y escucha con
# TLS (el bastión exige https para hablar con la bóveda). El certificado lo
# genera laboratorio.sh con una CA propia del laboratorio.
ui = true

# la imagen corre sin privilegios y no puede bloquear memoria, y el almacén
# raft pide desactivarlo; fuera de un laboratorio: swap cifrado
disable_mlock = true

storage "raft" {
  path    = "/openbao/file"
  node_id = "laboratorio"
}

listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_cert_file = "/openbao/config/tls/openbao.pem"
  tls_key_file  = "/openbao/config/tls/openbao-clave.pem"
}

api_addr     = "https://openbao:8200"
cluster_addr = "https://openbao:8201"

# el diario de auditoría se declara aquí: OpenBao 2.7 no deja activarlo por
# la API («use declarative, config-based audit device management»)
audit "file" "auditoria" {
  description = "cada petición y su respuesta, en JSON por línea"
  options {
    file_path = "/openbao/logs/auditoria.log"
  }
}
