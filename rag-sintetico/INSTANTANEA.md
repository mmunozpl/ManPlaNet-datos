# Medición del RAG sintético: el permiso antes o después de recuperar

Corpus sintético, no documentos: `corpus.csv` guarda 600 vectores de 64
dimensiones generados con semilla fija, agrupados en tres ámbitos alrededor de
un centroide, con la lista de autorizados de cada fragmento. `consultas.csv`
guarda las 300 consultas de un usuario autorizado solo al ámbito
público y, para cada una, cuántos fragmentos ajenos leyó el sistema y cuántos
útiles entregó en cada variante. No interviene ningún dato de ninguna persona.

- Motor: qdrant-client 1.19.0, modo local (:memory:) — misma API de filtro que el servidor
- Semilla: 20260825 · dimensiones: 64 · fragmentos: 600 (200 por ámbito) · k = 10
- Dispersión de los fragmentos alrededor de su centroide: 0.15 por dimensión, que deja el coseno medio en 0.411 dentro de un ámbito y -0.047 entre ámbitos · consultas uniformes en la esfera
- Extraído: 2026-09-12

## Resultado

| | permiso después de recuperar | permiso dentro de la consulta |
|---|---|---|
| fragmentos ajenos leídos, media por consulta | 6.29 | 0 |
| fragmentos ajenos leídos, total | 1886 | 0 |
| consultas con al menos uno ajeno | 280 de 300 | 0 |
| resultados útiles entregados, media de 10 | 3.71 | 10.0 |
| consultas sin ningún resultado útil | 88 | 0 |

## Campos

| Columna | Origen |
|---|---|
| `ambito`, `acl` | ámbito del fragmento y su lista de autorizados |
| `v0`…`v63`, `q0`…`q63` | el vector, normalizado |
| `post_utiles`, `post_expuestos`, `post_vacia` | recuperar k y descartar lo ajeno después |
| `pre_utiles`, `pre_expuestos` | filtro de `acl` dentro de la consulta |

La dispersión de los ámbitos es una decisión del diseño, no un dato: con más
solapamiento entre ámbitos se lee más material ajeno, y con menos, menos. Se
declara aquí para que se pueda discutir o rehacer con otro valor.
