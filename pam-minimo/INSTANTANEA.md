# Instantánea del laboratorio PAM mínimo

Medido el 2026-11-03. OpenBao 2.7.2, Warpgate 0.30.2, PostgreSQL 17.11, Debian bookworm con OpenSSH como objetivo, todo en Docker Compose, en una sola máquina. Dato protegido: la tabla 28193 del INE (ganancia media anual por comunidad, ocupación, sexo y año, 3.672 filas), sin ninguna persona.

## Pruebas

- 36 de 36 pruebas con el resultado esperado.
- **bastión SSH**: contraseña + TOTP, orden en el servidor → entra y ejecuta (1165 ms); contraseña correcta, TOTP erróneo → rechazado (1082 ms); contraseña correcta, sin TOTP → rechazado (1074 ms); protección contra fuerza bruta tras los dos fallos → HTTP 200 (0 ms); tres fallos más (cinco en total): IP bloqueada → 1 bloqueada(s) (3217 ms); contraseña y TOTP correctos con la IP bloqueada → rechazado (2033 ms); desbloqueo por el administrador (API) → 0 bloqueada(s) (0 ms).
- **bastión PostgreSQL**: entrar por el bastión con la contraseña de la usuaria → lee (60 ms); contraseña incorrecta → rechazado (35 ms); escribir a través del bastión → rechazado (39 ms).
- **certificados SSH**: firmar para «root» → HTTP 400 (3 ms); firmar con TTL de 1 h (máximo del rol: 15 min) → HTTP 400 (2 ms); firmar para «operador», TTL 2m → certificado (2 ms); entrar en el servidor con el certificado → entra (111 ms); entrar con una clave sin certificado → rechazado (63 ms); entrar con el certificado caducado → rechazado (71 ms); orden en la sesión abierta antes de caducar → sigue viva (4 ms).
- **credenciales dinámicas**: pedir credenciales de lectura → TTL 180 s (17 ms); leer la tabla con ellas → lee (6 ms); escribir en la tabla con ellas → rechazado (6 ms); revocar la concesión antes de tiempo → HTTP 204 (25 ms); leer tras la revocación → rechazado (5 ms); segunda credencial, leer → lee (6 ms); leer con la credencial caducada → rechazado (6 ms); consulta en la conexión abierta antes del TTL → sin privilegios (1 ms).
- **límites de las políticas**: entrar como el bastión (AppRole) → bastion, default (0 ms); bastión: GET database/creds/lectura → HTTP 403 (2 ms); bastión: GET secret/data/bastion/salarios → HTTP 200 (2 ms); bastión: GET sys/policies/acl/bastion → HTTP 403 (2 ms); bastión: POST ssh-ca/sign/operador → HTTP 400 (2 ms); operadora: GET secret/data/bastion/salarios → HTTP 403 (2 ms); operadora: GET sys/policies/acl/operador → HTTP 403 (2 ms); operadora: GET database/config/salarios → HTTP 403 (2 ms).
- **rotación**: contraseña original del administrador de la base de datos → rechazada (4 ms).
- **grabaciones**: grabaciones en disco del bastión → 1 grabaciones (0 ms); sesiones registradas por el bastión → HTTP 200, 10 sesiones, 3 autenticadas (0 ms).

## Certificados SSH

- Certificado del camino directo: ssh-ed25519-cert-v01@openssh.com, principal «operador», key ID «medidor:ana», válido 150 s, firmado en 2 ms.

## Credenciales dinámicas

- revocada: TTL 180 s, emitida en 17 ms.
- caducada: TTL 180 s, emitida en 10 ms.

## Grabaciones y sesiones

- 1 grabaciones, 607 octetos en total; 1 contienen la salida de la orden en claro (base64 por trozos, con su instante).
- 10 sesiones en el registro del bastión, 3 de ellas autenticadas.

## Lo que vio el servidor SSH

- 3 acceso aceptado, 2 acceso rechazado, 2 cerrada sin autenticar, 4 certificado aceptado por la CA, 1 certificado inválido.
- Key ID de los certificados aceptados: medidor:ana, warpgate:ana:38881ba2-eccb-4982-a8bc-3546561edd2b.

## Auditoría de la bóveda

- 40 respuestas registradas, 5 con error, en 31 combinaciones de quién, operación y ruta.

## Auditoría del bastión

- 1 AccessRoleGranted HTTP, 2 CredentialCreated HTTP, 1 UserCreated HTTP, 2 SecretResolved PostgreSQL (éxito sí), 2 TargetSessionEnded PostgreSQL, 2 TargetSessionStarted PostgreSQL, 2 UserAuthenticated PostgreSQL, 1 UserAuthenticationFailed PostgreSQL, 1 SshCertificateIssued SSH (éxito sí), 1 TargetSessionEnded SSH, 1 TargetSessionStarted SSH, 1 UserAuthenticated SSH, 5 UserAuthenticationFailed SSH.

## Esfuerzo

- `init` completo en 22 s: secretos y TLS a los 0 s; imágenes a los 2 s; bóveda iniciada a los 10 s; bóveda configurada a los 14 s; servidor SSH a los 15 s; bastión arrancado a los 21 s; bastión configurado a los 22 s; listo a los 22 s.
- 368 líneas de configuración y guion en 10 ficheros, sin comentarios ni líneas en blanco.
- Imágenes: openbao/openbao:2.7.2 192MB; postgres:17.11 454MB; ghcr.io/warp-tech/warpgate:0.30.2 137MB; pam-minimo-objetivo-ssh:latest 99.7MB; pam-minimo-medidor:latest 183MB.
- Memoria en reposo: warpgate-1 130MiB; objetivo-ssh-1 2.605MiB; postgres-1 31.65MiB; openbao-1 35.36MiB.
