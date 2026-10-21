# N-Ways Addressing for The Gambia: engine specification

Version 1.0, in force since the first issue on 20 October 2026. This specification is normative. `engine/reference/gm_engine.py` is its executable reference: where the two disagree, this document wins and the script has a bug. The registry server in `server/` uses the reference engine for every rule below and adds only storage and HTTP.

Words used here: a **structure** is one building footprint; a **compound** is the address unit, the plot one gate serves (a family compound, a house, a block of flats, a school); a **zone** is one of the 7 frozen code zones; a **place** is the place word of a home code, such as a town, village or neighbourhood.

## 1. What the engine does

| Function | Input → output |
|---|---|
| `find` | a typed home code ("Bakau 2513", "BAKAU 2513 · KANIFING", "bakau 25 13") → the one (zone, place, number) it names, with no context |
| `address_forms` | (place, number) → home, written, machine and spoken forms |
| `validate` | a machine form → valid or the reason it is not |
| `plus_code` / `short_plus` | a point → the government's Plus Code (the official address) |
| `name_key` / `allocate_families` | place words → national name families, number lengths and blocks |
| `group_compounds` | structures (+ enclosures) → compounds |
| `Lieux.nearest` | a point → its place |
| `number_lieu` / `insert_in_lieu` | the compounds of a place → numbers; a new compound → its number |
| `plus_decode` / `plus_recover` | a full Plus Code → its cell; a short Plus Code and a reference point → the full code |
| `classify` / `size_profile` / `compound_use` | a structure's tags, shape and size → its use class; a compound's classes → its use |

## 2. Zones

The 7 zones are The Gambia's five regions, the City of Banjul and Kanifing Municipality, with the abbreviations Gambians already use. Their outlines are the OpenStreetMap admin_level=4 relations, frozen on 20 October 2026 (`model/zones.json`, `model/zones.geojson`).

| Index | Key | Zone | ISO 3166-2 |
|---|---|---|---|
| 0 | BJL | Banjul | GM-B |
| 1 | CRR | Central River | GM-M |
| 2 | KMC | Kanifing | none (`GM-KM` in `zones.json` stands in for it) |
| 3 | LRR | Lower River | GM-L |
| 4 | NBR | North Bank | GM-N |
| 5 | URR | Upper River | GM-U |
| 6 | WCR | West Coast | GM-W |

**Point → zone.** The zone whose outline holds the point (the lowest index on an overlap); else the zone with the nearest outline vertex within 2 km (river banks, the coast); else the point is outside The Gambia. Each zone also has a Hilbert frame in WGS 84 / UTM 28N metres (`originE`, `originN`, `frameMetres`) for numbering.

### 2.1 The border decides

A code is only ever issued for a building whose entrance lies inside the national border of The Gambia, OpenStreetMap's admin_level=2 boundary (`ISO3166-1=GM`), or within 300 m of it (`gm_engine.BORDER_M`). A point further out is in a neighbouring country and is outside The Gambia, whatever the zone rule above gives: zone outlines, the 2 km reach along rivers and coasts, and outlines from other sources (geoBoundaries, GADM and the like) may spill over the border, and they never decide.

The border ships as `engine/data/border.geojson`, made by `tools/build_border.py` from the OpenStreetMap relation: its ways joined into rings and simplified by Douglas-Peucker at 50 m on the UTM 28N grid, coordinates to 1e-5 degrees (under 1 MB). The file records the largest distance between the simplified line and the true one, measured both ways (`maxDeviationM`, 49.8 m for the current file). `gm_engine.Border` applies 300 m less that deviation, rounded up (250 m), so a point it accepts is never more than 300 m outside the true border. The price is on the safe side: a point between 250 and 300 m outside may be refused, never one in a neighbouring country accepted.

## 3. The home code

### 3.1 Forms

| Form | Pattern | Example | Who uses it |
|---|---|---|---|
| **Home** | `<Place> <number>` | `Bakau 2513` | people: said, typed, written on a parcel |
| **Written** | `<PLACE> <number> · <ZONE NAME>` | `BAKAU 2513 · KANIFING` | plates, stickers, forms; never the check digit |
| **Machine** | `GM-<KEY>-<place index, 4 digits>-<number>-<check>` | `GM-KMC-0001-2513-1` | APIs, QR codes, partners |

The forms map one-to-one. The home form is **unique in the whole of The Gambia on its own**: no zone, town or position is needed to decode it. The number has 3, 4 or 5 digits and never starts with 0; 5 digits are written and said as 2 + 3 (`19 474`, "nineteen, four hundred and seventy-four"), 4 as two pairs ("twenty-five, thirteen").

### 3.2 Places

The places are the towns, villages, suburbs and neighbourhoods of N-Ways' `geo_names` (OpenStreetMap places, GeoNames localities). `tools/build_lieux.py`:

- drops a GeoNames locality when an OpenStreetMap place lies within 300 m, or within 1 km with the same name key, and keeps one entry for a place mapped twice within 1 km;
- leaves out landmarks mapped as places (points, islands, roundabouts, junctions, traffic lights, bridges, wharves, markets, the airport): they name no home;
- turns a second name in brackets into an alias ("Busura (Kunkujang)");
- gives each place its zone and its index in the zone (by name key, then id), both frozen at first issue.

**The plate name** (the name in the code) has at most 12 characters and 2 words; a trailing number counts in the characters only ("Brusubi 1"). Generic words go (village, ward, town, settlement, area, layout, quarters, phase, roundabout…). A name that still does not fit keeps its rarest words across all Gambian place names ("Balanghar Kerjuri" → "Kerjuri", since six villages are Balanghar something) as a provisional plate name, flagged for its council (`needsCouncilChoice`, up to 3 candidates). The official name stays an alias, so typing it works. An alias that folds to another plate name's key, or that two plate names claim, is dropped.

**Point → place (`Lieux.nearest`).** The nearest place of any kind within 2.5 km; else a town or city within 10 km; else the nearest place of the zone. Ties go to the lower index. Most Gambian towns have no neighbourhoods mapped, so a town centre takes its town, not the village next to it. A compound's place is decided when it is first numbered and never recomputed.

### 3.3 One national range per name

Every place whose plate name folds to the same **name key** belongs to one name family, with one national number range cut into one block per place. A number falls in exactly one block, so "name + number" decodes to one place and one compound anywhere in the country.

**Name key.** `ñ` → `ny`, `ŋ` → `ng`; accents and case removed; hyphens, apostrophes, dots and brackets become spaces; a trailing number and the words *no*, *number*, *village*, *ward* at the end are dropped; *the*, *village*, *of* at the start are dropped; `kerr`, `keur`, `kerre` → `ker`; spaces removed; then `ou` → `u`, `oo` → `u`, `ee` → `i`, `dj` → `j`, `kh` → `k`, `ph` → `f`, `th` → `t`, `c` before e/i/y → `s`, `ck`/`c`/`q` → `k`, `y` → `i`, `h` dropped; doubled letters collapsed; a final `e` dropped after two letters. So Serrekunda = Serre Kunda, Kerr Mbaye = Keur Mbaye, Sukuta = Sukkuta, Suwareh = Suware.

**Number length and blocks.** Each place needs a block of 3 × its compounds (room for about 30 years of growth), rounded up to tens (3 digits) or hundreds (4-5 digits). A name's digits d is the smallest of 3, 4, 5 for which its blocks fill at most 90 % of the range; blocks are cut from the bottom in (zone, index) order. The block table is frozen at first issue: blocks are never moved, renumbered or shrunk; a full place gets a further block of one grain from its name's spare space.

**2026 counts** (`model/name-families.json`): 2,347 places, 1,854 names; 298 names repeat over 791 places; 572 plate names wait for their council. Number lengths, share of compounds: 3 digits 18.6 %, 4 digits 53.5 %, 5 digits 27.9 %.

### 3.4 Typing

`find` reads the trailing digits as the number and the words before them as the name. The name key gives the family, the family gives d, and the number is the last d digits; digits before them must be the place's own trailing number. A zone name after a comma and a check digit after another comma are only checked: a wrong one makes the code invalid, never re-routes it. A number in no block, or not issued, is not a home code.

## 4. Check digit

`check = Damm(family id as 5 digits ++ number as 5 digits)`, Damm's quasigroup check digit (the table in `gm_engine.DAMM`). It catches every single wrong digit and every swap of two adjacent digits; the selftest checks this on 3,000 random payloads. It binds the name and the number; the place follows from the block table, so a slip into another same-named place's block is refused. The check digit appears in the machine form only, where systems, QR codes and partners read it: plates, forms and everything people read show the name and number alone, so nobody has to remember or copy it. A machine form with a wrong check digit is refused, never corrected to a nearby code.

## 5. The official address: the government's Plus Code

The Gambia's National Digital Addressing Policy (2023) adopts Plus Codes (Open Location Code) as the national digital address. N-Ways shows, for every compound, the Plus Code of its gate with its town, first, as the official address: `F8HC+9G6 Bakau`. Where a council has numbered the door (an OpenStreetMap `addr:street` + `addr:housenumber`, or later the council's register), that street address comes first of all. The home code sits beside it and leads to the same gate. N-Ways issues no grid of its own.

## 6. Building profile

Each structure carries a use class, a short stable code (`res.maison` a house, `res.concession` a family compound, `com.boutique` a shop, `rel.mosquee` a mosque…; the full table is in `gm_engine.py`), its size, floors and status, each with its source; the compound sums them (use, kind, structures, floor area). The ladder: OSM building and amenity tags, N-Ways places inside the footprint, then shape (satellites, large low buildings, small rural huts). The heights that come with the machine-learned footprints are rendering placeholders, not measurements, and are never used. A home never carries a name or anything about the people inside.

## 7. Compounds and the registry

**Grouping (7.1).** R0: every structure whose centre is inside an N-Ways enclosure (a walled site or compound, not an estate) belongs to that enclosure's compound. R1: a structure under 30 m² joins the nearest main structure within 4 m (urban) or 8 m (rural) gap. R2: in rural fabric, small structures (under 120 m²) within 6 m of each other form one concession, at most 30. Urban fabric is a 250 m tile with at least 100 structures. Two main structures in urban fabric are never merged by shape alone.

**Gates (7.2).** A mapped gate on an enclosure's edge, else the main structure's centre.

**First issue (7.3).** Each place's compounds are ordered by the Hilbert index of their centre on a 2¹⁶ × 2¹⁶ grid over the zone's frame and spread evenly over the place's first block: compound i of n gets `lo + floor((i + 0.5) × (hi − lo + 1) / n)`.

**After first issue (7.4).** A new compound takes the free number midway between its Hilbert neighbours; else the lowest free number of the place's further blocks; else a new block from its name's spare space. Issued numbers never change; a retired number is never given again.

**The border (7.5).** Grouping drops every structure whose centre, and every compound whose entrance, lies outside the border by more than the limit of 2.1, before any place or number is given; issuing on demand refuses such a point, and an entrance never moves there. `tools/build_border.py check` counts the published codes whose entrance lies across the border: none.

**The registry** is kept by a single issuer, N-WAYS LIMITED, unless the State designates another (GOVERNANCE.md). It is published whole in `registry/`: every issued code with its entrance, its centre (from which numbers are ordered), its compound profile and its official address, the frozen place table with every block, and every structure with its footprint. `server/` serves it and, on the designated issuer's deployment only, issues by rule 7.4.

## 8. Test vectors

`python3 gm_engine.py vectors --write` writes `engine/reference/vectors.json`: Plus Codes of seven places, check digits, spoken numbers, name-key pairs, same-name decodings (Brikama, Sanchaba, Fula Kunda, Madina), and plate names with their official names typed. `selftest` recomputes them and checks that every one of the 2,347 places decodes on its own. Any implementation of this specification must reproduce them value for value.

## 9. Versioning

A change to any algorithm, constant, zone, frozen place field, the name key or an issued block bumps the major version and is not allowed for issued codes. Adding blocks is not a change. Profile rules may change in minor versions: they change classes, never codes.
