# Certificados de conformidad con el Esquema Nacional de Seguridad

Registro público de certificados vigentes del Centro Criptológico Nacional
(CCN), leído el 15-10-2026 de los cuatro listados que sirve su portal de
gobernanza: sistemas certificados de categoría BÁSICA, MEDIA y ALTA, y
certificados contra perfiles de cumplimiento específicos (artículo 30 del Real
Decreto 311/2022).

- Fuente: `gobernanza.ccn-cert.cni.es/amparo/API/public/certificaciones/empresas/`
  con los listados `sistemascertificadosbasica`, `sistemascertificadosmedia`,
  `sistemascertificadosalta` y `requisitosesenciales`; cada página trae los
  datos en una variable `rowData` en JSON
- Fecha de la consulta: 15-10-2026
- Sin datos identificativos: de cada entidad se guarda un número interno, su
  tipo según el CCN y la clase de la letra de su NIF (sociedad, administración
  local, organismo público…); no se guardan nombre, NIF, dirección ni web. El
  alcance certificado se reduce a indicadores temáticos por palabras clave
- Los registros de la propiedad, mercantiles y de bienes muebles comparten en
  el registro un NIF de relleno (`00000000A`); se distinguen por su nombre,
  que tampoco se guarda, y se marcan con la columna `registro`

## Cifras

| | |
|---|---|
| certificados vigentes | 3.959 (2.967 por categoría y 992 por perfil) |
| por categoría | BÁSICA 74 · MEDIA 1.869 · ALTA 1.024 |
| de empresas | 2.657 certificados de 2.443 empresas |
| entidades locales distintas (los dos listados) | 159 |
| certificadoras (listados por categoría) | 27; las cuatro primeras, 64,7 %; índice de Herfindahl-Hirschman, 1.209 |
| perfiles específicos | 840 de registros; 960 firmados por el CCN y 32 por la Agencia de Ciberseguridad de Cataluña |
| vencen del 15-10-2026 al 31-12-2026 | 1.026 (232 por categoría y 794 por perfil) |
| ya vencidos y aún publicados | 38 |
| duración de dos años exactos (por categoría) | 2.841 de 2.967 |

La fecha de concesión que publica el registro no distingue altas de
renovaciones.

## Ficheros

- `generar.py`: descarga los cuatro listados y escribe `salidas/`
- `salidas/certificados.csv`: una fila por certificado, sin datos
  identificativos
- `salidas/certificadoras.csv`, `salidas/resumen.csv`,
  `salidas/vencimientos_mensuales.csv`, `salidas/volumenes.json`
