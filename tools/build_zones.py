#!/usr/bin/env python3
"""The 7 frozen code zones of The Gambia (engine/SPEC.md section 2): its five
regions plus the City of Banjul and Kanifing Municipality, the units every
Gambian already says (BJL, KMC, WCR, NBR, LRR, CRR, URR).

  tools/build_zones.py <regions.geojson>    the 7 admin_level=4 OpenStreetMap
                                            relations, whole (not clipped at the border)

Writes model/zones.json (key, index, name, ISO 3166-2 code, the Hilbert frame
in WGS 84 / UTM 28N metres) and model/zones.geojson (the outlines). Run once:
the zones are frozen at first issue and never follow later boundary changes.
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, '..', 'model')
sys.path.insert(0, os.path.join(HERE, '..', 'engine', 'reference'))
import gm_engine as E  # noqa: E402

# Key, name and ISO 3166-2 code, by Wikidata id. Kanifing Municipality has no
# ISO 3166-2 code of its own; GM-KM stands in for it in the same style.
ZONES = {
    'Q3726': ('BJL', 'Banjul', 'GM-B'),
    'Q277397': ('KMC', 'Kanifing', 'GM-KM'),
    'Q846158': ('WCR', 'West Coast', 'GM-W'),
    'Q846161': ('NBR', 'North Bank', 'GM-N'),
    'Q824421': ('LRR', 'Lower River', 'GM-L'),
    'Q824431': ('CRR', 'Central River', 'GM-M'),
    'Q824373': ('URR', 'Upper River', 'GM-U'),
}


def main(path):
    fc = json.load(open(path))
    seen, feats, meta = set(), [], []
    for f in fc['features']:
        wd = f['properties'].get('wikidata')
        if wd not in ZONES or wd in seen:
            continue
        seen.add(wd)
        key, name, iso = ZONES[wd]
        polys = f['geometry']['coordinates'] if f['geometry']['type'] == 'MultiPolygon' else [f['geometry']['coordinates']]
        # Round to 1e-5 degrees (about a metre): enough for a zone, a smaller file.
        polys = [[[[round(x, 5), round(y, 5)] for x, y in ring] for ring in poly] for poly in polys]
        es, ns = [], []
        for poly in polys:
            for x, y in poly[0]:
                e, n = E.utm_forward(y, x)
                es.append(e)
                ns.append(n)
        e0, n0 = math.floor(min(es) / 1000) * 1000, math.floor(min(ns) / 1000) * 1000
        frame = math.ceil(max(max(es) - e0, max(ns) - n0) / 1000) * 1000
        meta.append({'key': key, 'name': name, 'iso': iso, 'wikidata': wd, 'originE': e0, 'originN': n0, 'frameMetres': frame})
        feats.append({'type': 'Feature', 'properties': {'key': key, 'name': name},
                      'geometry': {'type': 'MultiPolygon', 'coordinates': polys}})
    if len(meta) != 7:
        sys.exit(f'expected 7 zones, found {len(meta)}')
    meta.sort(key=lambda z: z['key'])
    for i, z in enumerate(meta):
        z['index'] = i
    json.dump({'frozen': '2026-10-20', 'crs': 'EPSG:32628 (WGS 84 / UTM zone 28N), for the Hilbert frames',
               'source': 'OpenStreetMap admin_level=4 relations (ODbL), © OpenStreetMap contributors', 'zones': meta},
              open(os.path.join(MODEL, 'zones.json'), 'w'), ensure_ascii=False, indent=1)
    json.dump({'type': 'FeatureCollection', 'features': feats}, open(os.path.join(MODEL, 'zones.geojson'), 'w'),
              ensure_ascii=False, separators=(',', ':'))
    for z in meta:
        print(z['index'], z['key'], z['name'], z['frameMetres'])


if __name__ == '__main__':
    main(sys.argv[1])
