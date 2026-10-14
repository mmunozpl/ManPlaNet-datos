# Modelos de decisión tipada como guardarraíles: el ataque del canal de opciones

Réplica del artículo arXiv 2610.12292 v1 (Azizi, Baghaei Potraghloo y Pedram,
«One Word Opens the Gate: The Option-Channel Attack on Typed Decision Models as
Agent Guardrails», 8 de octubre de 2026) con su propio código, bajo licencia MIT
(`github.com/ArminAzizi98/option-channel-attack`, commit
`7ca2f8382f0ec50590b38e3a766061506a52af93`), extendida a tres modelos publicados
la semana del 5 de octubre que el artículo no evaluó. GuardBench, las seis
políticas, las líneas de registro inyectadas y el vocabulario de 198 etiquetas
se importan del repositorio sin reescribirlos. GuardBench es sintético: no
interviene ningún dato de ninguna persona.

- Tarea: decidir si una llamada de herramienta propuesta por un agente se
  permite o se bloquea según una política escrita; dos opciones con su nombre y
  su definición, decisión por la mayor probabilidad
- Condiciones: nombres originales (`block`, `allow`); opción permisiva renombrada
  `escalate` o `remediate`; nombres intercambiados; 1, 3 o 6 líneas de registro
  y 1 o 3 notas de aprobación sin verificar en el tramo que controla el atacante
- Tamaño: 300 llamadas por política (150 que deben bloquearse y 150 que deben
  permitirse) en las nueve condiciones, 1.800 por modelo y condición; 23 pares
  de etiquetas con 300; barrido de 198 etiquetas con 200
- Fallo abierto: permitir una llamada que la política manda bloquear. Fallo
  cerrado: bloquear una que la política permite
- Semillas: 0 (random, numpy, torch); GuardBench con crc32 de (política, 0);
  inferencia sin muestreo
- Entorno: Python 3.12.12, torch 2.14.1 (CUDA 13.0), transformers 5.19.0,
  laya 0.4.6; RTX 5090 de 32 GB; versiones exactas en `requirements-gpu.txt`
- Ejecutado: 13-10-2026, unas 3,9 horas de GPU

## Modelos

| Modelo | Revisión | Parámetros | Licencia |
|---|---|---|---|
| convaiinnovations/laya-typed-decisions (LAYA-TD, referencia del artículo) | `e929ae5c` | 421 M | Apache-2.0 |
| LiquidAI/d1-omni-600M | `02b55d70` | 587 M | LFM Open License v1.0 |
| LiquidAI/d1-3B | `051bcc46` | 3,12 B | LFM Open License v1.0 |
| inclusionAI/LemonDecider | `6930d153` | 4,54 B | Apache-2.0 |

No entraron por memoria (más de unos 15 GB): perplexity-ai/pplx-decider-v1.1-27b,
vllm-sr/d3, Cloudflare/clef-omni y autotrust/JEV-35B (23,3 GiB en NVFP4).

## Validación contra el artículo (LAYA-TD)

| Cifra | Artículo | Esta réplica |
|---|---|---|
| unauth_irrev, nombres originales: acierto / fallo abierto | 87,3 % / 0 % | 87,3 % / 0 % |
| unauth_irrev, 6 líneas de registro: bloqueos correctos que pasan a permitidos | 63,3 % | 62,0 % (93 de 150) |
| unauth_irrev, permisiva renombrada `escalate` | 0 → 100 % | 0 → 100 % |
| barrido de 198 etiquetas, media de seis políticas: original / mejor | 60,0 / 98,2 % | 59,7 / 98,2 % |

Probabilidad por ítem frente a la caché del repositorio: diferencia máxima
0,0143; acuerdo de decisión del 99 al 100 % por política. El residuo es ruido
numérico de bf16 en otro hardware.

## Resultado (1.800 llamadas por celda; acierto / fallo abierto / fallo cerrado, %)

| Condición | LAYA-TD | d1-omni-600M | d1-3B | LemonDecider |
|---|---|---|---|---|
| nombres originales | 67,8 / 59,8 / 4,7 | 67,0 / 2,8 / 63,2 | 93,4 / 6,1 / 7,1 | 96,0 / 2,9 / 5,1 |
| permisiva `escalate` | 51,9 / 95,6 / 0,6 | 73,8 / 10,6 / 41,9 | 93,4 / 6,1 / 7,1 | 96,7 / 2,4 / 4,1 |
| 6 líneas de registro | 58,9 / 82,1 / 0,0 | 73,8 / 15,8 / 36,7 | 91,0 / 6,3 / 11,7 | 95,9 / 2,9 / 5,2 |

En d1-3B la etiqueta no llega a la red: su biblioteca escribe solo «A
<definición>» y «B <definición>» (`entrada_etiqueta.csv`, `ejemplos_entrada.txt`),
y las probabilidades son idénticas con cualquier nombre.

## La ola en Hugging Face (`ola.py`)

Repositorios con alguna de las etiquetas `decision-model`, `system-one`, `jev`,
`typed-decision` o `decider`, por semana de creación, consultados el 13-10-2026:
2.291 únicos; 4 antes del 14 de septiembre; 130, 729, 602 y 665 en las semanas
del 14, 21 y 28 de septiembre y del 5 de octubre; 161 en la del 12 hasta el día
de la consulta.

## Ficheros

- `generar.py`: el experimento completo (necesita GPU); `ola.py`: el recuento de
  Hugging Face (sin GPU)
- `resumen_condiciones.csv`, `resumen_politicas.csv`, `resumen_candidatos.csv`,
  `resumen_barrido.csv`, `presupuesto_barrido.csv`, `estratos_barrido.csv`:
  acierto, fallo abierto, fallo cerrado, ECE, `asr_open` y abstención por
  modelo y condición
- `items_condiciones.csv.gz`, `items_candidatos.csv.gz`, `items_barrido.csv.gz`:
  una fila por llamada, con la verdad, la opción elegida y la probabilidad de
  cada opción
- `validacion.csv`: cada cifra del artículo frente a la réplica y a la caché
- `entrada_etiqueta.csv`, `ejemplos_entrada.txt`: si el nombre de la opción
  llega al modelo, con la entrada exacta
- `ola_repos.csv`, `ola_semanal.csv`; `entorno.json`, `tiempos.csv`
