# Cómo terminan los procedimientos de la AEPD

Resoluciones publicadas por la Agencia Española de Protección de Datos (AEPD)
en aepd.es, leídas el 15-10-2026 y clasificadas de nuevo el 20-10-2026: recuento por año de firma y tipo de
procedimiento (2008-2026) y parte dispositiva de las resoluciones de los
procedimientos sancionadores (PS) y de apercibimiento (PA) de expedientes de
2024, 2025 y 2026.

- Fuente: `www.aepd.es/informes-y-resoluciones/resoluciones` (recuentos del
  buscador) y `www.aepd.es/documento/<prefijo>-NNNNN-AAAA.pdf` (documentos)
- El buscador devolvía errores 500 y 503 o una comprobación de navegador a
  partir de su página 55; no se intentó sortearla. Las resoluciones se
  reunieron recorriendo los números de expediente en sus direcciones
  públicas, una petición cada dos segundos
- Sin datos identificativos: de cada responsable se guarda solo la clase de
  su NIF (sociedad, persona física, administración local…); el número de
  expediente permite volver a la fuente. Los PDF y sus textos se quedan en
  una caché fuera de este repositorio
- Validación (20-10-2026): muestra estratificada de 42 resoluciones, ocho
  por desenlace y las dos revocaciones, elegidas al azar con semilla fija y
  comprobadas a mano contra la parte dispositiva. La primera versión del
  clasificador fallaba en 2 desenlaces (PA archivados leídos como
  apercibimientos), 4 listas de artículos y 2 marcas de medidas; corregido
  (archivo antes que apercibimiento, «ordenar el archivo» no es medida,
  artículos con «6.1.», «13 RGPD» y listas, y fuera los poderes 58.1.a) y
  58.2.d)), cambiaron 4 desenlaces, 22 marcas y 122 listas de artículos en
  las 780, y las 42 coinciden en desenlace, importe y artículos. El importe
  guardado es el de la resolución (una multa de 500 € con 400 € ya pagados
  se guarda como 500)

## Cifras

| | |
|---|---|
| resoluciones leídas | 780 (700 PS, 78 PA y 2 revocaciones, que se excluyen) |
| PS de expedientes de 2024 | 413 de 626 números: multa 38,7 %, pago con reducción 37,0 %, declaración a administraciones 13,3 %, archivo 10,9 % |
| PS de 2024 sin administraciones | 357: el 87,4 % termina con sanción económica |
| reducciones (artículo 85 de la LPACAP) | 207 del 40 %, 81 del 20 % y 4 sin porcentaje legible |
| sanciones con importe | 526: mediana de 6.000 €; 14 de un millón o más suman el 65,6 % del total |
| propuesto frente a final | 86,1 frente a 74,3 millones de euros |
| resoluciones comunicadas al Defensor del Pueblo (artículo 77 de la LOPDGDD) | 87, 86 de ellas declaraciones de infracción sin multa |
| apercibimientos (PA) | 62, y 16 archivos |
| desfase entre firma y publicación | mediana de 80 días (205 resoluciones del buscador) |

Las cohortes de 2025 y 2026 están incompletas: muchos procedimientos siguen
abiertos y los ya publicados son los que terminan antes.

## Ficheros

- `generar.py`: las etapas `serie`, `listado`, `enumerar`, `pdfs` y
  `clasificar`
- `salidas/serie_tipos.csv`: resoluciones por año de firma y tipo
- `salidas/resoluciones.csv`: una fila por resolución, con desenlace,
  importes, reducción, artículos infringidos y clase de responsable
- `salidas/desenlaces_anuales.csv`, `salidas/importes_anuales.csv`,
  `salidas/listado.csv`, `salidas/enumeracion.csv`, `salidas/volumenes.json`
