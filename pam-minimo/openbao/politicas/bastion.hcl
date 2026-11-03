# Lo único que el bastión puede pedir a la bóveda: un certificado SSH para la
# cuenta «operador» (un principal, TTL del rol) y la contraseña con la que
# entra en la base de datos. Ni credenciales dinámicas, ni otras rutas.
path "ssh-ca/sign/operador" {
  capabilities = ["update"]
}

path "secret/data/bastion/salarios" {
  capabilities = ["read"]
}
