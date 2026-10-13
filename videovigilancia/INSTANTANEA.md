# Videovigilancia con capacidades de IA en los pliegos de contratación pública

Licitaciones de videovigilancia publicadas en la Plataforma de Contratación del
Sector Público entre enero de 2024 y el 12 de octubre de 2026, con la búsqueda
de reconocimiento facial, búsqueda por apariencia, analítica de vídeo o IA y
lectura de matrículas en dos niveles: el título y el resumen del anuncio (nivel
A) y el texto completo del pliego de prescripciones técnicas (nivel B). Los
pliegos son documentos públicos; de ellos solo se guardan el nombre del órgano
de contratación, los datos del expediente y frases técnicas literales. No se
extrae ningún dato personal.

- Fuente: datos abiertos de sindicación de la Plataforma de Contratación,
  feed 643 (perfiles alojados en la Plataforma, 34 ficheros mensuales de
  2024-01 a 2026-10) y feed 1044 (plataformas autonómicas agregadas, 3 anuales)
- Volumen: 37 ficheros, 5.913 ATOM, 2.614.734 entradas y 333.273 bajas;
  701.801 expedientes únicos (clave: expediente y órgano; se queda la última
  versión por `atom:updated`)
- Selección: CPV de videovigilancia (32323500, 35125300, 32234000, 32235000,
  32231000, 92222000) o palabras del título, el objeto y los lotes en
  castellano, catalán, gallego y euskera; 2.117 candidatos, 371 descartados con
  su motivo en `salidas/excluidas.csv`, 1.746 seleccionados
- Pliegos: 1.451 con texto extraído; 222 sin URL de pliego, 33 con error 500,
  32 escaneados sin capa de texto y 8 con otros fallos: 3 PDF dañados, 2
  formatos desconocidos, 2 páginas HTML en lugar del documento y 1 tiempo
  agotado (`salidas/estado_pliegos.csv`)
- Recuento: menciones afirmativas; una mención dentro de una cláusula que
  excluye la función no cuenta
- Consultado: 13-10-2026; identificación `ManPlaNet-medicion/1.0`, una petición
  por segundo a los pliegos

## Resultado (nivel B sobre 1.451 pliegos con texto)

| Capacidad | Nivel A (título, 1.746) | Nivel B (pliego, 1.451) |
|---|---|---|
| reconocimiento facial | 0 | 124 (8,5 %) |
| búsqueda por apariencia | 0 | 74 (5,1 %) |
| analítica de vídeo o IA | 29 (1,7 %) | 601 (41,4 %) |
| lectura de matrículas | 130 (7,4 %) | 626 (43,1 %) |

Ayuntamientos y demás entidades locales (pliegos con texto):

| Año | Reconocimiento facial | Búsqueda por apariencia |
|---|---|---|
| 2024 | 14 de 227 (6,2 %) | 13 de 227 (5,7 %) |
| 2025 | 34 de 260 (13,1 %) | 27 de 260 (10,4 %) |
| 2026 | 31 de 223 (13,9 %) | 20 de 223 (9,0 %) |

Dónde aparece el reconocimiento facial en los 124 pliegos (`lista_rostros.py`):
26 lo unen a una lista de vigilancia o a una base de rostros, 19 de ellos de
entidades locales; en 40 todas las menciones están en líneas de ficha de
producto (canales, grabador, resolución, códecs); en 4, junto a control de
accesos; 54 en el resto de menciones.

## Ficheros

- `generar.py`: descarga, análisis de los ATOM, selección, descarga de pliegos,
  extracción de texto y recuentos; `lista_rostros.py`: la clasificación de las
  menciones de reconocimiento facial (necesita la caché de pliegos de
  `generar.py`)
- `salidas/licitaciones_videovigilancia.csv`: una fila por expediente, con
  órgano, tipo de órgano, CPV, importes, URL del pliego, marcas de nivel A y B,
  términos encontrados y la frase literal
- `salidas/conteos_*.csv`: por mes, año, tipo de órgano y capacidad
- `salidas/facial_contra_lista.csv`, `salidas/ejemplos_facial_apariencia.csv`,
  `salidas/excluidas.csv`, `salidas/estado_pliegos.csv`, `salidas/volumenes.json`
