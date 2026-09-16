# El evaluador dentro del bucle: dos experimentos sintéticos

Simulaciones con `numpy` 2.3.3, semilla 20260917, generadas el 2026-09-17. No interviene ningún dato de ninguna persona: las etiquetas, los envíos y las tiradas son aleatorios.

## `semillas.csv` — el mejor de k

Un modelo con exactitud real `p` evaluado `k` veces sobre `n` preguntas; cada evaluación es una binomial(n, p)/n y se publica la mejor de las k. 20000 repeticiones por celda.

| Columna | Origen |
|---|---|
| `n`, `p`, `k` | tamaño del banco, exactitud real, evaluaciones entre las que se elige |
| `sigma_puntos` | 100·sqrt(p(1-p)/n): la desviación de una evaluación, en puntos |
| `inflacion_esperada_puntos` | sigma por la esperanza del máximo de k normales estándar (integración numérica) |
| `inflacion_simulada_puntos` | media de (mejor de k − p), en puntos, sobre las repeticiones |
| `percentil_90_puntos` | percentil 90 de la misma diferencia |

## `asalto-serie.csv` y `asalto-por-tamano.csv` — el asaltante sin modelo

Marcador con `n` ejemplos de respuesta binaria equilibrada; el asaltante envía 2000 vectores al azar, lee lo que el evaluador publica y combina por mayoría los que le convienen (Blum y Hardt, 2015). Cuatro evaluadores sobre la misma secuencia de envíos; cada columna es la cifra que ese evaluador publica tras cada consulta, y el asaltante solo ve esa cifra:

| Columna | Evaluador |
|---|---|
| `ingenuo` | devuelve la puntuación exacta y publica la mejor vista; el asaltante conserva los vectores que superan el 50 % |
| `escalera` | solo publica una mejora mayor que eta=0.01, redondeada a múltiplos de eta; el asaltante conserva los vectores que la hacen subir |
| `anclado` | devuelve la exacta durante la época de 100 consultas y, al cerrarla, publica la del envío combinado sobre un conjunto de anclaje de `n` ejemplos que nunca da retroalimentación |
| `rotado` | como el anclado, pero el anclaje es la otra mitad del conjunto público y las mitades se intercambian en cada época |
| `real` | exactitud del envío combinado sobre 20000 ejemplos privados |

Media de 20 tiradas. La serie es para n=1000; la tabla por tamaño, para n en (200, 1000, 5000) a 100, 500, 1000 y 2000 consultas.
