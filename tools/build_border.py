#!/usr/bin/env python3
"""The national border of The Gambia (engine/SPEC.md section 2.1), and the
check that no code lies across it.

  tools/build_border.py build <gambia.osm.pbf> [--full FILE]
        the OpenStreetMap admin_level=2 relation of The Gambia (ISO3166-1=GM),
        its ways joined into rings, simplified by Douglas-Peucker at 50 m on the
        UTM 28N grid -> engine/data/border.geojson (--full also writes the ring
        unsimplified, for `check --border`)
  tools/build_border.py check [--registry registry] [--border FILE]
        counts the codes whose entrance lies more than 300 m outside the border

Reading the extract needs duckdb (its spatial extension, ST_ReadOSM), as
tools/issue_registry.py does. The simplified file records how far it strays
from the true line at most (maxDeviationM, measured both ways: every vertex of
the true line to the simplified one, and the simplified line, sampled every
10 m, to the true one); the engine's Border takes that off the 300 m, so a
point it accepts is never more than 300 m outside the true border.
"""
import argparse
import csv
import gzip
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, 'engine', 'data', 'border.geojson')
sys.path.insert(0, os.path.join(REPO, 'engine', 'reference'))
import gm_engine as E  # noqa: E402

ISO = 'GM'
SIMPLIFY_M = 50.0
SAMPLE_M = 10.0


def read_relation(pbf):
    """(relation id, [(role, [(lon, lat), ...]) per member way])."""
    sql = f"""
LOAD spatial;
CREATE TABLE o AS SELECT kind, id, tags, refs, ref_roles, ref_types, lat, lon FROM ST_ReadOSM('{pbf}');
CREATE TABLE r AS SELECT id, refs, ref_roles, ref_types FROM o
  WHERE kind = 'relation' AND tags['boundary'] = 'administrative' AND tags['admin_level'] = '2' AND tags['ISO3166-1'] = '{ISO}';
CREATE TABLE m AS SELECT r.id AS rid, unnest(generate_series(1, len(r.refs))) AS pos, unnest(r.refs) AS wid,
  unnest(r.ref_roles) AS role, unnest(r.ref_types) AS t FROM r;
CREATE TABLE w AS SELECT m.rid, m.pos, m.role, unnest(generate_series(1, len(o.refs))) AS k, unnest(o.refs) AS nid
  FROM m JOIN o ON o.kind = 'way' AND o.id = m.wid WHERE m.t = 'way';
COPY (SELECT w.rid, w.pos, w.role, w.k, n.lon, n.lat FROM w JOIN o n ON n.kind = 'node' AND n.id = w.nid
      ORDER BY w.pos, w.k) TO '/dev/stdout' (HEADER, DELIMITER ',');
"""
    r = subprocess.run(['duckdb', '-csv'], input=sql, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit('duckdb failed: ' + r.stderr[-3000:])
    rows = list(csv.DictReader(r.stdout.splitlines()))
    if not rows:
        sys.exit(f'no admin_level=2 relation with ISO3166-1={ISO} in {pbf}')
    rids = {row['rid'] for row in rows}
    if len(rids) != 1:
        sys.exit(f'expected one border relation, found {sorted(rids)}')
    ways = {}
    for row in rows:
        ways.setdefault(int(row['pos']), (row['role'] or 'outer', []))[1].append((float(row['lon']), float(row['lat'])))
    return rids.pop(), [ways[p] for p in sorted(ways)]


def join_rings(parts):
    """Member ways joined end to end into closed rings."""
    open_, rings = [list(p) for p in parts if len(p) > 1], []
    while open_:
        ring = open_.pop(0)
        while ring[0] != ring[-1]:
            for i, p in enumerate(open_):
                if p[0] == ring[-1]:
                    ring += p[1:]
                elif p[-1] == ring[-1]:
                    ring += p[-2::-1]
                elif p[-1] == ring[0]:
                    ring = p[:-1] + ring
                elif p[0] == ring[0]:
                    ring = p[:0:-1] + ring
                else:
                    continue
                open_.pop(i)
                break
            else:
                sys.exit(f'the border does not close: a ring stops at {ring[-1]}')
        rings.append(ring)
    return rings


def _seg_d(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def douglas_peucker(pts, tol):
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        best, k = -1.0, None
        for m in range(i + 1, j):
            d = _seg_d(pts[m], pts[i], pts[j])
            if d > best:
                best, k = d, m
        if k is not None and best > tol:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [p for p, f in zip(pts, keep) if f]


def simplify_ring(ring, tol):
    """A closed ring (UTM) simplified, split at its first vertex and the vertex
    farthest from it so both halves are open lines."""
    pts = ring[:-1]
    far = max(range(len(pts)), key=lambda i: math.hypot(pts[i][0] - pts[0][0], pts[i][1] - pts[0][1]))
    a = douglas_peucker(pts[:far + 1], tol)
    b = douglas_peucker(pts[far:] + [pts[0]], tol)
    out = a + b[1:]
    return out if len(out) >= 4 else ring


class SegIndex:
    def __init__(self, rings, cell=500.0):
        self.cell, self.segs, self.grid = cell, [], {}
        for ring in rings:
            for i in range(1, len(ring)):
                self.segs.append((ring[i - 1], ring[i]))
        for k, (a, b) in enumerate(self.segs):
            for gx in range(int(min(a[0], b[0]) // cell), int(max(a[0], b[0]) // cell) + 1):
                for gy in range(int(min(a[1], b[1]) // cell), int(max(a[1], b[1]) // cell) + 1):
                    self.grid.setdefault((gx, gy), []).append(k)

    def dist(self, p):
        gx, gy = int(p[0] // self.cell), int(p[1] // self.cell)
        for r in range(1, 50):
            best = math.inf
            for x in range(gx - r, gx + r + 1):
                for y in range(gy - r, gy + r + 1):
                    for k in self.grid.get((x, y), ()):
                        best = min(best, _seg_d(p, *self.segs[k]))
            if best <= (r - 0.5) * self.cell:   # nothing beyond the searched square can be nearer
                return best
        return best


def deviation(true_rings, simple_rings):
    t, s = SegIndex(true_rings), SegIndex(simple_rings)
    worst = max(s.dist(p) for ring in true_rings for p in ring)
    for ring in simple_rings:
        for i in range(1, len(ring)):
            a, b = ring[i - 1], ring[i]
            n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) // SAMPLE_M))
            for j in range(n + 1):
                worst = max(worst, t.dist((a[0] + (b[0] - a[0]) * j / n, a[1] + (b[1] - a[1]) * j / n)))
    return worst


def to_geo(ring):
    out = []
    for e, n in ring:
        lat, lon = E.utm_inverse(e, n)
        out.append([round(lon, 5), round(lat, 5)])
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def build(pbf, full=None):
    rid, members = read_relation(os.path.abspath(pbf))
    roles = {r for r, _ in members}
    if roles - {'outer', 'inner'}:
        sys.exit(f'unexpected member roles {sorted(roles)}')
    outer = join_rings([p for r, p in members if r == 'outer'])
    inner = join_rings([p for r, p in members if r == 'inner'])
    utm = lambda ring: [E.utm_forward(lat, lon) for lon, lat in ring]  # noqa: E731
    t_out, t_in = [utm(r) for r in outer], [utm(r) for r in inner]
    s_out = [simplify_ring(r, SIMPLIFY_M) for r in t_out]
    s_in = [simplify_ring(r, SIMPLIFY_M) for r in t_in]
    # Each inner ring goes with the outer ring holding it.
    polys, fpolys = [[to_geo(r)] for r in s_out], [[r] for r in outer]
    for h, hs, hg in zip(t_in, s_in, inner):
        x, y = h[0]
        for k, r in enumerate(t_out):
            if E.Zones._in_ring(x, y, r):
                polys[k].append(to_geo(hs))
                fpolys[k].append(hg)
                break
    geo_simple = [[[E.utm_forward(lat, lon) for lon, lat in ring] for ring in poly] for poly in polys]
    dev = deviation(t_out + t_in, [r for poly in geo_simple for r in poly])
    vertices = sum(len(r) for p in polys for r in p)
    doc = {'type': 'Feature',
           'properties': {'country': ISO, 'source': f'OpenStreetMap relation/{rid} (admin_level=2), ODbL, © OpenStreetMap contributors',
                          'simplifiedM': SIMPLIFY_M, 'maxDeviationM': round(dev, 1), 'borderM': E.BORDER_M,
                          'limitM': E.BORDER_M - math.ceil(round(dev, 1))},
           'geometry': {'type': 'MultiPolygon', 'coordinates': polys}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, separators=(',', ':'))
        f.write('\n')
    if full:
        with open(full, 'w', encoding='utf-8') as f:
            json.dump({'type': 'Feature', 'properties': {'country': ISO, 'source': f'OpenStreetMap relation/{rid}', 'maxDeviationM': 0},
                       'geometry': {'type': 'MultiPolygon', 'coordinates': fpolys}}, f, separators=(',', ':'))
    print(f'relation {rid}: {sum(len(r) for r in outer + inner)} vertices -> {vertices}, '
          f'largest deviation {dev:.1f} m, limit {doc["properties"]["limitM"]:.0f} m, {os.path.getsize(OUT):,} bytes')


def check(registry, border):
    b = E.Border(border) if border else E.Border()
    keys = sorted(fn[:-7] for fn in os.listdir(registry) if fn.endswith('.csv.gz') and fn != 'lieux.csv.gz')
    total = abroad = 0
    first = []
    for k in keys:
        with gzip.open(os.path.join(registry, f'{k}.csv.gz'), 'rt', encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                total += 1
                if not b.holds(float(row['entrance_lat']), float(row['entrance_lng'])):
                    abroad += 1
                    if len(first) < 10:
                        first.append(row['machine'])
    print(f'{abroad} of {total} codes have their entrance more than {b.limit:.0f} m outside the border'
          + (f' (first: {", ".join(first)})' if first else ''))
    return abroad


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('build')
    p.add_argument('pbf')
    p.add_argument('--full')
    c = sub.add_parser('check')
    c.add_argument('--registry', default=os.path.join(REPO, 'registry'))
    c.add_argument('--border', help='a border file (default engine/data/border.geojson)')
    a = ap.parse_args()
    if a.cmd == 'build':
        build(a.pbf, a.full)
    else:
        sys.exit(1 if check(a.registry, a.border) else 0)


if __name__ == '__main__':
    main()
