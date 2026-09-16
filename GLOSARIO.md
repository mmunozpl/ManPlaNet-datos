# Glosario · Glossary

Los ficheros y sus columnas están en español. Esta tabla fija la forma
inglesa de cada término, y es la que usa `README.md`.

The files and their columns are in Spanish. This table fixes the English
form of each term, and it is the one `README.md` uses.

| Español | English | Dónde · Where |
|---|---|---|
| medición | measurement | todo el repositorio · whole repository |
| instantánea | snapshot | `INSTANTANEA.md`, todas las carpetas · all folders |
| ficha de procedencia | provenance record | `INSTANTANEA.md` |
| recuento agregado | aggregate count | `kev`, `agi-tendencias` |
| guion | script | `generar.py` |
| alta | addition (to the catalogue) | `kev/altas.csv` |
| `fecha`, `dia_semana`, `altas` | date, weekday, additions | `kev/altas.csv` |
| escaparate | shop window (the Hub's trending list) | `hf-tendencia` |
| `puesto`, `descargas`, `likes` | rank, downloads, likes | `hf-tendencia/tendencia.csv` |
| `creado`, `edad_dias` | created, age in days | `hf-tendencia/tendencia.csv` |
| `biblioteca`, `ficheros` | library, file count | `hf-tendencia/tendencia.csv` |
| `con_fichero_consulta` | has a query file (one the Hub counts downloads by) | `hf-tendencia/tendencia.csv` |
| `safetensors_raiz` | `.safetensors` at the top level | `hf-tendencia/tendencia.csv` |
| cuota | share | `agi-tendencias` |
| `termino`, `consulta`, `anio` | term, query, year | `agi-tendencias/cuotas.csv` |
| `recuento`, `denominador`, `por_diez_mil` | count, denominator, per ten thousand | `agi-tendencias/cuotas.csv` |
| `anio_parcial` | partial year | `agi-tendencias/cuotas.csv` |
| comprobaciones | checks | `agi-tendencias/comprobaciones.csv` |
| máscara, parche, rejilla | mask, patch, grid | `ijepa` |
| contexto, objetivo | context, target | `ijepa` |
| `fila`, `columna`, `veces_objetivo`, `veces_contexto` | row, column, times as target, times as context | `ijepa/cobertura.csv` |
| `contexto_bruto`, `contexto_truncado` | raw context, truncated context | `ijepa/muestras.csv` |
| lote, semilla | batch, seed | `ijepa/resumen.json` |
| fragmento, consulta | chunk, query | `rag-sintetico` |
| ámbito, `acl` | scope, ACL (access-control list) | `rag-sintetico/corpus.csv` |
| `v0`…`v63`, `q0`…`q63` | embedding coordinates of the chunk, of the query | `rag-sintetico/corpus.csv`, `consultas.csv` |
| `post_utiles`, `post_expuestos`, `post_vacia` | useful, exposed, empty — filter after retrieval | `rag-sintetico/consultas.csv` |
| `pre_utiles`, `pre_expuestos` | useful, exposed — filter before retrieval | `rag-sintetico/consultas.csv` |
| generación | generation | `deepseek-kv` |
| razón de compresión | compression ratio | `deepseek-kv` |
| `capas`, `capas_kv` | layers, layers with global cache | `deepseek-kv/generaciones.csv` |
| `entradas_por_token` | cache entries per token | `deepseek-kv/generaciones.csv` |
| `latente`, `bits` | latent width, storage bits | `deepseek-kv/generaciones.csv` |
| `bytes_token_ficha` | bytes per token, from the model card | `deepseek-kv/generaciones.csv` |
| `bytes_entrada_implicitos`, `bytes_entrada_declarados` | implied bytes per entry, documented bytes per entry | `deepseek-kv/generaciones.csv` |
| `residuo_por_entrada`, `indexador` | unaccounted bytes per entry, indexer key bytes | `deepseek-kv/generaciones.csv` |
| `contexto_1M_MiB` | global cache for one million tokens, in MiB | `deepseek-kv/generaciones.csv` |
| explotada, marca (de explotación) | exploited, (exploitation) flag | `euvd-kev` |
| alta, fecha límite, ventana | addition, due date, window | `euvd-kev` |
| `alta_eu_kev`, `alta_cisa_kev`, `eu_menos_cisa_dias` | EU KEV addition date, CISA KEV addition date, EU minus CISA in days | `euvd-kev/eu-kev.csv` |
| `asignador`, `proveedor`, `honeypot` | CVE assigner, vendor, has honeypot observation | `euvd-kev/eu-kev.csv` |
| `3 días` … `6 meses`, `otros` | deadline window bands | `euvd-kev/ventanas-kev.csv` |
| `anios_desde_el_cve` | years since the CVE identifier | `euvd-kev/antiguedad-kev.csv` |
| `cisa_kev`, `eu_kev` (por mes) | monthly additions to each list | `euvd-kev/altas-mensuales.csv` |
| triaje forense | forensic triage | `euvd-kev/resumen.json` |
| parámetros activos por token, guardados | active parameters per token, stored | `hf-activos` |
| expertos enrutados, compartidos | routed experts, shared experts | `hf-activos` |
| tablas de consulta | lookup tables (input embedding, n-gram memories) | `hf-activos/activos.csv` |
| `tipo` (moe, denso, cuantizado, gguf, sin safetensors, sin acceso, incompleto) | kind (MoE, dense, quantised, GGUF, no safetensors, gated, incomplete) | `hf-activos/activos.csv` |
| `params_total`, `params_activos`, `fraccion_activa` | total, active, active fraction | `hf-activos/activos.csv` |
| `params_expertos`, `params_tablas`, `params_activos_con_tablas` | expert, table and active-including-tables parameters | `hf-activos/activos.csv` |
| `capas_moe`, `expertos_por_capa`, `activos_por_token` | MoE layers, experts per layer, active experts per token (k) | `hf-activos/activos.csv` |
| `declarado_total_B`, `declarado_activo_B` | declared in the repository name, in billions | `hf-activos/activos.csv` |
| `shards`, `tensores`, `params_total_hub`, `params_elementos` | shards read, tensors, the Hub's total, elements (quantised) | `hf-activos/activos.csv` |
| ficha completa (estados `Analyzed` y `Modified` del NVD) | complete record (NVD statuses `Analyzed` and `Modified`) | `nvd-fichas` |
| aplazado (`Deferred`) | deferred | `nvd-fichas` |
| `cve`, `publicado`, `estado`, `en_kev`, `kev_alta` | CVE id, published, NVD status, in the KEV catalogue, KEV addition date | `nvd-fichas/cve-estados.csv.gz` |
| `publicados`, `ficha_completa`, `aplazados`, `recibidos`, `en_espera`, `en_analisis`, `explotados` | published, complete record, deferred, received, awaiting analysis, undergoing analysis, exploited | `nvd-fichas/por-anio.csv`, `por-mes.csv` |
| parque instalado | installed base | `parque-instalado` |
| edad (del fallo al entrar en el catálogo) | age (of the flaw at catalogue entry: year added minus CVE year) | `parque-instalado/altas-edades.csv` |
| `anio_cve`, `anio_alta`, `fecha_alta`, `edad`, `proveedor`, `producto`, `borde_red` | CVE year, year added, date added, age, vendor, product, network-edge device | `parque-instalado/altas-edades.csv` |
| `edad_0`, `edad_1_4`, `edad_5_9`, `edad_10_mas`, `pct_5_mas`, `mas_antiguo` | age bands, share five years or older, oldest CVE | `parque-instalado/edades-por-anio.csv` |
| dispositivos de borde de red | network-edge devices (firewalls, VPNs, routers) | `parque-instalado` |
| `region`, `mes`, `win11`, `win10`, `win7`, `winxp`, `win8`, `win81`, `otros` | region, month, share of each Windows version | `parque-instalado/windows-versiones.csv` |
| sondeo | survey (of model configurations) | `transformers` |
| `params_reales`, `params_predichos` | actual parameters, predicted parameters | `transformers/configs.csv` |
| regla, colección, nivel, estado | rule, collection, level, status | `sigma/reglas.csv` |
| `fp_declarado`, `fp_sustantivo` | false positives declared, false positives substantive | `sigma/reglas.csv` |
| manifiesto | manifest | `vigencia-boe/manifiesto.csv` |
| vigencia | currency (whether a legal code is up to date) | `vigencia-boe` |
| `codigo`, `categoria`, `bloque`, `materia` | code, category, block, subject | `vigencia-boe/manifiesto.csv` |
| `fecha_actualizacion`, `marca_tiempo` | update date, timestamp | `vigencia-boe/manifiesto.csv` |
