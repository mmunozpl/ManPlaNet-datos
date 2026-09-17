# [Data] Measurements behind the articles at manpla.net

🇬🇧 English · 🇪🇸 [Español](LEEME.md)

**Manuel Muñoz Plá** · [ORCID 0009-0000-5714-912X](https://orcid.org/0009-0000-5714-912X)

[![Web](https://img.shields.io/badge/Web-manpla.net-009e73)](https://manpla.net)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0000--5714--912X-a6ce39)](https://orcid.org/0009-0000-5714-912X)
[![License](https://img.shields.io/badge/License-Apache--2.0-009e73)](LICENSE)
[![Binder](https://img.shields.io/badge/Binder-Notebooks-009e73)](https://mybinder.org/v2/gh/mmunozpl/ManPlaNet-datos/main)
[![Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97_Hugging_Face-Space-ffd21e)](https://huggingface.co/spaces/ManPla/rag-sintetico)
[![Cite](https://img.shields.io/badge/Cite-BibTeX-009e73)](#how-to-cite)

**Abstract:** Every article at [manpla.net](https://manpla.net) that states
a figure measures it, and this repository keeps the support for those figures:
the snapshot of each source on the date it was taken, the provenance record
that says where it came from and what each column contains, and the script
that produces it, so that it can be taken again. These are counts and
metadata, not the sources: no folder redistributes a vulnerability catalogue,
a model, an arXiv paper or a legal text. Nor do personal data come in, except
the Adult set from the 1994 census, which its licence allows to be
redistributed and which is kept exactly as its repository publishes it.

## Contents

One folder per measurement. Inside, the data, its record and — where it was
kept — the script:

```
.
├── kev/              # daily additions to CISA's KEV catalogue
├── hf-tendencia/     # the Hub's 100 trending repositories
├── agi-tendencias/   # yearly share of nine terms in arXiv abstracts
├── ijepa/            # simulation of I-JEPA's mask sampling
├── rag-sintetico/    # permissions in a RAG: 600 synthetic chunks, 300 queries, filter before or after
├── deepseek-kv/      # global KV cache per token across four DeepSeek generations, from their configs
├── euvd-kev/         # the two lists of exploited vulnerabilities, CISA's KEV and ENISA's EUVD, entry by entry
├── hf-activos/       # total and per-token active parameters of the Hub's 100 trending models, tensor by tensor
├── nvd-fichas/       # enrichment status of every CVE published since 2023 in the NVD, and whether it is listed as exploited
├── parque-instalado/ # age of the flaw when it enters the exploited catalogue, and share of each Windows version on the desktop
├── evaluador-bucle/  # two simulations of the evaluator inside the loop: best-of-k seeds and the attacker with no model
├── rsi-survey/       # the recursive self-improvement survey, coded: the eight L5 mechanisms and equation 4 recomputed
├── transformers/     # configs of the Hub's 600 most downloaded models
├── sigma/            # metadata of SigmaHQ's 3,760 detection rules
├── adult/            # UCI's Adult data set, unmodified
├── vigencia-boe/     # daily manifest of the BOE's 350 electronic codes
├── GLOSARIO.md       # the English form of every term and every column
├── CITATION.cff
└── LICENSE
```

Each folder also carries a notebook, `reproducir.ipynb`, which loads the data
next to it, prints the record and draws one figure; `requirements.txt` at the
root is what Binder needs to launch them.

Each folder's record is called `INSTANTANEA.md` and carries the source, the
extraction date, the source's version when it publishes one, and a table
with the origin of each column. In `ijepa/` that role is played by
`resumen.json`, with the seed and the parameters of the simulation.

## Claim → script → data

| Article | Script | Data |
|---|---|---|
| [Clean, and already inside](https://manpla.net/en/posts/clean-and-already-inside/) · [Twenty-four hours and a web form](https://manpla.net/en/posts/twenty-four-hours-and-a-web-form/) | `kev/generar.py` | `kev/altas.csv` |
| [The shop window and the counter](https://manpla.net/en/posts/the-shop-window-and-the-counter/) | `hf-tendencia/generar.py` | `hf-tendencia/tendencia.csv` |
| [Four terms have already peaked](https://manpla.net/en/posts/four-terms-have-already-peaked/) | `agi-tendencias/generar.py` | `agi-tendencias/cuotas.csv`, `comprobaciones.csv` |
| [Predicting without drawing](https://manpla.net/en/posts/predicting-without-drawing/) | `ijepa/generar.py` | `ijepa/cobertura.csv`, `muestras.csv`, `resumen.json` |
| [A RAG that survives an audit](https://manpla.net/en/posts/a-rag-that-survives-an-audit/) | `rag-sintetico/generar.py` · [demo](https://huggingface.co/spaces/ManPla/rag-sintetico) | `rag-sintetico/corpus.csv`, `consultas.csv`, `resumen.json` |
| [Four layers out of forty](https://manpla.net/en/posts/four-layers-out-of-forty/) | `deepseek-kv/generar.py` | `deepseek-kv/generaciones.csv`, `configs/*.json` |
| [Before the first layer](https://manpla.net/en/posts/before-the-first-layer/) | procedure in `INSTANTANEA.md`; the survey script was not kept | `transformers/configs.csv` |
| article in preparation | procedure in `INSTANTANEA.md`; the extraction script was not kept | `sigma/reglas.csv` |
| [Five in every hundred](https://manpla.net/en/posts/five-in-every-hundred/) | `hf-activos/generar.py` | `hf-activos/activos.csv`, `resumen.json` |
| [The key doped with AI and the lock with obsolete technology](https://manpla.net/en/posts/thirty-three-thousand-without-a-record/) | `parque-instalado/generar.py` · `nvd-fichas/generar.py` | `parque-instalado/edades-por-anio.csv`, `altas-edades.csv`, `windows-versiones.csv` · `nvd-fichas/por-anio.csv`, `por-mes.csv`, `cve-estados.csv.gz` |
| [The last AI built by humans, read from the inside](https://manpla.net/en/posts/the-last-ai-read-from-the-inside/) | `rsi-survey/generar.py` · `agi-tendencias/generar.py` | `rsi-survey/l5-sistemas.csv`, `hci-eq4.csv`, `resumen.json` · `agi-tendencias/cuotas.csv`, `comprobaciones.csv` |
| [Who watches the evaluator](https://manpla.net/en/posts/who-watches-the-evaluator/) | `evaluador-bucle/generar.py` | `evaluador-bucle/semillas.csv`, `asalto-serie.csv`, `asalto-por-tamano.csv`, `resumen.json` |
| article in preparation | `euvd-kev/generar.py` | `euvd-kev/resumen.json`, `eu-kev.csv`, `ventanas-kev.csv`, `antiguedad-kev.csv`, `altas-mensuales.csv` |
| [Looking is already processing](https://manpla.net/en/posts/looking-is-already-processing/) | none: downloaded from UCI | `adult/adult.data.gz`, `adult.test.gz`, `adult.names` |
| [Currency of the BOE legal codes](https://manpla.net/en/temas/boe-legal-codes-currency/) | the live page's own, daily | `vigencia-boe/manifiesto.csv`, `resumen-fichas.json` |

The figures in each article correspond to the snapshot of its date, which is
the one recorded in the provenance record and in this repository's history.
Running a script again takes today's snapshot and overwrites it.

## Reproducing

Python 3.10 or later. The scripts use the standard library, except
`ijepa/generar.py`, which needs NumPy, and `rag-sintetico/generar.py`, which
needs NumPy and `qdrant-client`. Each one writes next to itself, so it
can be launched from anywhere:

```bash
python kev/generar.py
python hf-tendencia/generar.py
python agi-tendencias/generar.py     # ~8 min: arXiv asks for a pause
python ijepa/generar.py              # deterministic: seed 20260910
python rag-sintetico/generar.py      # deterministic: seed 20260825; in-memory index
python deepseek-kv/generar.py        # downloads four public config.json files from Hugging Face
python euvd-kev/generar.py           # the KEV JSON and the EUVD's public API; about two minutes
python hf-activos/generar.py         # safetensors headers of 100 repositories; an hour, or minutes with HF_ACTIVOS_CACHE
python nvd-fichas/generar.py         # NVD API 2.0, no key; about twenty minutes because of the request limit
python parque-instalado/generar.py   # CISA's KEV catalogue and the StatCounter series; seconds
python evaluador-bucle/generar.py    # deterministic: seed 20260917; half a minute, no network
python rsi-survey/generar.py         # coded transcription of the survey; instant, no network
```

None needs credentials. `kev`, `hf-tendencia`, `agi-tendencias`,
`deepseek-kv`, `euvd-kev`, `hf-activos`, `nvd-fichas` and `parque-instalado` query an API or download public files; `ijepa`,
`rag-sintetico`, `evaluador-bucle` and `rsi-survey` never leave the machine.

## Notebooks

One reading notebook per measurement, runnable in the browser with Binder —
it launches on this very repository, so the data sit next to the notebook and
nothing has to be downloaded and no account is needed — or locally with
`jupyter lab`. They only read; to take the snapshot again there is
`generar.py`.

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

The synthetic-RAG measurement also has a demo on Hugging Face,
[ManPla/rag-sintetico](https://huggingface.co/spaces/ManPla/rag-sintetico): the same corpus and the same in-memory index,
to pick a query and who launches it and see what the system reads under each
variant.

Binder's first launch takes a few minutes, because it builds the image; the
following ones come from its cache.

## How to cite

```bibtex
@misc{munozpla2026mediciones,
  author = {Muñoz Plá, Manuel},
  title  = {Mediciones que respaldan los artículos de manpla.net},
  year   = {2026},
  url    = {https://github.com/mmunozpl/ManPlaNet-datos},
  note   = {Versión 2026.09.13}
}
```

## Licence

The scripts, under [Apache-2.0](LICENSE). The own measurements — `kev`,
`hf-tendencia`, `agi-tendencias`, `ijepa`, `transformers`, `sigma`,
`rag-sintetico` and `vigencia-boe` — under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Third-party material keeps its terms, and each record declares them:

- **KEV**: the daily count is taken from the feed CISA publishes under the
  licence linked from the catalogue itself; no entry is redistributed.
- **Hugging Face and arXiv**: metadata and counts read from their public
  APIs; no weights, no code, no papers.
- **SigmaHQ**: identifiers and aggregable fields of the rules, which are
  published under the Detection Rule License 1.1; no titles, no descriptions,
  no detection logic.
- **Adult**: Becker and Kohavi, UCI Machine Learning Repository, 1996,
  [CC BY 4.0](https://doi.org/10.24432/C5XW20); kept unmodified.
- **BOE**: metadata and links from the Biblioteca Jurídica Digital, reusable
  under the terms of its legal notice and of Law 37/2007, citing the source.
