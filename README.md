# [Data] Measurements behind the articles at manpla.net

🇬🇧 English · 🇪🇸 [Español](LEEME.md)

**Manuel Muñoz Plá** · [ORCID 0009-0000-5714-912X](https://orcid.org/0009-0000-5714-912X)

[![Web](https://img.shields.io/badge/Web-manpla.net-009e73)](https://manpla.net)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0000--5714--912X-a6ce39)](https://orcid.org/0009-0000-5714-912X)
[![License](https://img.shields.io/badge/License-Apache--2.0-009e73)](LICENSE)
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
├── transformers/     # configs of the Hub's 600 most downloaded models
├── sigma/            # metadata of SigmaHQ's 3,760 detection rules
├── adult/            # UCI's Adult data set, unmodified
├── vigencia-boe/     # daily manifest of the BOE's 350 electronic codes
├── GLOSARIO.md       # the English form of every term and every column
├── CITATION.cff
└── LICENSE
```

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
| [Before the first layer](https://manpla.net/en/posts/before-the-first-layer/) | procedure in `INSTANTANEA.md`; the survey script was not kept | `transformers/configs.csv` |
| article in preparation | procedure in `INSTANTANEA.md`; the extraction script was not kept | `sigma/reglas.csv` |
| [Looking is already processing](https://manpla.net/en/posts/looking-is-already-processing/) | none: downloaded from UCI | `adult/adult.data.gz`, `adult.test.gz`, `adult.names` |
| [Currency of the BOE legal codes](https://manpla.net/en/temas/boe-legal-codes-currency/) | the live page's own, daily | `vigencia-boe/manifiesto.csv`, `resumen-fichas.json` |

The figures in each article correspond to the snapshot of its date, which is
the one recorded in the provenance record and in this repository's history.
Running a script again takes today's snapshot and overwrites it.

## Reproducing

Python 3.10 or later. The scripts use the standard library, except
`ijepa/generar.py`, which needs NumPy. Each one writes next to itself, so it
can be launched from anywhere:

```bash
python kev/generar.py
python hf-tendencia/generar.py
python agi-tendencias/generar.py     # ~8 min: arXiv asks for a pause
python ijepa/generar.py              # deterministic: seed 20260910
```

None needs credentials. The first two and the third query a public API. The
fourth never leaves the machine.

## How to cite

```bibtex
@misc{munozpla2026mediciones,
  author = {Muñoz Plá, Manuel},
  title  = {Mediciones que respaldan los artículos de manpla.net},
  year   = {2026},
  url    = {https://github.com/mmunozpl/ManPlaNet-datos},
  note   = {Versión 2026.09.12}
}
```

## Licence

The scripts, under [Apache-2.0](LICENSE). The own measurements — `kev`,
`hf-tendencia`, `agi-tendencias`, `ijepa`, `transformers`, `sigma` and
`vigencia-boe` — under
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
