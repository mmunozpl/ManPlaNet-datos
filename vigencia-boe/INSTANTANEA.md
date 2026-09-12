# Manifiesto de vigencia de los códigos electrónicos del BOE

Metadatos del catálogo, no los códigos: `manifiesto.csv` guarda, para cada
uno de los códigos electrónicos que publica la Agencia Estatal Boletín
Oficial del Estado, su nombre, su clasificación y la fecha de actualización
que el propio BOE declara. `resumen-fichas.json` añade, por código, el
resumen de su ficha de contenido. El texto de las normas no se redistribuye:
se consulta en la fuente, y cada fila trae su enlace.

- Fuente: https://www.boe.es/biblioteca_juridica/
- Códigos catalogados: 350
- Actualización: diaria, con la marca de tiempo de cada pasada en la columna
  `marca_tiempo`; la fecha de cada versión del fichero la da el historial
  de este repositorio
- Página viva que se construye sobre estos datos:
  https://manpla.net/temas/vigencia-codigos-normativos-boe/

## Campos de `manifiesto.csv`

| Columna | Origen |
|---|---|
| `codigo` | nombre del código electrónico, tal como lo publica el BOE |
| `categoria`, `bloque`, `materia` | clasificación propia en seis materias y treinta secciones, sobre la del BOE |
| `codigo_id` | identificador del código en la URL del BOE |
| `fecha_actualizacion` | la que declara el BOE en la ficha del código |
| `url_codigo`, `pdf_url`, `epub_url` | enlaces a la fuente |
| `marca_tiempo` | instante de la pasada que leyó el catálogo, en UTC |

La clasificación en materias y secciones es decisión del análisis, no del
BOE, y se declara aquí para que se pueda discutir o rehacer.

## Reutilización

Los contenidos del BOE son reutilizables en los términos de su aviso legal y
de la Ley 37/2007, citando la fuente. Este fichero es una compilación propia
de metadatos y enlaces.
