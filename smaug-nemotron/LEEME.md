# Leer un modelo de pesos abiertos antes de desplegarlo

Medición que acompaña a la monografía «Qué podemos saber de un modelo de pesos
abiertos antes de desplegarlo». Tiene dos partes.

**La lectura sin ejecutar** (`generar.py`, sin GPU): Smaug-Nemotron-3.5 frente
a su base de NVIDIA, leídos por rangos de bytes sobre los `safetensors` con las
revisiones fijadas; el historial de la ficha del derivado; el error típico de
cada mejora anunciada; el código remoto frente a dos revisiones de la base; el
mismo censo y el mismo rango sobre dos derivados hechos para rechazar menos; y
un inventario de pares base-derivado del Hub.

**La evaluación del comportamiento** (`conducta.py`, con GPU): cinco modelos de
la familia Qwen ante las 450 peticiones de XSTest, clasificados con WildGuard,
con WildGuard también como filtro de entrada, y una revisión a mano de dos
muestras de 60 respuestas.

## Procedencia y licencia

- La API pública y los ficheros de Hugging Face de los repositorios citados,
  con la revisión de cada uno en `ficheros.csv`, `inventario.csv` y
  `resumen.json`. Las cifras de evaluación de las fichas son de sus autores.
- XSTest (`Paul/XSTest`, CC BY 4.0) y WildGuard (`allenai/wildguard`,
  Apache-2.0), con su revisión en `resumen.json`.
- Las respuestas de los modelos no se publican: las de un modelo con los
  rechazos reducidos pueden contener instrucciones peligrosas. Se publican los
  recuentos y las etiquetas de la revisión a mano, sin el texto.
- El recuento mensual de modelos del Hub cuyo nombre anuncia menos rechazos
  está en `hub_sin_rechazos_mes.csv`; la lista de identificadores la rehace el
  generador y no se publica.

## Reproducir

```bash
uv sync --frozen --group generadores
uv run python smaug-nemotron/generar.py                    # lectura, ~1 h
uv run python smaug-nemotron/conducta.py generar --modelo qwen38 --salida DIR
uv run python smaug-nemotron/conducta.py clasificar --salida DIR
uv run python smaug-nemotron/conducta.py resumir --salida DIR
```

La lectura no necesita GPU ni credenciales. La evaluación necesita 96 GB de
GPU para los modelos de 27.000 millones de parámetros en BF16 y unos 16 GB para
los pequeños y para WildGuard. `reproducir.ipynb` lee los resultados ya
escritos y no ejecuta ningún modelo.

## Ficheros principales

| Fichero | Qué contiene |
|---|---|
| `censo.csv`, `censo_componentes.csv`, `censo_tipos.csv`, `tensores.csv` | el censo de los tensores por ventanas, por tensor y por bloque |
| `rango.csv` | valores singulares y energía acumulada de los dos tensores leídos enteros, frente a la diferencia barajada |
| `ficha_versiones.csv`, `ficha_base_terminal.csv`, `commits.csv` | las cifras de cada versión de las fichas |
| `ruido.csv` | error típico y z de cada mejora, sin emparejar y con correlación 0,8 |
| `codigo.csv`, `ficheros.csv` | el código remoto y los ficheros frente a la base |
| `contraste_*.csv` | censo, papel en el flujo residual y rango de Heretic y Smaug-Uncensored |
| `derivados_base.csv`, `hub_sin_rechazos_mes.csv`, `rechazos_declarados.csv`, `inventario.csv` | el árbol de la base, el recuento del Hub y el inventario de pares |
| `conducta_resumen.csv`, `conducta_pares.csv`, `conducta_recuentos.csv` | proporciones con su intervalo de Wilson, contrastes emparejados (Newcombe, McNemar, Holm) y recuentos por tipo de petición |
| `conducta_repeticion.csv` | la repetición de la pareja pequeña en otro entorno de cálculo |
| `conducta_revision.csv` | las etiquetas de la revisión a mano de dos muestras de 60 respuestas, frente a WildGuard |
| `resumen.json` | lo anterior resumido, con fechas, revisiones y huellas del código |
