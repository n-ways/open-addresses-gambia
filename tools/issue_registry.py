#!/usr/bin/env python3
"""The compounds of The Gambia for issuing home codes (engine/SPEC.md section 7).

Reads N-Ways' map data read-only, groups every structure into compounds
(SPEC 7.1: R0 enclosures, R1 satellites, R2 rural concessions), gives each
compound its gate (7.2), its lieu (3.2, Lieux.nearest) and its coverage (SPEC 5),
and writes one JSON line per compound (gzip). NUMBERS ARE NOT GIVEN HERE: the
registry server (the N-Ways backend, `homecodes issue -country GM`) numbers
them, keeps every number already issued and only adds new ones.

  python3 tools/issue_registry.py extract --root <data root> --work DIR      heavy: DuckDB, 3 GB cap
  python3 tools/issue_registry.py group --work DIR --out compounds.jsonl.gz  one zone at a time
  python3 tools/issue_registry.py counts --work DIR                       compounds per lieu -> model/lieux.json

`counts` writes each lieu's real compound count into model/lieux.json; then
run `tools/build_lieux.py ranges` to cut the national ranges from those counts before
first issue (after it the blocks are frozen and only ever added to).

The border decides (SPEC 2.1): grouping drops every structure whose centre,
and every compound whose entrance, lies more than 300 m outside the national
border (engine/data/border.geojson, from tools/build_border.py), whatever
the zone outlines say, so no building in a neighbouring country is ever listed.

Extracting needs NWAYS_DB (the N-Ways database, read-only, for the places
inside footprints) and duckdb. Run one heavy job at a time.

Each line: {"key": stable id of the main structure, "muni": zone key ("KMC"),
"zone": lieu ref ("KMC-0012"), "e", "n": the compound's centroid (UTM 28N),
"anchor": [lat, lon], "anchorKind": "gate"|"centre", "gate": [lat, lon]|null,
"coverage": "nways"|"official"|"official-pending", "official": address|null,
"enclosed": bool, "estate": id|null, "rule": "single"|"enclosure"|"satellite"|
"rural-concession", "extentM", "structures": [{"id", "src": "osm"|"ml", "lat",
"lon", "areaM2", "perimeterM", "tags", "places", "annexe", "urban", "wkt"}]}
(main structure first, then by distance from it).

Structure ids are stable across map updates: OpenStreetMap "osm:way/<id>" or
"osm:relation/<id>"; a Google/Microsoft footprint "nw:" + the first 12 hex
characters of the SHA-1 of its centre to 1e-6 degrees and its area to 1 m2.
"""
import argparse
import collections
import csv
import gzip
import hashlib
import json
import math
import os
import subprocess
import sys

csv.field_size_limit(1 << 30)
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MODEL = os.path.join(REPO, 'model')
sys.path.insert(0, os.path.join(REPO, 'engine', 'reference'))
import gm_engine as E  # noqa: E402

TAGS = ['building', 'building:levels', 'height', 'amenity', 'shop', 'office', 'tourism', 'religion', 'craft',
        'industrial', 'name', 'man_made', 'healthcare', 'government', 'addr:street', 'addr:housenumber',
        'addr:postcode', 'ref']
UTM = "'EPSG:4326', 'EPSG:32628', always_xy := true"
BOX = (-16.95, 13.0, -13.7, 13.9)


def duck(sql, work):
    os.makedirs(os.path.join(work, 'duck-tmp'), exist_ok=True)
    r = subprocess.run(['duckdb', '-csv'], input=sql, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.exit('duckdb failed: ' + r.stderr[-3000:])


def export_places(work):
    """N-Ways places in The Gambia's box (for the class of the building they are in)."""
    db = os.environ.get('NWAYS_DB')
    if not db:
        sys.exit('NWAYS_DB is needed (read-only) to export the places')
    q = (f"\\copy (SELECT id, category, ST_X(location::geometry) AS lon, ST_Y(location::geometry) AS lat FROM places "
         f"WHERE ST_Intersects(location::geometry, ST_MakeEnvelope({BOX[0]}, {BOX[1]}, {BOX[2]}, {BOX[3]}, 4326))) "
         f"TO '{work}/places.csv' WITH CSV HEADER")
    subprocess.run(['psql', db, '-v', 'ON_ERROR_STOP=1', '-c', q], check=True)


def extract(root, work):
    """Every structure of The Gambia with its zone (SPEC 2.2: lowest index wins),
    its enclosure (the smallest N-Ways compound or site holding its centre;
    an estate only marks its houses), the places inside it and its footprint,
    partitioned by zone."""
    export_places(work)
    osm = os.path.join(root, 'data', 'detail', 'countries', 'gambia', 'buildings-src.geojsonseq')
    ml = os.path.join(root, 'data', 'detail', 'ml', 'GM.parquet')
    comp = os.path.join(root, 'data', 'valhalla', 'compounds.geojsonseq')
    gates = os.path.join(root, 'data', 'valhalla', 'gates.geojsonseq')
    zones = os.path.join(MODEL, 'zones.geojson')
    zmeta = os.path.join(MODEL, 'zones.json')
    tagobj = ', '.join(f"'{t}', json_extract_string(j, '$.properties.\"{t}\"')" for t in TAGS)
    line = "(SELECT ltrim(line, chr(30)) AS j FROM read_csv('{}', columns={{'line': 'VARCHAR'}}, header=false, delim=chr(1), quote='', escape='', max_line_size=16000000) WHERE length(line) > 2)"
    duck(f"""
SET memory_limit='3GB'; SET threads=4; SET preserve_insertion_order=false; SET temp_directory='{work}/duck-tmp';
INSTALL spatial; LOAD spatial;
CREATE TABLE zm AS SELECT unnest(zones, recursive := true) FROM read_json('{zmeta}');
CREATE TABLE zg AS SELECT key, geom FROM ST_Read('{zones}');
CREATE TABLE z AS SELECT zg.key, zm.index AS zi, zg.geom FROM zg JOIN zm USING (key);
CREATE TABLE raw AS
SELECT 'osm' AS src, json_extract_string(j, '$.properties."@type"') || '/' || json_extract_string(j, '$.properties."@id"') AS oid,
  ST_GeomFromGeoJSON(json_extract(j, '$.geometry')) AS g, to_json(json_object({tagobj})) AS tags
FROM {line.format(osm)}
UNION ALL
SELECT 'ml', NULL, geometry::GEOMETRY, NULL FROM '{ml}';
CREATE TABLE b AS
SELECT row_number() OVER () AS bid, src, oid, tags, g, ST_PointOnSurface(g) AS c,
  ST_Area(ST_Transform(g, {UTM})) AS area_m2, ST_Perimeter(ST_Transform(g, {UTM})) AS perimeter_m,
  ST_AsText(ST_ReducePrecision(g, 0.0000001)) AS wkt
FROM raw;
DROP TABLE raw;
CREATE TABLE bz AS SELECT b.bid, arg_min(z.key, z.zi) AS zone FROM b JOIN z ON ST_Contains(z.geom, b.c) GROUP BY b.bid;
CREATE TABLE cp AS
SELECT json_extract_string(j, '$.properties.id') AS cid, json_extract_string(j, '$.properties.kind') AS kind,
  ST_GeomFromGeoJSON(json_extract(j, '$.geometry')) AS g
FROM {line.format(comp)};
DELETE FROM cp WHERE NOT ST_Intersects(g, ST_MakeEnvelope({BOX[0]}, {BOX[1]}, {BOX[2]}, {BOX[3]}));
CREATE TABLE be AS SELECT b.bid, arg_min(cp.cid, ST_Area(cp.g)) AS encl FROM b JOIN cp ON cp.kind <> 'estate' AND ST_Contains(cp.g, b.c) GROUP BY b.bid;
CREATE TABLE bs AS SELECT b.bid, arg_min(cp.cid, ST_Area(cp.g)) AS estate FROM b JOIN cp ON cp.kind = 'estate' AND ST_Contains(cp.g, b.c) GROUP BY b.bid;
CREATE TABLE gt AS SELECT json_extract_string(j, '$.properties.id') AS gid, ST_GeomFromGeoJSON(json_extract(j, '$.geometry')) AS pt FROM {line.format(gates)};
DELETE FROM gt WHERE NOT ST_Intersects(pt, ST_MakeEnvelope({BOX[0]}, {BOX[1]}, {BOX[2]}, {BOX[3]}));
COPY (SELECT cp.cid, arg_min(gt.gid, gt.gid) AS gid, arg_min(ST_Y(gt.pt), gt.gid) AS lat, arg_min(ST_X(gt.pt), gt.gid) AS lon
      FROM cp JOIN gt ON cp.kind <> 'estate' AND ST_DWithin(ST_Boundary(cp.g), gt.pt, 0.0001) GROUP BY cp.cid ORDER BY cp.cid)
  TO '{work}/gates.csv' (HEADER, DELIMITER ',');
CREATE TABLE p AS SELECT category, ST_Point(lon, lat) AS pt FROM read_csv('{work}/places.csv', header=true);
CREATE TABLE bp AS SELECT b.bid, list(p.category ORDER BY p.category) AS cats FROM p JOIN b ON ST_Contains(b.g, p.pt) GROUP BY b.bid;
COPY (
  SELECT bz.zone, b.bid, src, oid, ST_X(c) AS lon, ST_Y(c) AS lat, area_m2, perimeter_m, tags, wkt, be.encl, bs.estate,
    array_to_string(bp.cats, '|') AS cats
  FROM b JOIN bz USING (bid) LEFT JOIN be USING (bid) LEFT JOIN bs USING (bid) LEFT JOIN bp USING (bid)
) TO '{work}/structs' (FORMAT csv, HEADER, PARTITION_BY (zone), OVERWRITE_OR_IGNORE);
SELECT count(*) AS structures FROM b;
SELECT count(*) AS in_zones FROM bz;
""", work)


def structure_id(r):
    if r['src'] == 'osm':
        return 'osm:' + r['oid']
    h = hashlib.sha1(f"{float(r['lat']):.6f},{float(r['lon']):.6f},{round(float(r['area_m2']))}".encode()).hexdigest()[:12]
    return 'nw:' + h


class LieuIndex:
    """Lieux.nearest (SPEC 3.2) on a grid: the nearest place of any kind within
    2.5 km, else a town or city within 10 km, else the nearest of the zone;
    ties to the lower index."""

    def __init__(self, lieux):
        self.tiers = []
        for kinds, lim in (({'neighbourhood', 'suburb', 'village', 'locality', 'extension', 'town', 'city'}, 2500.0), ({'town', 'city'}, 10000.0)):
            g = collections.defaultdict(list)
            for it in lieux:
                if it['kind'] in kinds:
                    g[(int(it['e'] // lim), int(it['n'] // lim))].append(it)
            self.tiers.append((lim, g))
        self.all = lieux

    def nearest(self, e, n):
        for lim, g in self.tiers:
            gx, gy = int(e // lim), int(n // lim)
            best = None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for it in g.get((gx + dx, gy + dy), ()):
                        d = math.hypot(it['e'] - e, it['n'] - n)
                        if d <= lim and (best is None or (d, it['index']) < best[:2]):
                            best = (d, it['index'], it)
            if best:
                return best[2]
        return min(self.all, key=lambda it: (math.hypot(it['e'] - e, it['n'] - n), it['index']), default=None)


def group_zone(rows):
    """SPEC 7.1 on one zone's structures. R0 uses the enclosure each structure's
    centre lies in (the smallest one, from the extract); the rest is
    gm_engine.group_compounds' R1 and R2."""
    structs = []
    for r in rows:
        e, n = E.utm_forward(float(r['lat']), float(r['lon']))
        structs.append({'id': r['sid'], 'e': e, 'n': n, 'area': float(r['area_m2']), 'row': r})
    encl = collections.defaultdict(list)
    for s in structs:
        if s['row']['encl']:
            encl[s['row']['encl']].append(s)
    # tile density over the whole zone (SPEC 7.1: urban fabric), for every structure
    tiles = collections.Counter((int(s['e'] // E.URBAN_TILE), int(s['n'] // E.URBAN_TILE)) for s in structs)
    for s in structs:
        s['tileCount'] = tiles[(int(s['e'] // E.URBAN_TILE), int(s['n'] // E.URBAN_TILE))]
        s['urban'] = s['tileCount'] >= E.URBAN_MIN
    # R0: one compound per enclosure; the rest grouped by the engine's R1/R2.
    loose = [s for s in structs if not s['row']['encl']]
    comps = E.group_compounds(loose)
    by_id = {s['id']: s for s in structs}
    for cid, members in encl.items():
        members.sort(key=lambda s: (-s['area'], s['id']))
        m0 = members[0]
        rest = sorted(members[1:], key=lambda s: (math.hypot(s['e'] - m0['e'], s['n'] - m0['n']), s['id']))
        ms = [m0] + rest
        tot = sum(s['area'] for s in ms)
        ce = sum(s['e'] * s['area'] for s in ms) / tot
        cn = sum(s['n'] * s['area'] for s in ms) / tot
        ext = max(math.hypot(s['e'] - ce, s['n'] - cn) + E.radius(s['area']) for s in ms)
        comps.append({'members': [s['id'] for s in ms], 'rule': 'enclosure', 'confidence': 0.9,
                      'urban': True, 'e': ce, 'n': cn, 'extentM': round(ext, 1), 'encl': cid})
    return comps, by_id


def group(work, out_path, only=None):
    lieux = json.load(open(os.path.join(MODEL, 'lieux.json')))['lieux']
    by_zone = collections.defaultdict(list)
    for it in lieux:
        by_zone[it['zone']].append(it)
    gates = {}
    gp = os.path.join(work, 'gates.csv')
    if os.path.exists(gp):
        for row in csv.DictReader(open(gp, newline='', encoding='utf-8')):
            gates[row['cid']] = (float(row['lat']), float(row['lon']))
    border = E.Border()
    counts = collections.Counter()
    per_lieu = collections.Counter()
    seen = set()
    zdirs = sorted(d for d in os.listdir(os.path.join(work, 'structs')) if d.startswith('zone='))
    with gzip.open(out_path, 'wt', encoding='utf-8') as out:
        for zd in zdirs:
            zk = zd[5:]
            if only and zk not in only:
                continue
            rows = []
            for fn in sorted(os.listdir(os.path.join(work, 'structs', zd))):
                with open(os.path.join(work, 'structs', zd, fn), newline='', encoding='utf-8') as f:
                    for r in csv.DictReader(f):
                        r['sid'] = structure_id(r)
                        rows.append(r)
            # one structure id once (an OSM building drawn twice keeps its first row);
            # none across the national border (SPEC 2.1)
            uniq = {}
            for r in rows:
                if not border.holds(float(r['lat']), float(r['lon'])):
                    counts['abroadStructure'] += 1
                    continue
                if r['sid'] in uniq:
                    counts['duplicateStructure'] += 1
                    continue
                uniq[r['sid']] = r
            comps, by_id = group_zone(list(uniq.values()))
            li = LieuIndex(by_zone[zk])
            for c in comps:
                lieu = li.nearest(c['e'], c['n'])
                if lieu is None:
                    counts['noLieu'] += 1
                    continue
                ms = [by_id[i] for i in c['members']]
                m0 = ms[0]
                key = m0['id']
                if key in seen:
                    counts['duplicateKey'] += 1
                    continue
                seen.add(key)
                gate = gates.get(c.get('encl')) if c.get('encl') else None
                anchor = gate or (float(m0['row']['lat']), float(m0['row']['lon']))
                if not border.holds(*anchor):
                    counts['abroadCompound'] += 1
                    continue
                # coverage (SPEC 5): a door a council has numbered (OSM addr:street and
                # addr:housenumber) keeps that street address as its official address
                official = None
                for s in ms:
                    t = json.loads(s['row']['tags']) if s['row']['tags'] else {}
                    if t.get('addr:street') and t.get('addr:housenumber'):
                        official = f"{t['addr:housenumber']} {t['addr:street']}"
                        break
                if official:
                    cov = 'official'
                elif lieu.get('coverage', 'nways') != 'nways':
                    cov = 'official-pending'
                else:
                    cov = 'nways'
                sts = []
                for s in ms:
                    r = s['row']
                    tags = {k: v for k, v in (json.loads(r['tags']) if r['tags'] else {}).items() if v}
                    sts.append({'id': s['id'], 'src': r['src'], 'lat': round(float(r['lat']), 7), 'lon': round(float(r['lon']), 7),
                                'areaM2': round(float(r['area_m2']), 1), 'perimeterM': round(float(r['perimeter_m']), 1),
                                'tags': tags, 'places': [p for p in r['cats'].split('|') if p] if r['cats'] else [],
                                'annexe': bool(s.get('satellite')), 'urban': bool(s.get('urban')), 'wkt': r['wkt']})
                rec = {'key': key, 'muni': zk, 'zone': f"{zk}-{lieu['index']:04d}", 'e': round(c['e'], 1), 'n': round(c['n'], 1),
                       'anchor': [round(anchor[0], 7), round(anchor[1], 7)], 'anchorKind': 'gate' if gate else 'centre',
                       'gate': [round(gate[0], 7), round(gate[1], 7)] if gate else None, 'coverage': cov, 'official': official,
                       'enclosed': c['rule'] == 'enclosure', 'estate': (m0['row']['estate'] or None), 'rule': c['rule'],
                       'extentM': c['extentM'], 'structures': sts}
                out.write(json.dumps(rec, ensure_ascii=False, separators=(',', ':')) + '\n')
                counts['compounds'] += 1
                counts['structures'] += len(sts)
                counts['cov:' + cov] += 1
                per_lieu[rec['zone']] += 1
            print(zk, len(uniq), 'structures,', sum(1 for _ in comps), 'compounds', flush=True)
    json.dump(per_lieu, open(os.path.join(work, 'per-lieu.json'), 'w'))
    print(json.dumps(counts))


def write_counts(work):
    """The real compounds of each lieu into model/lieux.json (before first issue only)."""
    per = json.load(open(os.path.join(work, 'per-lieu.json')))
    p = os.path.join(MODEL, 'lieux.json')
    doc = json.load(open(p))
    nf = json.load(open(os.path.join(MODEL, 'name-families.json')))
    if nf.get('issued'):
        sys.exit('the name ranges are frozen (issued): counts no longer change blocks')
    for it in doc['lieux']:
        it['compounds'] = per.get(f"{it['zone']}-{it['index']:04d}", 0)
    json.dump(doc, open(p, 'w'), ensure_ascii=False, separators=(',', ':'))
    print('lieux with compounds:', sum(1 for it in doc['lieux'] if it['compounds']), 'of', len(doc['lieux']),
          '; compounds:', sum(it['compounds'] for it in doc['lieux']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=['extract', 'group', 'counts'])
    ap.add_argument('--root', default=os.environ.get('NWAYS_ROOT'))
    ap.add_argument('--work', required=True)
    ap.add_argument('--zone', action='append', help='only these zone keys (KMC, WCR...)')
    ap.add_argument('--out')
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    if a.stage == 'extract':
        if not a.root:
            sys.exit('--root (or NWAYS_ROOT): the N-Ways checkout')
        extract(os.path.abspath(a.root), os.path.abspath(a.work))
    elif a.stage == 'group':
        if not a.out:
            sys.exit('--out compounds.jsonl.gz')
        group(a.work, a.out, set(a.zone or []))
    else:
        write_counts(a.work)


if __name__ == '__main__':
    main()
