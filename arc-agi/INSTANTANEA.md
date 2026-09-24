# Instantánea del marcador de ARC-AGI

Cifras publicadas por ARC Prize en los JSON que alimentan su marcador
verificado. No contiene ninguna tarea del ARC-AGI.

- Fuente: https://arcprize.org/media/data/{datasets,models,providers,evaluations}.json
- Extraído: 2026-09-25
- Evaluaciones mostradas: 980
- Kaggle: cabecera de las tablas públicas de ARC Prize 2026
  (arc-prize-2026-arc-agi-3, arc-prize-2026-arc-agi-2), si el cliente está configurado

## Ficheros

| Fichero | Contenido |
|---|---|
| `marcador.csv` | una fila por evaluación mostrada: conjunto, modelo, fecha de publicación del modelo, arnés (solo ARC-AGI-3), puntuación, coste por tarea (v1, v2) o total de la pasada (v3) |
| `frontera.csv` | la mejor puntuación acumulada por fecha de publicación, por versión y arnés, en los conjuntos semiprivados; sin las entradas de competición, fechadas por su edición |
| `hueco-v2.csv` | puntuación en el conjunto público menos la del semiprivado de ARC-AGI-2, modelo a modelo |
| `kaggle-2026.csv` | diez primeros puestos de cada tabla pública de Kaggle |
| `resumen.json` | las cifras que cita el artículo |

La puntuación de ARC-AGI-3 no es un porcentaje de juegos resueltos: pondera
cada nivel por la eficiencia en acciones frente a la línea base humana —el
cociente al cuadrado, con tope en 1,15 por nivel—, pondera los niveles por su
número y promedia por juego. El conjunto semiprivado tiene 55 entornos. La
tabla pública de Kaggle no es la clasificación final del premio.
