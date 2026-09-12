# [Datos] Mediciones que respaldan los artículos de manpla.net

🇪🇸 Español · 🇬🇧 [English](README.md)

**Manuel Muñoz Plá** · [ORCID 0009-0000-5714-912X](https://orcid.org/0009-0000-5714-912X)

[![Web](https://img.shields.io/badge/Web-manpla.net-009e73)](https://manpla.net)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0000--5714--912X-a6ce39)](https://orcid.org/0009-0000-5714-912X)
[![License](https://img.shields.io/badge/License-Apache--2.0-009e73)](LICENSE)
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
├── kev/              # altas por día en el catálogo KEV de CISA
├── hf-tendencia/     # los 100 repositorios en tendencia del Hub de Hugging Face
├── agi-tendencias/   # cuota anual de nueve términos en los resúmenes de arXiv
├── ijepa/            # simulación del muestreo de máscaras de I-JEPA
├── transformers/     # configuración de los 600 modelos más descargados del Hub
├── sigma/            # metadatos de las 3 760 reglas de detección de SigmaHQ
├── adult/            # el conjunto Adult de UCI, sin modificar
├── vigencia-boe/     # manifiesto diario de los 350 códigos electrónicos del BOE
├── GLOSARIO.md       # la forma inglesa de cada término y cada columna
├── CITATION.cff
└── LICENSE
```

La ficha de cada carpeta se llama `INSTANTANEA.md` y lleva la fuente, la
fecha de extracción, la versión de la fuente cuando la publica, y una tabla
con el origen de cada columna. En `ijepa/` ese papel lo hace `resumen.json`,
con la semilla y los parámetros de la simulación.

## Afirmación → guion → dato

| Artículo | Guion | Dato |
|---|---|---|
| [Limpio, y ya estaba dentro](https://manpla.net/posts/limpio-y-ya-estaba-dentro/) · [Veinticuatro horas y un formulario](https://manpla.net/posts/veinticuatro-horas-y-un-formulario/) | `kev/generar.py` | `kev/altas.csv` |
| [El escaparate y el contador](https://manpla.net/posts/el-escaparate-y-el-contador/) | `hf-tendencia/generar.py` | `hf-tendencia/tendencia.csv` |
| [Cuatro términos ya han tocado techo](https://manpla.net/posts/cuatro-terminos-ya-han-tocado-techo/) | `agi-tendencias/generar.py` | `agi-tendencias/cuotas.csv`, `comprobaciones.csv` |
| [Predecir sin dibujar](https://manpla.net/posts/predecir-sin-dibujar/) | `ijepa/generar.py` | `ijepa/cobertura.csv`, `muestras.csv`, `resumen.json` |
| [Antes de la primera capa](https://manpla.net/posts/antes-de-la-primera-capa/) | procedimiento en `INSTANTANEA.md`; el guion del sondeo no se conservó | `transformers/configs.csv` |
| artículo en preparación | procedimiento en `INSTANTANEA.md`; el guion de la extracción no se conservó | `sigma/reglas.csv` |
| [Mirar ya es tratar](https://manpla.net/posts/mirar-ya-es-tratar/) | ninguno: se descarga de UCI | `adult/adult.data.gz`, `adult.test.gz`, `adult.names` |
| [Vigencia de los códigos normativos del BOE](https://manpla.net/temas/vigencia-codigos-normativos-boe/) | el de la página viva, diario | `vigencia-boe/manifiesto.csv`, `resumen-fichas.json` |

Las cifras de cada artículo corresponden a la instantánea de su fecha, que
es la que consta en la ficha y en el historial de este repositorio. Volver a
ejecutar un guion toma la instantánea de hoy y la sobrescribe.

## Reproducir

Python 3.10 o posterior. Los guiones usan la biblioteca estándar, salvo
`ijepa/generar.py`, que necesita NumPy. Cada uno escribe junto a sí mismo, así
que se lanza desde cualquier sitio:

```bash
python kev/generar.py
python hf-tendencia/generar.py
python agi-tendencias/generar.py     # unos ocho minutos: arXiv pide pausa
python ijepa/generar.py              # determinista: semilla 20260910
```

Ninguno necesita credenciales. Los dos primeros y el tercero consultan una API
pública. El cuarto no sale de la máquina.

## Cómo citar

```bibtex
@misc{munozpla2026mediciones,
  author = {Muñoz Plá, Manuel},
  title  = {Mediciones que respaldan los artículos de manpla.net},
  year   = {2026},
  url    = {https://github.com/mmunozpl/ManPlaNet-datos},
  note   = {Versión 2026.09.12}
}
```

## Licencia

Los guiones, bajo [Apache-2.0](LICENSE). Las mediciones propias —`kev`,
`hf-tendencia`, `agi-tendencias`, `ijepa`, `transformers`, `sigma` y
`vigencia-boe`—, bajo
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
- **BOE**: metadatos y enlaces de la Biblioteca Jurídica Digital, reutilizables
  en los términos de su aviso legal y de la Ley 37/2007, citando la fuente.
