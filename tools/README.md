# tools/

How the zones, places, border and compounds of The Gambia were built (engine/SPEC.md), and the paper's measures. Python 3.9 or later; the heavy steps also need `duckdb` (with its spatial extension) and, for N-Ways' own data, `psql` with `NWAYS_DB` (read-only). Run one heavy job at a time.

| Script | What it does |
|---|---|
| `build_zones.py <regions.geojson>` | The 7 frozen code zones from the OpenStreetMap admin_level=4 relations -> `model/zones.json`, `model/zones.geojson` (SPEC 2) |
| `build_border.py build <extract.osm.pbf>` | The national border from the OpenStreetMap admin_level=2 relation of The Gambia -> `engine/data/border.geojson` (SPEC 2.1) |
| `build_border.py check` | Counts the published codes whose entrance lies more than 300 m outside the border; exits non-zero if there is any |
| `build_lieux.py inventory`, `ranges` | The place words and their national number ranges -> `model/lieux.json`, `model/name-families.json` (SPEC 3.2, 3.3) |
| `issue_registry.py extract`, `group`, `counts` | Every structure, grouped into compounds with their gate, place and coverage, one JSON line per compound, for the issuer to number (SPEC 7) |
| `paper_data.py` | Every measure and figure of the paper, recomputed from the registry |

## The border decides

A code is only ever issued for a building whose entrance lies inside the national border, OpenStreetMap's admin_level=2 boundary, or within 300 m of it. Zone outlines from any source (OpenStreetMap regions, geoBoundaries, GADM and the like) may spill over the border, and the zone rule reaches 2 km beyond the outlines along rivers and coasts; none of them decides.

`build_border.py build` reads the relation tagged `boundary=administrative`, `admin_level=2`, `ISO3166-1=GM` from an OpenStreetMap extract with DuckDB's `ST_ReadOSM`, joins its member ways into closed rings, simplifies them by Douglas-Peucker at 50 m on the UTM 28N grid and writes `engine/data/border.geojson` (about 10 kB). The extract must hold the relation whole: a country extract clipped at its own outline usually misses some of the border ways, and the tool then stops with "the border does not close". Use an extract of the region around The Gambia, or of the boundary relations alone (for example `osmium tags-filter <planet or region>.osm.pbf r/admin_level=2`). The file records the largest distance between the simplified line and the true one, measured both ways (`maxDeviationM`), and the limit the engine applies, 300 m less that deviation rounded up (`limitM`), so a point accepted is never more than 300 m outside the true border. `--full FILE` also writes the unsimplified border, which `check --border FILE` can use with the full 300 m.

`issue_registry.py group` loads that border (`gm_engine.Border`) and drops every structure whose centre lies beyond it, and then every compound whose entrance (its gate, else its main building's centre) lies beyond it, before any place is chosen; the counts it prints show how many (`abroadStructure`, `abroadCompound`). The registry server applies the same rule to every code issued on demand and every entrance moved (`422 outside`). `build_border.py check` verifies the published registry: 0 of 471,031 codes lie more than 300 m outside the border.

## Order

```sh
python3 tools/build_zones.py regions.geojson                         # once, before first issue
python3 tools/build_border.py build region.osm.pbf                     # the border; re-run when OpenStreetMap corrects it
NWAYS_DB=... python3 tools/build_lieux.py inventory
NWAYS_DB=... python3 tools/issue_registry.py extract --root <N-Ways checkout> --work work
python3 tools/issue_registry.py group --work work --out compounds.jsonl.gz
python3 tools/issue_registry.py counts --work work                    # before first issue only
python3 tools/build_lieux.py ranges work/per-lieu.json                 # before first issue only
python3 tools/build_border.py check                                    # after every export of the registry
```
