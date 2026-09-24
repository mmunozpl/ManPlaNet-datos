# [Datos] Mediciones que respaldan los artículos de manpla.net

🇪🇸 Español · 🇬🇧 [English](README.md)

**Manuel Muñoz Plá** · [ORCID 0009-0000-5714-912X](https://orcid.org/0009-0000-5714-912X)

[![Web](https://img.shields.io/badge/Web-manpla.net-009e73)](https://manpla.net)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0000--5714--912X-a6ce39)](https://orcid.org/0009-0000-5714-912X)
[![License](https://img.shields.io/badge/License-Apache--2.0-009e73)](LICENSE)
[![Binder](https://img.shields.io/badge/Binder-Cuadernos-009e73)](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main)
[![Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97_Hugging_Face-Space-ffd21e)](https://huggingface.co/spaces/ManPla/rag-sintetico)
[![Cite](https://img.shields.io/badge/Cite-BibTeX-009e73)](#cómo-citar)

**Resumen:** Cada artículo de [manpla.net](https://manpla.net) que afirma una
cifra la mide, y este repositorio guarda el soporte de esas cifras: la
instantánea de cada fuente en la fecha en que se tomó, la ficha de
procedencia que dice de dónde salió y qué contiene cada columna, y el guion
que la produce, para volver a tomarla. Son recuentos y metadatos, no las
fuentes: ninguna carpeta redistribuye un catálogo de vulnerabilidades, un
modelo, un artículo de arXiv ni una norma. Los datos de personas tampoco
entran, salvo el conjunto Adult del censo de 1994, que su licencia permite
redistribuir y que se guarda tal como lo publica su repositorio.

## Contenido

Una carpeta por medición. Dentro, el dato, su ficha y —cuando se conservó—
el guion:

```
.
├── kev/              # altas por día en el catálogo KEV de CISA, ventana mensual y entradas con triaje forense
├── hf-tendencia/     # los 100 repositorios en tendencia del Hub de Hugging Face
├── agi-tendencias/   # cuota anual de nueve términos en los resúmenes de arXiv
├── arc-agi/          # el marcador verificado de ARC-AGI: puntuación, coste y arnés de cada evaluación, y la cabecera de Kaggle 2026
├── ijepa/            # simulación del muestreo de máscaras de I-JEPA
├── rag-sintetico/    # permisos en un RAG: 600 fragmentos sintéticos, 300 consultas, filtro antes o después
├── deepseek-kv/      # caché KV global por token en cuatro generaciones de DeepSeek, desde sus configs
├── euvd-kev/         # las dos listas de vulnerabilidades explotadas: el KEV de CISA y la EUVD de ENISA, entrada a entrada
├── hf-activos/       # parámetros totales y activos por token en los 100 modelos en tendencia del Hub, tensor a tensor
├── nvd-fichas/       # estado de enriquecimiento de cada CVE publicado desde 2023 en el NVD, y si consta como explotado
├── parque-instalado/ # edad del fallo al entrar en el catálogo de explotadas, y cuota de cada versión de Windows en escritorio
├── evaluador-bucle/  # dos simulaciones sobre el evaluador dentro del bucle: el mejor de k semillas y el asaltante sin modelo
├── rsi-survey/       # el survey de automejora recursiva, codificado: los ocho mecanismos L5 y la ecuación 4 recalculada
├── transformers/     # configuración de los 600 modelos más descargados del Hub
├── sigma/            # metadatos de las 3 760 reglas de detección de SigmaHQ
├── adult/            # el conjunto Adult de UCI, sin modificar
├── vigencia-boe/     # manifiesto diario de los 350 códigos electrónicos del BOE
├── GLOSARIO.md       # la forma inglesa de cada término y cada columna
├── CITATION.cff
└── LICENSE
```

Cada carpeta lleva además un cuaderno, `reproducir.ipynb`, que carga el dato
de al lado, muestra la ficha y dibuja una figura; `requirements.txt` en la
raíz es lo que Binder necesita para arrancarlos.

La ficha de cada carpeta se llama `INSTANTANEA.md` y lleva la fuente, la
fecha de extracción, la versión de la fuente cuando la publica, y una tabla
con el origen de cada columna. En `ijepa/` ese papel lo hace `resumen.json`,
con la semilla y los parámetros de la simulación.

## Afirmación → guion → dato

| Artículo | Guion | Dato |
|---|---|---|
| [Tres días y un triaje forense](https://manpla.net/posts/tres-dias-y-un-triaje/) · [Limpio, y ya estaba dentro](https://manpla.net/posts/limpio-y-ya-estaba-dentro/) · [Veinticuatro horas y un formulario](https://manpla.net/posts/veinticuatro-horas-y-un-formulario/) | `kev/generar.py` | `kev/altas.csv`, `ventanas-mensuales.csv`, `triaje-forense.csv`, `resumen.json` |
| [El escaparate y el contador](https://manpla.net/posts/el-escaparate-y-el-contador/) | `hf-tendencia/generar.py` | `hf-tendencia/tendencia.csv` |
| [Cuatro términos ya han tocado techo](https://manpla.net/posts/cuatro-terminos-ya-han-tocado-techo/) | `agi-tendencias/generar.py` | `agi-tendencias/cuotas.csv`, `comprobaciones.csv` |
| [Predecir sin dibujar](https://manpla.net/posts/predecir-sin-dibujar/) | `ijepa/generar.py` | `ijepa/cobertura.csv`, `muestras.csv`, `resumen.json` |
| [Un RAG que aguante una inspección](https://manpla.net/posts/un-rag-que-aguante-una-inspeccion/) | `rag-sintetico/generar.py` · [demo](https://huggingface.co/spaces/ManPla/rag-sintetico) | `rag-sintetico/corpus.csv`, `consultas.csv`, `resumen.json` |
| [Cuatro capas de cuarenta](https://manpla.net/posts/cuatro-capas-de-cuarenta/) | `deepseek-kv/generar.py` | `deepseek-kv/generaciones.csv`, `configs/*.json` |
| [Antes de la primera capa](https://manpla.net/posts/antes-de-la-primera-capa/) | procedimiento en `INSTANTANEA.md`; el guion del sondeo no se conservó | `transformers/configs.csv` |
| artículo en preparación | procedimiento en `INSTANTANEA.md`; el guion de la extracción no se conservó | `sigma/reglas.csv` |
| [Cinco de cada cien](https://manpla.net/posts/cinco-de-cada-cien/) | `hf-activos/generar.py` | `hf-activos/activos.csv`, `resumen.json` |
| [La llave dopada con IA y la cerradura con tecnología obsoleta](https://manpla.net/posts/treinta-y-tres-mil-sin-ficha/) | `parque-instalado/generar.py` · `nvd-fichas/generar.py` | `parque-instalado/edades-por-anio.csv`, `altas-edades.csv`, `windows-versiones.csv` · `nvd-fichas/por-anio.csv`, `por-mes.csv`, `cve-estados.csv.gz` |
| [La última IA construida por humanos, leída en profundidad](https://manpla.net/posts/la-ultima-ia-leida-por-dentro/) | `rsi-survey/generar.py` · `agi-tendencias/generar.py` | `rsi-survey/l5-sistemas.csv`, `hci-eq4.csv`, `resumen.json` · `agi-tendencias/cuotas.csv`, `comprobaciones.csv` |
| [Quién vigila al evaluador](https://manpla.net/posts/quien-vigila-al-evaluador/) | `evaluador-bucle/generar.py` | `evaluador-bucle/semillas.csv`, `asalto-serie.csv`, `asalto-por-tamano.csv`, `resumen.json` |
| [La misma IA saca un 62,7 o un 99,9 según quién la conecte al examen](https://manpla.net/posts/el-mismo-modelo-dos-arneses/) | `arc-agi/generar.py` · `agi-tendencias/generar.py` | `arc-agi/marcador.csv`, `frontera.csv`, `hueco-v2.csv`, `kaggle-2026.csv`, `resumen.json` · `agi-tendencias/cuotas.csv`, `comprobaciones.csv` |
| artículo en preparación | `euvd-kev/generar.py` | `euvd-kev/resumen.json`, `eu-kev.csv`, `ventanas-kev.csv`, `antiguedad-kev.csv`, `altas-mensuales.csv` |
| [Mirar ya es tratar](https://manpla.net/posts/mirar-ya-es-tratar/) | ninguno: se descarga de UCI | `adult/adult.data.gz`, `adult.test.gz`, `adult.names` |
| [Vigencia de los códigos normativos del BOE](https://manpla.net/temas/vigencia-codigos-normativos-boe/) | el de la página viva, diario | `vigencia-boe/manifiesto.csv`, `resumen-fichas.json` |

Las cifras de cada artículo corresponden a la instantánea de su fecha, que
es la que consta en la ficha y en el historial de este repositorio. Volver a
ejecutar un guion toma la instantánea de hoy y la sobrescribe.

## Reproducir

Python 3.10 o posterior. Los guiones usan la biblioteca estándar, salvo
`ijepa/generar.py`, que necesita NumPy, y `rag-sintetico/generar.py`, que
necesita NumPy y `qdrant-client`. Cada uno escribe junto a sí mismo, así
que se lanza desde cualquier sitio:

```bash
python kev/generar.py
python hf-tendencia/generar.py
python agi-tendencias/generar.py     # unos ocho minutos: arXiv pide pausa
python ijepa/generar.py              # determinista: semilla 20260910
python rag-sintetico/generar.py      # determinista: semilla 20260825; índice en memoria
python deepseek-kv/generar.py        # descarga cuatro config.json públicos de Hugging Face
python euvd-kev/generar.py           # el JSON del KEV y la API pública de la EUVD; unos dos minutos
python hf-activos/generar.py         # cabeceras safetensors de 100 repositorios; una hora, o minutos con HF_ACTIVOS_CACHE
python nvd-fichas/generar.py         # API 2.0 del NVD, sin clave; unos veinte minutos por el límite de peticiones
python parque-instalado/generar.py   # catálogo KEV de CISA y serie de StatCounter; segundos
python evaluador-bucle/generar.py    # determinista: semilla 20260917; medio minuto, sin red
python rsi-survey/generar.py         # transcripción codificada del survey; instantáneo, sin red
python arc-agi/generar.py            # los cuatro JSON del marcador de arcprize.org; segundos; la tabla de Kaggle solo si el cliente está configurado
```

Ninguno necesita credenciales. `kev`, `hf-tendencia`, `agi-tendencias`,
`deepseek-kv`, `euvd-kev`, `hf-activos`, `nvd-fichas`, `parque-instalado` y `arc-agi` consultan una API o descargan ficheros públicos —`arc-agi` añade la cabecera de Kaggle solo si encuentra el cliente configurado—; `ijepa`,
`rag-sintetico`, `evaluador-bucle` y `rsi-survey` no salen de la máquina.

## Cuadernos

Un cuaderno de lectura por medición, ejecutable en el navegador con Binder
—arranca sobre este mismo repositorio, así que el dato está al lado y no hay
que descargar nada ni tener cuenta— o en local con `jupyter lab`. Solo leen;
para volver a tomar la instantánea está `generar.py`.

- [`kev/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=kev%2Freproducir.ipynb)
- [`hf-tendencia/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=hf-tendencia%2Freproducir.ipynb)
- [`agi-tendencias/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=agi-tendencias%2Freproducir.ipynb)
- [`ijepa/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=ijepa%2Freproducir.ipynb)
- [`transformers/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=transformers%2Freproducir.ipynb)
- [`sigma/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=sigma%2Freproducir.ipynb)
- [`adult/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=adult%2Freproducir.ipynb)
- [`rag-sintetico/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=rag-sintetico%2Freproducir.ipynb)
- [`deepseek-kv/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=deepseek-kv%2Freproducir.ipynb)
- [`euvd-kev/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=euvd-kev%2Freproducir.ipynb)
- [`hf-activos/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=hf-activos%2Freproducir.ipynb)
- [`nvd-fichas/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=nvd-fichas%2Freproducir.ipynb)
- [`parque-instalado/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=parque-instalado%2Freproducir.ipynb)
- [`evaluador-bucle/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=evaluador-bucle%2Freproducir.ipynb)
- [`rsi-survey/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=rsi-survey%2Freproducir.ipynb)
- [`vigencia-boe/reproducir.ipynb`](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main?labpath=vigencia-boe%2Freproducir.ipynb)

La medición del RAG sintético tiene además una demo en Hugging Face,
[ManPla/rag-sintetico](https://huggingface.co/spaces/ManPla/rag-sintetico): el mismo corpus y el mismo índice en memoria,
para elegir una consulta y quién la lanza y ver qué lee el sistema en cada
variante.

La primera arrancada de Binder tarda unos minutos, porque construye la
imagen; las siguientes salen de su caché.

## Cómo citar

```bibtex
@misc{munozpla2026mediciones,
  author = {Muñoz Plá, Manuel},
  title  = {Mediciones que respaldan los artículos de manpla.net},
  year   = {2026},
  url    = {https://github.com/mmunozpl/ManPlaNet-datos},
  note   = {Versión 2026.09.13}
}
```

## Licencia

Los guiones, bajo [Apache-2.0](LICENSE). Las mediciones propias —`kev`,
`hf-tendencia`, `agi-tendencias`, `ijepa`, `transformers`, `sigma`,
`rag-sintetico` y `vigencia-boe`—, bajo
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.es). El material de terceros conserva sus condiciones, y cada ficha las declara:

- **KEV**: el recuento por día se toma del feed que CISA publica con la
  licencia enlazada desde el propio catálogo; no se redistribuye ninguna
  entrada.
- **Hugging Face y arXiv**: metadatos y recuentos leídos de sus API públicas;
  ni pesos, ni código, ni artículos.
- **SigmaHQ**: identificadores y campos agregables de las reglas, que se
  publican bajo la Detection Rule License 1.1; ni títulos, ni descripciones,
  ni lógica de detección.
- **Adult**: Becker y Kohavi, repositorio de aprendizaje automático de UCI,
  1996, [CC BY 4.0](https://doi.org/10.24432/C5XW20); se guarda sin
  modificar.
- **ARC Prize**: las cifras que publica en los JSON de su marcador verificado
  y la cabecera de sus tablas de Kaggle; ninguna tarea del ARC-AGI.
- **BOE**: metadatos y enlaces de la Biblioteca Jurídica Digital, reutilizables
  en los términos de su aviso legal y de la Ley 37/2007, citando la fuente.
