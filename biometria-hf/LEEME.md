# Caras sintéticas y sus detectores en Hugging Face

Inventario de los modelos y las aplicaciones (Spaces) de Hugging Face cuyo
nombre remite a intercambiar caras o fabricar deepfakes, frente a los que
remiten a detectarlos o a comprobar que hay una persona viva delante de la
cámara (detección de ataques de presentación). Para los modelos detectores se
lee además su ficha y se anota si declara métricas, conjunto de prueba,
ataques de presentación o ataques de inyección.

Solo se usan la API pública de metadatos y los README públicos: no se descarga
ningún modelo, no se ejecuta ninguna aplicación y no interviene la imagen ni
ningún otro dato de ninguna persona. La consulta no tiene coste.

## Procedencia y licencia

- Búsquedas en `https://huggingface.co/api/models` y `/api/spaces` con los 25
  términos de `TERMINOS` en el guion, que casan con el identificador del
  repositorio. Fecha de consulta en `resumen.json`; las cifras cambian a diario.
- Los metadatos y las fichas son de sus autores. Esta carpeta publica los
  identificadores de los repositorios, su clasificación, sus recuentos y las
  marcas leídas en las fichas, no las fichas ni ningún fichero de los
  repositorios.
- La entrada que acompaña a la medición no nombra ninguna herramienta de
  intercambio de caras: los nombres solo están en `repos.csv`.

## Reproducir

```bash
python biometria-hf/generar.py todo                    # consulta la API
python biometria-hf/generar.py inventario --sin-red    # reclasifica lo guardado
python biometria-hf/generar.py instantanea             # congela la toma del día
```

Hace falta `tqdm`. Las búsquedas y las fichas quedan en `crudo/`, que no se
versiona. La consulta completa tarda unos cinco minutos.

## Ficheros

| Fichero | Qué contiene |
|---|---|
| `repos.csv` | cada repositorio encontrado: tipo, familia, subtipo, modalidad, fechas, descargas, «me gusta», licencia, estado y hardware del Space, y las marcas «sin filtros» e «invita a duplicar» |
| `recuentos.csv` | repositorios, descargas, «me gusta» y Spaces en marcha por tipo, familia, subtipo y modalidad |
| `serie_trimestral.csv` | repositorios creados por trimestre, tipo y familia |
| `fichas_detectores.csv` | por modelo detector: si tiene ficha, su longitud, si es la plantilla vacía, y si menciona métricas, conjunto de prueba, ataques de presentación o de inyección |
| `resumen.json` | lo anterior resumido, con la fecha de consulta |
| `instantaneas/AAAA-MM-DD/` | la toma de un día: los CSV y el resumen de esa fecha, y `metadatos.json.gz` con los metadatos completos que devolvió la API, uno por repositorio; la entrada publicada lee la del 2026-11-26 |

## Cómo se clasifica

Se mira el nombre del repositorio sin el usuario, el título y la descripción
corta de los Spaces y las etiquetas. Detección manda sobre generación. Un
repositorio que solo dice «deepfake» queda como ambiguo y no cuenta en ninguna
familia; en la muestra revisada de modelos resultó ser un clasificador. La clasificación se revisó a
mano sobre muestras de 15 a 20 repositorios por clase, y las reglas se
corrigieron tres veces con lo que salió de esas muestras. Las marcas de las
fichas son menciones detectadas con expresiones de búsqueda: una ficha que
nombra «accuracy» sin dar su valor cuenta, y una evaluación descrita con otro
vocabulario o en otro idioma no cuenta. Las descargas de `descargas_total` son
las acumuladas (`downloadsAllTime`); las de `descargas_30d`, las de los últimos
30 días (`downloads`).
