#!/usr/bin/env python3
"""The place words of The Gambia (engine/SPEC.md section 3.2) and their
national number ranges (3.3).

  NWAYS_DB=… tools/build_lieux.py inventory     the places from N-Ways' geo_names
                                               (OpenStreetMap places, GeoNames localities)
  tools/build_lieux.py ranges <per-lieu.json>  cut every name's national range from the
                                               real compound counts (before first issue only)

Writes model/lieux.json and model/name-families.json. A GeoNames locality is
dropped when an OpenStreetMap place lies within 300 m of it, or within 1 km
with the same name key. Each place takes its zone from the frozen outlines,
its plate name (at most 12 characters and 2 words) and its index in its zone
(by name key, then id); the index and the plate name are frozen at first issue.
"""
import collections, json, math, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, '..', 'model')
sys.path.insert(0, os.path.join(HERE, '..', 'engine', 'reference'))
import gm_engine as E  # noqa: E402

KINDS = ('city', 'town', 'village', 'suburb', 'neighbourhood', 'locality')
# Landmarks mapped as places name no home: their compounds go to the town around
# them ("Dockyard Point" would have named most of Banjul, "Sukuta Traffic Light"
# 4,780 homes of Sukuta).
LANDMARK = re.compile(r'\b(point|islands?|roundabout|junction|traffic lights?|bridge|wharf|ferry|crossing|market|airport)\b', re.I)


def inventory():
    db = os.environ.get('NWAYS_DB')
    if not db:
        sys.exit('NWAYS_DB is needed (read-only)')
    q = (f"SELECT id, name, kind, ST_Y(location::geometry), ST_X(location::geometry), coalesce(popn, 0) FROM geo_names "
         f"WHERE country = 'GM' AND kind IN ({','.join(repr(k) for k in KINDS)}) AND upstream_gone_at IS NULL AND length(name) > 1")
    rows = [r.split('\t') for r in subprocess.run(['psql', db, '-At', '-F', '\t', '-c', q], capture_output=True, text=True, check=True).stdout.splitlines()]
    zones = E.Zones()
    osm, gn = [], []
    landmarks = 0
    for pid, name, kind, lat, lon, popn in rows:
        if LANDMARK.search(name):
            landmarks += 1
            continue
        lat, lon = float(lat), float(lon)
        e, n = E.utm_forward(lat, lon)
        main, alts = E.split_brackets(name.strip())
        it = {'id': pid, 'name': main, 'alts': alts, 'kind': kind, 'lat': lat, 'lon': lon, 'e': round(e), 'n': round(n), 'popn': int(popn)}
        (gn if pid.startswith('gn:') else osm).append(it)
    # One place mapped twice (a point and an area) keeps its first id.
    osm.sort(key=lambda x: x['id'])
    one, seen = [], collections.defaultdict(list)
    for it in osm:
        k = E.name_key(it['name'])
        if any(math.hypot(o['e'] - it['e'], o['n'] - it['n']) <= 1000 for o in seen[k]):
            continue
        seen[k].append(it)
        one.append(it)
    twice = len(osm) - len(one)
    osm = one
    grid = collections.defaultdict(list)
    for it in osm:
        grid[(it['e'] // 1000, it['n'] // 1000)].append(it)
    keep = list(osm)
    dropped = 0
    for it in gn:
        near = [o for dx in (-1, 0, 1) for dy in (-1, 0, 1) for o in grid.get((it['e'] // 1000 + dx, it['n'] // 1000 + dy), ())]
        if any(math.hypot(o['e'] - it['e'], o['n'] - it['n']) <= 300 or
               (math.hypot(o['e'] - it['e'], o['n'] - it['n']) <= 1000 and E.name_key(o['name']) == E.name_key(it['name'])) for o in near):
            dropped += 1
            continue
        keep.append(it)
    by_zone = collections.defaultdict(list)
    outside = 0
    for it in keep:
        zk = zones.lookup(it['lat'], it['lon'])
        if zk is None:
            outside += 1
            continue
        by_zone[zk].append(it)
    # How often each word appears across all place names: the rarest is the most distinctive.
    freq = collections.Counter(w.lower() for it in keep for w in E.plate_words(it['name']))
    lieux = []
    for zk in sorted(by_zone):
        for i, it in enumerate(sorted(by_zone[zk], key=lambda x: (E.name_key(x['name']), x['id']))):
            plate, rule, council, cands = E.derive_plate(it['name'], freq)
            rec = {'zone': zk, 'index': i, 'name': plate, 'officialName': it['name'], 'aliases': [], 'kind': it['kind'],
                   'source': it['id'], 'e': it['e'], 'n': it['n'], 'compounds': 0, 'coverage': 'nways', 'nearTown': None,
                   'plateRule': rule, 'needsCouncilChoice': council}
            if cands:
                rec['plateCandidates'] = cands
            rec['aliases'] = ([it['name']] if plate != it['name'] else []) + it['alts']
            lieux.append(rec)
    json.dump({'status': 'place inventory, before the ranges are cut', 'sources': 'N-Ways geo_names: OpenStreetMap places (ODbL), GeoNames localities (CC BY 4.0)',
               'lieux': lieux}, open(os.path.join(MODEL, 'lieux.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    print(f'{len(lieux)} places ({landmarks} landmarks left out, {twice} mapped twice, {dropped} GeoNames duplicates dropped, {outside} outside the zones); council choice: '
          f"{sum(1 for x in lieux if x['needsCouncilChoice'])}")


def ranges(per_path):
    """Cut every name's national range from the real counts (SPEC 3.3)."""
    nf_path = os.path.join(MODEL, 'name-families.json')
    if os.path.exists(nf_path) and json.load(open(nf_path)).get('issued'):
        sys.exit('the name ranges are frozen (issued): blocks are only ever added')
    per = json.load(open(per_path))
    p = os.path.join(MODEL, 'lieux.json')
    doc = json.load(open(p))
    for it in doc['lieux']:
        it['compounds'] = per.get(f"{it['zone']}-{it['index']:04d}", 0)
    fams = E.allocate_families(doc['lieux'])
    # An alias may not decode to another name: one that folds to another plate
    # name's key, or that two plate names claim, is dropped (and listed).
    claims = collections.defaultdict(set)
    for it in doc['lieux']:
        for a in it.get('aliases', []):
            claims[E.name_key(a)].add(it['nameKey'])
    dropped = 0
    for it in doc['lieux']:
        keep, gone = [], []
        for a in it.get('aliases', []):
            k = E.name_key(a)
            (gone if (k != it['nameKey'] and k in fams) or len(claims[k]) > 1 else keep).append(a)
        it['aliases'] = keep
        if gone:
            it['aliasesDropped'] = gone
            dropped += len(gone)
    print('aliases dropped:', dropped)
    json.dump(doc, open(p, 'w'), ensure_ascii=False, separators=(',', ':'))
    shared = {k: v for k, v in fams.items() if len(v['blocks']) > 1}
    digits = collections.Counter()
    for it in doc['lieux']:
        digits[it['digits']] += it['compounds']
    tot = sum(digits.values()) or 1
    summary = {'lieux': len(doc['lieux']), 'nameKeys': len(fams), 'repeatingNames': len(shared),
               'lieuxWithRepeatingNames': sum(len(v['blocks']) for v in shared.values()),
               'compounds': tot, 'shareByDigits': {str(d): round(c / tot, 4) for d, c in sorted(digits.items())}}
    json.dump({'status': 'ranges cut from the compound counts; frozen at first issue, after which blocks are only added', 'issued': False,
               'summary': summary, 'families': [{'key': k, **v} for k, v in sorted(fams.items())]},
              open(nf_path, 'w'), ensure_ascii=False, separators=(',', ':'))
    print(json.dumps(summary))


if __name__ == '__main__':
    if sys.argv[1] == 'inventory':
        inventory()
    else:
        ranges(sys.argv[2])
