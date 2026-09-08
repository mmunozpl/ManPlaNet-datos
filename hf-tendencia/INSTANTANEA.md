# Instantánea del escaparate de Hugging Face

Metadatos de los 100 repositorios con más «trending score» del Hub.
No contiene pesos ni código: solo los números que el propio Hub publica y el
recuento de ficheros de cada repositorio.

- API: https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=100
- Extraído: 2026-09-09
- Con cero descargas: 8
- Sin ningún fichero de consulta por defecto: 44

## Campos

| Columna | Origen |
|---|---|
| `puesto` | orden de la respuesta del Hub por `trendingScore` |
| `descargas`, `likes` | los que publica el Hub en la ficha del modelo |
| `creado`, `edad_dias` | `createdAt`, y su distancia a la fecha del sondeo |
| `biblioteca` | `library_name` declarada en el repositorio |
| `ficheros` | número de entradas en `siblings` |
| `con_fichero_consulta` | 1 si contiene alguno de los cinco ficheros de consulta por defecto |
| `safetensors_raiz` | 1 si tiene algún `.safetensors` en la raíz, no anidado |

Las dos últimas columnas son cálculo propio sobre el listado de ficheros, y
sirven para contrastar el recuento de descargas contra el mecanismo que el
Hub documenta. La lista de ficheros de consulta por defecto se toma de la
documentación del Hub y puede cambiar sin aviso.
