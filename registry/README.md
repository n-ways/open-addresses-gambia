# registry/

The issued registry of The Gambia's N-Ways home codes (engine/SPEC.md section 7), complete: 471,031 codes in the seven zones, with 672,836 building footprints. Every compound received its home code in one run on 20 October 2026 (471,030 codes), with the place table and every name's blocks frozen; codes issued since are added by the same rules and nothing already issued ever changes. A code is provisional until people confirm it.

| File | Rows | What it holds |
|---|---|---|
| `lieux.csv.gz` | 2,347 | The frozen place table |
| `<KEY>.csv.gz` | one per code | The codes of one zone (BJL, CRR, KMC, LRR, NBR, URR, WCR) |
| `structures/<KEY>.csv.gz` | one per building | The buildings of each code of the zone, with their footprints |
| `MANIFEST.json` | | Counts per zone, the SHA-256 of every file before compression, the export date, the engine version, the credit and the licence |

## Columns

**`lieux.csv.gz`**: `lieu` (the place id, `KMC-0001`), `zone`, `index`, `plate_name` (the name in the code), `official_name`, `kind` (city, town, village, suburb, neighbourhood, locality), `name_key` (SPEC 3.3), `family`, `digits`, `blocks` (`lo-hi`, separated by `|`, in the order they were given), `needs_council_choice` (the short name awaits its council), `aliases` (`|`-separated), `near_town`, `coverage`, `e_utm28n`, `n_utm28n` (the place's position, WGS 84 / UTM zone 28N).

**`<KEY>.csv.gz`**, in order of name family and number:

| Column | Meaning |
|---|---|
| `machine` | The machine form, `GM-KMC-0001-2389-6`: zone, place index, number, check digit |
| `home`, `written` | The remembered form (`Bakau 2389`) and the written form for plates and forms (`BAKAU 2389 · KANIFING`) |
| `lieu`, `official_name` | The place and its official name |
| `number`, `check` | The number, and the check digit of the machine form |
| `status` | `provisional`, `confirmed` or `retired` (a retired number is never given again) |
| `issued`, `issued_at` | `bulk` (the first issue) or `on-demand`, and when (UTC) |
| `entrance_lat`, `entrance_lng`, `entrance_kind` | The point the code leads to: a mapped `gate`, a `door`, or the main building's `centre` |
| `plus_code` | The Plus Code of the entrance; with the place's town it is the official address (`F8HC+9G6 Bakau`) |
| `class`, `use`, `kind`, `structures`, `floor_area_m2` | The compound profile (SPEC 6): main class, use, kind (one building, a family compound, an enclosed site), number of buildings, total floor area |
| `postcode` | Empty: The Gambia has no postcodes |
| `coverage`, `official_address` | `official` and the council's street address where a council has numbered the door; empty elsewhere |
| `anchor_lat`, `anchor_lng` | The compound's centre, from which numbers are ordered along the Hilbert curve (SPEC 7.3 and 7.4) |
| `rule`, `enclosed` | How the compound's buildings were grouped (`single`, `satellite`, `rural-concession`, `enclosure`; SPEC 7.1), and whether a wall encloses it |

**`structures/<KEY>.csv.gz`**, in the same order, main building first: `machine`, `index`, `structure_id` (`osm:way/…`, `osm:relation/…`, or `nw:` and a hash for a machine-learned footprint), `use` (the class), `confidence`, `class_source` (the evidence for the class), `status` (`existing`, `construction`, `ruin`), `footprint_m2`, `perimeter_m`, `height_m`, `height_source`, `floors`, `floor_area_m2`, `name` (only for buildings that are not homes, as mapped), `data` (`osm`, `ml` or `people`), `footprint_wkt` (WGS 84, seven decimals).

Nothing about the people in a home is recorded anywhere.

## Use

```sh
gzip -dc registry/KMC.csv.gz | head
python3 -m server import --registry registry --db data/addresses.sqlite    # load and verify it all
```

The import checks every file against `MANIFEST.json` and refuses any mismatch.

## How it is made

The registry server (the N-Ways backend) is the single issuer of codes. It numbers the compounds that `tools/issue_registry.py` lists, keeps every code already issued and only adds new ones, so a rerun never renumbers. Every file here, the footprints and the numbering anchors included, is written by its export, in one step:

```sh
go run ./cmd/homecodes export -country GM -out <open-addresses-gm>/registry
```

Files are UTF-8, comma-separated, with LF line ends; a field is quoted only when it holds a comma, a quote or a line break. The `.gz` files are gzip at level 9 without a name or a time stamp, so the same data always gives the same bytes. `python3 -m server export` writes a registry in exactly this format: exporting straight after importing gives files whose contents, and so the SHA-256 in `MANIFEST.json`, are these byte for byte. The compressed bytes can differ, because two gzip implementations need not choose the same encoding of the same contents.

Credit: "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)". Licence: ODbL 1.0 ([LICENSE-DATA](../LICENSE-DATA)); the footprints carry their sources' terms ([LICENSING.md](../LICENSING.md)).
