# Parámetros activos por token en los cien modelos en tendencia del Hub

Recuento tensor a tensor sobre las cabeceras de los ficheros `.safetensors`
(petición de rango: los primeros bytes de cada shard llevan la lista de
tensores con su forma), sin descargar pesos. No interviene ningún dato de
ninguna persona.

- Lista: `https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=100`
- Extraído: 2026-09-15

## Campos de `activos.csv`

| Columna | Origen |
|---|---|
| `puesto`, `modelo`, `pipeline`, `creado`, `likes` | la lista en tendencia del Hub |
| `arquitectura` | `architectures[0]` del `config.json` |
| `tipo` | `moe` si hay tensores de expertos enrutados; `denso` si no; `cuantizado` si los pesos van a 4 bits o empaquetados (el recuento por tensor no vale y se deja el total del Hub); `gguf` si el repositorio es una copia en ese formato; `sin safetensors` si no hay pesos en ese formato en la raíz; `sin acceso` si exige aceptar condiciones; `incompleto` si algún shard no se pudo leer |
| `params_total_hub` | el total que publica la API del Hub para el repositorio |
| `params_elementos` | en los cuantizados, elementos contados en las cabeceras (no parámetros) |
| `params_total` | suma de elementos de todos los tensores |
| `params_expertos` | elementos de los expertos enrutados (`…experts.N.…` o fusionados `…experts.peso`) |
| `params_tablas` | tablas de consulta: embedding de entrada y memorias de n-gramas (PLE, Engram) |
| `capas_moe`, `expertos_por_capa`, `activos_por_token` | capas con expertos, expertos por capa y el `k` del config |
| `params_activos` | total − expertos no usados por token − tablas; expertos compartidos, atención, MLP densos y cabeza de salida cuentan siempre |
| `params_activos_con_tablas` | lo mismo sin descontar las tablas, que es la convención de muchas fichas |
| `fraccion_activa` | `params_activos / params_total` |
| `declarado_total_B`, `declarado_activo_B` | lo que el nombre del repositorio dice (`35B-A3B`) |
| `shards`, `tensores` | cuántos ficheros y tensores se leyeron |
