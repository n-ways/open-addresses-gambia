"""Geometry the server needs beyond the engine: footprints as WKT, distances
in metres, and the overlap test that stops a building getting a second code.

Coordinates are (lng, lat) in degrees, as in WKT and GeoJSON. Distances are
measured on the WGS 84 / UTM zone 28N grid of the engine (E.utm_forward); over
the few metres these rules look at, the grid and the ellipsoid agree to the
millimetre.
"""
import math
import re

from .engine import E

_NUM = re.compile(r'-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?')


def parse_wkt(wkt):
    """POLYGON or MULTIPOLYGON text -> list of polygons, each a list of rings
    (outer first, then holes), each ring a list of (lng, lat)."""
    if not wkt:
        return []
    t = wkt.strip()
    head = t[:t.index('(')].strip().upper()
    body = t[t.index('('):]
    if head == 'POLYGON':
        polys = [body]
    elif head == 'MULTIPOLYGON':
        inner = body.strip()[1:-1]
        polys, depth, start = [], 0, None
        for i, ch in enumerate(inner):
            if ch == '(':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    polys.append(inner[start:i + 1])
    else:
        raise ValueError(f'unsupported geometry {head}')
    out = []
    for p in polys:
        rings = []
        for r in re.findall(r'\(([^()]*)\)', p):
            nums = [float(x) for x in _NUM.findall(r)]
            ring = list(zip(nums[0::2], nums[1::2]))
            if len(ring) > 1 and ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) >= 3:
                rings.append(ring)
        if rings:
            out.append(rings)
    return out


def ring_wkt(ring):
    """A closed POLYGON of one ring, seven decimals (the issuer's format)."""
    pts = list(ring) + [ring[0]]
    return 'POLYGON((' + ','.join(f'{x:.7f} {y:.7f}' for x, y in pts) + '))'


def bbox(polys):
    xs = [x for p in polys for r in p for x, _ in r]
    ys = [y for p in polys for r in p for _, y in r]
    return min(xs), min(ys), max(xs), max(ys)


def contains(polys, lng, lat):
    for rings in polys:
        if E.Zones._in_ring(lng, lat, rings[0]) and not any(E.Zones._in_ring(lng, lat, h) for h in rings[1:]):
            return True
    return False


def metres(lat1, lng1, lat2, lng2):
    """Distance between two points on the UTM grid."""
    e1, n1 = E.utm_forward(lat1, lng1)
    e2, n2 = E.utm_forward(lat2, lng2)
    return math.hypot(e2 - e1, n2 - n1)


def dist_m(lat1, lng1, lat2, lng2):
    """The issuer's short-range distance (an equirectangular approximation,
    used for the 80 m door rule and outline perimeters)."""
    dy = (lat2 - lat1) * 111320
    dx = (lng2 - lng1) * 111320 * math.cos((lat1 + lat2) / 2 * math.pi / 180)
    return math.hypot(dx, dy)


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def footprint_distance(polys, lat, lng):
    """Metres from a point to a footprint: 0 inside it, else to its nearest edge."""
    if contains(polys, lng, lat):
        return 0.0
    pe, pn = E.utm_forward(lat, lng)
    best = math.inf
    for rings in polys:
        for ring in rings:
            pts = [E.utm_forward(y, x) for x, y in ring]
            for i in range(len(pts)):
                a, b = pts[i - 1], pts[i]
                best = min(best, _seg_dist(pe, pn, a[0], a[1], b[0], b[1]))
    return best


def ring_area_m2(ring):
    """Area of a ring of (lng, lat) in square metres (shoelace on the UTM grid)."""
    if len(ring) < 3:
        return 0.0
    pts = [E.utm_forward(y, x) for x, y in ring]
    a = 0.0
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[(i + 1) % len(pts)]
        a += xi * yj - xj * yi
    return abs(a) / 2


def ring_perimeter_m(ring):
    return sum(dist_m(ring[i][1], ring[i][0], ring[(i + 1) % len(ring)][1], ring[(i + 1) % len(ring)][0])
               for i in range(len(ring)))


# ---------------------------------------------------------------- overlap
# Two footprints are the same building when their intersection covers more
# than half of the smaller one. Areas are compared in degrees squared, the
# ratio being the same as in metres over a building's extent.

def _signed(ring):
    return sum(ring[i - 1][0] * ring[i][1] - ring[i][0] * ring[i - 1][1] for i in range(len(ring))) / 2


def planar_area(ring):
    return abs(_signed(ring))


def _triangulate(ring):
    """Ear clipping of a simple ring into triangles (counter-clockwise)."""
    pts = list(ring)
    if _signed(pts) < 0:
        pts.reverse()
    idx = list(range(len(pts)))
    tris = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def inside(p, a, b, c):
        return cross(a, b, p) >= 0 and cross(b, c, p) >= 0 and cross(c, a, p) >= 0

    guard = 0
    while len(idx) > 3 and guard < 10 * len(pts) ** 2:
        guard += 1
        n = len(idx)
        for k in range(n):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if cross(a, b, c) <= 0:
                continue
            if any(inside(pts[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((a, b, c))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(pts[i] for i in idx))
    elif len(idx) > 3:   # a self-touching ring: fan the rest
        for k in range(1, len(idx) - 1):
            tris.append((pts[idx[0]], pts[idx[k]], pts[idx[k + 1]]))
    return tris


def _clip(subject, clip):
    """Sutherland-Hodgman: subject polygon clipped by a convex counter-clockwise polygon."""
    out = list(subject)
    for i in range(len(clip)):
        a, b = clip[i - 1], clip[i]
        inp, out = out, []
        if not inp:
            break

        def side(p):
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])

        for j in range(len(inp)):
            p, q = inp[j - 1], inp[j]
            sp, sq = side(p), side(q)
            if sq >= 0:
                if sp < 0:
                    t = sp / (sp - sq)
                    out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
                out.append(q)
            elif sp >= 0:
                t = sp / (sp - sq)
                out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def _ring_inter(r1, r2):
    t2 = _triangulate(r2)
    total = 0.0
    for t in _triangulate(r1):
        for u in t2:
            c = _clip(t, u)
            if len(c) >= 3:
                total += planar_area(c)
    return total


def poly_area(polys):
    return sum(planar_area(r[0]) - sum(planar_area(h) for h in r[1:]) for r in polys)


def intersection_area(polys, ring):
    """Area shared by a footprint (polygons with holes) and a simple ring."""
    total = 0.0
    for rings in polys:
        total += _ring_inter(rings[0], ring) - sum(_ring_inter(h, ring) for h in rings[1:])
    return max(0.0, total)


def same_building(polys, ring):
    a, b = poly_area(polys), planar_area(ring)
    return intersection_area(polys, ring) > 0.5 * min(a, b)
