# Un PAM mínimo con software libre: el laboratorio y su medición

Laboratorio reproducible de una gestión de accesos privilegiados (PAM) con
cuatro piezas de software libre, y las pruebas que miden qué garantiza cada
una. Todo corre en Docker Compose, en una sola máquina, con imágenes fijadas
por versión.

| Pieza | Software | Versión | Papel |
|---|---|---|---|
| bóveda | OpenBao (MPL-2.0) | 2.7.2 | autoridad de certificados SSH, credenciales dinámicas de PostgreSQL, secretos, políticas y auditoría |
| bastión | Warpgate (Apache-2.0) | 0.30.2 | entrada única con contraseña y TOTP, certificado SSH por sesión pedido a la bóveda, grabación de sesiones |
| objetivo SSH | Debian bookworm con OpenSSH | imagen propia | solo admite certificados firmados por la bóveda (`TrustedUserCAKeys`) |
| objetivo de datos | PostgreSQL | 17.11 | la tabla 28193 del INE: ganancia media anual por comunidad autónoma, ocupación, sexo y año (3.672 filas) |
| medidor | Python, paramiko, psycopg | 3.12.16, 5.1.0, 3.3.6 | ejecuta las pruebas desde la red interna |

La tabla que el laboratorio protege es real y pública: la 28193 de la
Encuesta Anual de Estructura Salarial del INE, descargada de su API
(`servicios.ine.es/wstempus/csv/ES/DATOS_TABLA/28193`) y guardada en
`datos/ine_28193_salarios.csv` tal como la sirve, para que `init` no dependa
de la red; `./laboratorio.sh datos` la vuelve a descargar y da su huella. En
el CSV del INE un signo «-» delante del dato marca que la muestra tiene entre
100 y 500 observaciones; `init.sql` lo guarda en la columna
`muestra_pequena`. Ningún dato de ninguna persona interviene.

## Reproducir

Requisitos: Docker con el plugin Compose, `openssl`, `jq`, `python3` y
`curl`. Unos 10 minutos de reloj y las imágenes descargadas.

```bash
./laboratorio.sh init     # levanta y configura las cuatro piezas
./laboratorio.sh medir    # ejecuta las pruebas y escribe los CSV
./laboratorio.sh limpiar  # borra contenedores, volúmenes, secretos y TLS
```

`init` genera en `secretos/` y `openbao/tls/` todo lo que no viaja con el
repositorio: contraseñas, token de administración, claves de desprecinto y
una CA de laboratorio para el TLS de la bóveda. `medir` corre el medidor
como servicio del compose y resume desde el anfitrión los registros de la
bóveda, del bastión y del servidor SSH.

## Ficheros

| Fichero | Qué es |
|---|---|
| `compose.yaml` | los cinco servicios, la red interna y los volúmenes |
| `laboratorio.sh` | `init`, `medir`, `estado`, `parar`, `limpiar` |
| `openbao/config.hcl` | configuración de la bóveda |
| `openbao/politicas/bastion.hcl` | lo único que el bastión puede pedir a la bóveda |
| `openbao/politicas/operador.hcl` | lo que puede pedir quien opera |
| `openbao/rol-ssh-operador.json` | el rol de la CA SSH: principal, TTL y extensiones |
| `objetivo-ssh/` | imagen del servidor SSH: `sshd_config` y arranque |
| `postgres/init.sql` | la tabla sintética y los roles de lectura |
| `medidor/medir.py` | las pruebas, desde la red interna |
| `medidor/registros.py` | el resumen de los registros, desde el anfitrión |

## Lo que mide

| CSV | Columnas | Contenido |
|---|---|---|
| `pruebas.csv` | instante, bloque, prueba, esperado, resultado, ok, ms, detalle | cada prueba con lo que se esperaba, lo que pasó y cuánto tardó |
| `certificados.csv` | camino, emitido, ms_firma, ttl_pedido, tipo, serie, key_id, principales, valido_desde, valido_hasta | los certificados SSH emitidos por la bóveda |
| `credenciales_bd.csv` | etiqueta, emitida, ms_emision, lease_id, ttl_s | las credenciales dinámicas de PostgreSQL |
| `grabaciones.csv` | grabacion, ficheros, octetos, contiene_la_orden, nombres | las grabaciones de sesión del bastión en disco |
| `sesiones.csv` | id, usuario, protocolo, objetivo, inicio, fin | las sesiones registradas por el bastión |
| `auditoria_openbao.csv` | quien, operacion, ruta, error, n | respuestas del diario de auditoría de la bóveda, por quién, operación y ruta |
| `sshd_accesos.csv` | tipo, usuario, key_id, detalle | lo que el servidor SSH registró de cada intento |
| `auditoria_bastion.csv` | evento, exito, n | eventos de auditoría del bastión |
| `esfuerzo.csv` | fase, segundos_acumulados | cuánto tarda cada fase de `init` |
| `configuracion.csv` | fichero, lineas | líneas de configuración y guion, sin comentarios |
| `imagenes.csv` | imagen, tamano | las imágenes y su tamaño |
| `recursos.csv` | contenedor, memoria | memoria de cada contenedor en reposo |
| `INSTANTANEA.md` | | el resumen legible de la última medición |

## Límites

- Es un laboratorio en una máquina: la bóveda es un solo nodo con su almacén
  integrado (raft), una sola clave de desprecinto, sin alta disponibilidad y
  sin bloqueo de memoria.
- El TLS de la bóveda es de una CA de laboratorio, y el bastión no comprueba
  ese certificado (`tls_skip_verify`). Fuera de aquí, un certificado de una CA
  propia distribuida o pública.
- El bastión y el servidor SSH se hablan dentro de la red del compose; el
  tráfico hacia el exterior solo pasa por el bastión, en 127.0.0.1.
- Las pruebas de caducidad esperan al TTL real (2 minutos el certificado,
  3 las credenciales); la medición entera dura unos cinco minutos.
