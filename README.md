# N-Ways Addressing for The Gambia (`open-addresses-gambia`)

**Status: issued.** Every compound in The Gambia has an N-Ways home code: 471,031 codes in all seven zones, 471,030 from the first issue on 20 October 2026 and one issued since. They are provisional until residents confirm them. The complete registry is in [`registry/`](registry/README.md): every code, its entrance and centre, its compound profile, its official address, every building footprint, and the frozen place table. Nothing is held back. Open: Apache 2.0 code, ODbL data, CC BY 4.0 documents ([LICENSING.md](LICENSING.md)). Credit: "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)".

## In one paragraph

The Gambia's official address is the government's Plus Code (National Digital Addressing Policy, 2023): `F8HC+9G6 Bakau`. N-Ways keeps it and always shows it first. Beside it, every compound has a home code that is easy to say and remember: the town, village or neighbourhood people already name, and a short number, **`Bakau 2389`**, unique in the whole country on its own. On plates and forms it is written `BAKAU 2389 · KANIFING`; systems and QR codes use the machine form `GM-KMC-0001-2389-6`, the only form with a check digit. Places with the same name share one national number range, one block each, so `Brikama 1001` is in Central River and `Brikama 7042` in West Coast, with no town said after it.

## What is here

| Path | What it is |
|---|---|
| [registry/](registry/README.md) | The issued registry: one file of codes and one of building footprints per zone, the place table, and `MANIFEST.json` with counts and checksums |
| [server/](server/README.md) | A ready-to-deploy registry server and JSON API (`docker compose up`), with its [OpenAPI contract](server/openapi.yaml) and tests |
| [docs/api.md](docs/api.md) | Every API endpoint with a real request and its real response |
| [engine/SPEC.md](engine/SPEC.md) | The engine specification (normative) |
| [engine/reference/](engine/reference/) | The reference engine `gm_engine.py` (standard-library Python), its tests `test_gm.py` and test vectors `vectors.json` |
| engine/data/ | The national border (`border.geojson`): no code is issued more than 300 m outside it (SPEC 2.1) |
| model/ | The seven frozen zones (`zones.json`, `zones.geojson`), the 2,347 places with their short names and frozen blocks (`lieux.json`), and the 1,854 name families (`name-families.json`) |
| [docs/paper.md](docs/paper.md), [docs/paper.fr.md](docs/paper.fr.md) | The research paper, in English and French, with the PDFs alongside (`n-ways-addressing-gambia-en.pdf`, `-fr.pdf`) |
| docs/paper/, docs/figures/ | The paper's typesetting (LaTeX template, bibliography, build script) and its eight figures as TikZ sources with their data |
| [docs/existing-systems.md](docs/existing-systems.md) | What exists today (Plus Codes, council street names, postcodes), with sources |
| [tools/](tools/README.md) | How the zones, places, border and compounds were built (`build_zones.py`, `build_lieux.py`, `build_border.py`, `issue_registry.py`), and `paper_data.py`, which recomputes every measure and figure of the paper from the registry |
| [GOVERNANCE.md](GOVERNANCE.md), [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) | Who issues and how things change; how to propose a change; how to report a problem |
| [LICENSING.md](LICENSING.md), [NOTICE](NOTICE), [SOURCES.md](SOURCES.md), [CITATION.cff](CITATION.cff) | Licences and how to credit N-Ways; every data source; how to cite the paper |

## Run the reference engine

Python 3.9 or later, the standard library only.

```sh
cd engine/reference
python3 gm_engine.py selftest                      # Damm, name keys, Plus Codes, every place decodes, vectors.json
python3 -m unittest test_gm
python3 gm_engine.py find  "Bakau 2389"            # the home code in all its forms, with no context
python3 gm_engine.py check "GM-KMC-0001-2389-6"    # validate the machine form
python3 gm_engine.py plus  13.4783 -16.6787        # the government's Plus Code of a point
```

## Run the server

The server loads the whole registry into SQLite and serves it as a JSON API: look up a code in any form, find the code at a point, browse zones and places, decode Plus Codes. With Docker:

```sh
docker compose up -d                                 # imports the registry on first start, then serves
curl 'http://localhost:8080/v1/find?q=Bakau%202389'
```

With plain Python 3.9 or later:

```sh
python3 -m server import --registry registry --db data/addresses.sqlite
python3 -m server serve  --db data/addresses.sqlite --port 8080
python3 -m unittest server.tests.test_server
```

A deployment is read-only unless the State or N-WAYS LIMITED has designated it as The Gambia's issuer: one issuer per country is what keeps every code unique. [server/README.md](server/README.md) covers deployment behind TLS, configuration, backups, updates and the issuing rules; [docs/api.md](docs/api.md) shows every endpoint.

## Build the paper

The paper is written in pandoc Markdown with TeX mathematics (`docs/paper.md`, `docs/paper.fr.md`), which GitHub also renders, and typeset with LaTeX:

```sh
python3 tools/paper_data.py     # recompute the figure data and the measures from registry/
sh docs/paper/build.sh          # compile the figures, then build both PDFs into docs/
```

The build needs pandoc 3, tectonic (a self-contained TeX engine) and Poppler's `pdftocairo`. References are in `docs/paper/references.bib`.

## Use and credit

Use the codes, the data and the engine freely under the licences in [LICENSING.md](LICENSING.md), and credit "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)". Questions and reports: hello@nways.ng.
