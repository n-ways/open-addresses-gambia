#!/usr/bin/env python3
"""Figure data and evaluation measures for the paper, computed from the
published registry and model (standard library only).

  python3 tools/paper_data.py            writes docs/figures/*.dat and prints the measures

Every number the paper reports about the registry can be recomputed with this
script; nothing is read from anywhere but registry/ and model/.
"""
import collections, csv, gzip, json, math, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'engine', 'reference'))
import gm_engine as E  # noqa: E402

REG = os.path.join(ROOT, 'registry')
FIG = os.path.join(ROOT, 'docs', 'figures')
ZONES = ['BJL', 'CRR', 'KMC', 'LRR', 'NBR', 'URR', 'WCR']
CELL_KM = 2.0


def rows(name):
    with gzip.open(os.path.join(REG, name), 'rt', encoding='utf-8', newline='') as f:
        yield from csv.DictReader(f)


def write(name, header, data):
    with open(os.path.join(FIG, name), 'w', encoding='utf-8') as f:
        f.write(header + '\n')
        for r in data:
            f.write(' '.join(str(v) for v in r) + '\n')


def simplify(pts, tol):
    """Douglas-Peucker on a list of (x, y)."""
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1e-12
    best, k = -1.0, 0
    for i in range(1, len(pts) - 1):
        d = abs(dy * (pts[i][0] - a[0]) - dx * (pts[i][1] - a[1])) / L
        if d > best:
            best, k = d, i
    if best <= tol:
        return [a, b]
    return simplify(pts[:k + 1], tol)[:-1] + simplify(pts[k:], tol)


def main():
    zones, lieux = E.Zones(), E.Lieux()
    out = {}

    # zone outlines in UTM 28N kilometres, rings separated by nan rows
    gj = json.load(open(os.path.join(ROOT, 'model', 'zones.geojson'), encoding='utf-8'))
    ring_rows, labels = [], []
    for f in gj['features']:
        for poly in f['geometry']['coordinates']:
            for ring in poly:
                pts = [tuple(v / 1000 for v in E.utm_forward(lat, lon)) for lon, lat in ring]
                k = max(range(len(pts)), key=lambda i: math.dist(pts[0], pts[i]))
                pts = simplify(pts[:k + 1], 0.15)[:-1] + simplify(pts[k:], 0.15)
                ring_rows += [(f'{x:.2f}', f'{y:.2f}') for x, y in pts] + [('nan', 'nan')]
    write('zones-outline.dat', 'x y', ring_rows)

    # every issued code: per-zone tallies, density cells, decoding and slips
    issued = collections.defaultdict(set)          # lieu ref -> numbers
    cells = collections.Counter()
    centroid = collections.defaultdict(lambda: [0.0, 0.0, 0])
    per_lieu = collections.Counter()
    homes, plus_ok, plus_recovered, total = set(), 0, 0, 0
    rule = collections.defaultdict(collections.Counter)
    lengths = collections.Counter()
    bakau = []
    find_ok = 0
    anchors = collections.defaultdict(list)
    for z in ZONES:
        for r in rows(f'{z}.csv.gz'):
            total += 1
            lieu = r['lieu']
            num = int(r['number'])
            issued[lieu].add(num)
            per_lieu[lieu] += 1
            homes.add(r['home'].lower())
            lengths[len(r['home'])] += 1
            rule[z][r['rule'] or 'single'] += 1
            lat, lng = float(r['anchor_lat']), float(r['anchor_lng'])
            e, n = E.utm_forward(lat, lng)
            cells[(int(e / 1000 // CELL_KM), int(n / 1000 // CELL_KM))] += 1
            c = centroid[z]
            c[0] += e; c[1] += n; c[2] += 1
            elat, elng = float(r['entrance_lat']), float(r['entrance_lng'])
            plus_ok += E.plus_code(elat, elng) == r['plus_code']
            zi, li = lieu.split('-')
            it = lieux.get(zi, int(li))
            plus_recovered += E.plus_recover(r['plus_code'][4:], *E.utm_inverse(it['e'], it['n'])) == r['plus_code']
            got = E.find(r['home'], zones, lieux)
            find_ok += len(got) == 1 and got[0][1] is it and got[0][2] == num
            anchors[lieu].append((e, n))
            if lieu == 'KMC-0001':
                ex, ny = E.utm_forward(lat, lng)
                bakau.append((ex, ny, num))
    out['codes'] = total
    out['distinctHomeForms'] = len(homes)
    out['plusEncodesEntrance'] = plus_ok
    out['plusShortRecoveredFromPlace'] = plus_recovered
    out['findUnique'] = find_ok
    out['homeLength'] = dict(sorted(lengths.items()))
    plate = collections.Counter(len(it['placeWord']) for it in lieux.items)
    write('lengths-plate.dat', 'chars places', [(k, plate.get(k, 0)) for k in range(1, 13)])
    write('lengths-home.dat', 'chars codes', [(k, lengths.get(k, 0)) for k in range(6, 20)])
    out['rulesByZone'] = {z: dict(rule[z]) for z in ZONES}

    write('density.dat', 'x y count',
          [((x + 0.5) * CELL_KM, (y + 0.5) * CELL_KM, k) for (x, y), k in sorted(cells.items())])
    write('zones-label.dat', 'x y key',
          [(f'{c[0] / c[2] / 1000:.1f}', f'{c[1] / c[2] / 1000:.1f}', z) for z, c in centroid.items()])
    out['densityCells'] = len(cells)
    out['densityMax'] = max(cells.values())

    # compounds per place, binned
    bins = [(0, 0), (1, 9), (10, 29), (30, 99), (100, 299), (300, 999), (1000, 2999), (3000, 9999)]
    counts = [per_lieu.get(f"{it['zone']}-{it['index']:04d}", 0) for it in lieux.items]
    hist = [(f'{lo}', sum(lo <= c <= hi for c in counts)) for lo, hi in bins]
    write('places-hist.dat', 'lo places', hist)
    s = sorted(counts)
    out['placesMedianCompounds'] = s[len(s) // 2]
    out['placesWithNone'] = sum(c == 0 for c in counts)
    out['placesHist'] = hist

    # Bakau, coloured by number, in metres from the place's south-west corner
    bakau.sort(key=lambda t: t[2])
    e0, n0 = min(t[0] for t in bakau), min(t[1] for t in bakau)
    write('bakau.dat', 'x y number', [(f'{(e - e0):.0f}', f'{(n - n0):.0f}', k) for e, n, k in bakau])
    out['bakau'] = {'codes': len(bakau), 'widthM': round(max(t[0] for t in bakau) - e0),
                    'heightM': round(max(t[1] for t in bakau) - n0)}
    gaps = [math.hypot(bakau[i + 1][0] - bakau[i][0], bakau[i + 1][1] - bakau[i][1]) for i in range(len(bakau) - 1)]
    gaps.sort()
    out['bakau']['medianStepM'] = round(gaps[len(gaps) // 2], 1)
    nn = []
    for i, (e, n, _) in enumerate(bakau):
        nn.append(min(math.hypot(e - f, n - g) for j, (f, g, _) in enumerate(bakau) if j != i))
    nn.sort()
    out['bakau']['medianNearestM'] = round(nn[len(nn) // 2], 1)

    # the blocks of two name families along their national ranges
    for key, name in (('brikama', 'blocks-brikama.dat'), ('madina', 'blocks-madina.dat')):
        f = lieux.families[key]
        d = f['digits']
        data = []
        for it in sorted(f['lieux'], key=lambda x: x['blocks'][0][0]):
            for lo, hi in it['blocks']:
                data.append((lo, hi, it['zone'], per_lieu.get(f"{it['zone']}-{it['index']:04d}", 0)))
        write(name, 'lo hi zone compounds', data)
        out[key] = {'digits': d, 'places': len(f['lieux']), 'blocks': data}

    # single-digit substitutions and adjacent transpositions of every issued home code
    sub = collections.Counter()
    swp = collections.Counter()
    for it in lieux.items:
        ref = f"{it['zone']}-{it['index']:04d}"
        mine = issued.get(ref, ())
        fam = lieux.families[it['nameKey']]
        for num in mine:
            s_ = str(num)
            variants = []
            for k in range(len(s_)):
                for x in '0123456789':
                    if x != s_[k]:
                        variants.append(('sub', s_[:k] + x + s_[k + 1:]))
                if k + 1 < len(s_) and s_[k] != s_[k + 1]:
                    variants.append(('swap', s_[:k] + s_[k + 1] + s_[k] + s_[k + 2:]))
            for kind, v in variants:
                tally = sub if kind == 'sub' else swp
                if v[0] == '0':
                    tally['not a number'] += 1
                    continue
                m = int(v)
                h = lieux.holder(it['nameKey'], m)
                if h is None:
                    tally['in no block'] += 1
                elif h is not it:
                    other = f"{h['zone']}-{h['index']:04d}"
                    tally['other place, issued' if m in issued.get(other, ()) else 'other place, free'] += 1
                else:
                    tally['same place, issued' if m in mine else 'same place, free'] += 1
    out['substitutions'] = dict(sub)
    out['transpositions'] = dict(swp)
    order = ['not a number', 'in no block', 'same place, free', 'other place, free', 'same place, issued', 'other place, issued']
    write('slips.dat', 'kind ' + ' '.join(f'c{i}' for i in range(len(order))),
          [(kind, *(f"{100 * t[o] / sum(t.values()):.2f}" for o in order))
           for kind, t in (('substitution', sub), ('transposition', swp))])

    # the same compounds ordered three ways: median and mean distance between consecutive numbers
    def morton(x, y):
        k = 0
        for b in range(16):
            k |= ((x >> b) & 1) << (2 * b) | ((y >> b) & 1) << (2 * b + 1)
        return k
    steps = {'hilbert': [], 'morton': [], 'rows': []}
    for ref, pts in anchors.items():
        z = zones.by_key[ref.split('-')[0]]
        side = z['frameMetres'] / 65536
        cell = [(min(65535, max(0, int((e - z['originE']) / side))), min(65535, max(0, int((n - z['originN']) / side))), e, n)
                for e, n in pts]
        for name, key in (('hilbert', lambda c: E.hilbert_d(16, c[0], c[1])), ('morton', lambda c: morton(c[0], c[1])),
                          ('rows', lambda c: (c[1], c[0]))):
            seq = sorted(cell, key=key)
            steps[name] += [math.hypot(seq[i + 1][2] - seq[i][2], seq[i + 1][3] - seq[i][3]) for i in range(len(seq) - 1)]
    out['ordering'] = {}
    for name, v in steps.items():
        v.sort()
        out['ordering'][name] = {'median': round(v[len(v) // 2], 1), 'mean': round(sum(v) / len(v), 1),
                                 'p90': round(v[int(len(v) * 0.9)], 1), 'pairs': len(v)}

    # without one national range per name: every place numbered on its own from the bottom of its own range
    alone = collections.defaultdict(set)
    clash = 0
    for it in lieux.items:
        nb = per_lieu.get(f"{it['zone']}-{it['index']:04d}", 0)
        if not nb:
            continue
        d = E.family_digits([nb])
        lo = 10 ** (d - 1)
        span = E.block_size(nb, d)
        for i in range(nb):
            alone[(it['nameKey'], lo + int((i + 0.5) * span / nb))].add(f"{it['zone']}-{it['index']}")
    clash = sum(len(v) for v in alone.values() if len(v) > 1)
    out['withoutNationalRanges'] = {'codesSharingTheirHomeForm': clash}
    rep = {k for k, f in lieux.families.items() if len(f['lieux']) > 1}
    out['codesInRepeatedNames'] = sum(per_lieu.get(f"{it['zone']}-{it['index']:04d}", 0) for it in lieux.items if it['nameKey'] in rep)

    # footprint sources by zone
    src = collections.defaultdict(collections.Counter)
    for z in ZONES:
        for r in rows(f'structures/{z}.csv.gz'):
            src[z][r['data']] += 1
    def pct(c, keys):
        t = sum(c[k] for k in keys)
        return [f'{100 * c[k] / t:.1f}' for k in keys]
    order_z = sorted(ZONES, key=lambda z: -sum(src[z].values()))
    write('sources.dat', 'zone structures osm ml single satellite concession enclosure',
          [(z, sum(src[z].values()), *pct(src[z], ['osm', 'ml']),
            *pct(rule[z], ['single', 'satellite', 'rural-concession', 'enclosure'])) for z in order_z])
    out['footprintSources'] = {z: dict(src[z]) for z in ZONES}

    # the Plus Code cells around Bakau 2389's entrance, and the footprints near it
    lat0, lng0 = 13.47841, -16.6787355
    full = E.plus_code(lat0, lng0)
    s10, w10, n10, e10 = E.plus_decode(full[:11])
    s11, w11, n11, e11 = E.plus_decode(full)
    my = 110574.0
    mx = 111320.0 * math.cos(math.radians(lat0))
    polys = []
    for r in rows('structures/KMC.csv.gz'):
        m_ = re.search(r'\(\(\(?([^()]*)\)', r['footprint_wkt'])
        if not m_:
            continue
        pts = [tuple(map(float, p.split())) for p in m_.group(1).split(',')]
        if any(abs((y - lat0) * my) < 45 and abs((x - lng0) * mx) < 45 for x, y in pts):
            polys += [(f'{(x - w10) * mx:.2f}', f'{(y - s10) * my:.2f}') for x, y in pts] + [('nan', 'nan')]
    write('spot-footprints.dat', 'x y', polys)
    out['spot'] = {'code': full, 'cell10': [round((e10 - w10) * mx, 2), round((n10 - s10) * my, 2)],
                   'cell11': [round((w11 - w10) * mx, 2), round((s11 - s10) * my, 2),
                              round((e11 - w10) * mx, 2), round((n11 - s10) * my, 2)],
                   'gate': [round((lng0 - w10) * mx, 2), round((lat0 - s10) * my, 2)]}

    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
