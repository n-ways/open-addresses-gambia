#!/usr/bin/env python3
"""N-Ways Addressing for The Gambia: reference engine (standard library only).

This file is the executable definition of engine/SPEC.md. Where the two
disagree, the SPEC wins and this file is a bug.

  python3 gm_engine.py find   "Bakau 2512"              resolve a home code (no context needed)
  python3 gm_engine.py check  "GM-KMC-0012-2512-4"      validate the machine form
  python3 gm_engine.py plus   13.4549 -16.5790          the government's Plus Code of a point
  python3 gm_engine.py vectors                          print the test vectors
  python3 gm_engine.py selftest                         run every check (and compare vectors.json)
  python3 -m unittest test_gm                           the tests

A home code (SPEC section 3) has three forms of one identity:
  home      Bakau 2512                place word + 3-5 digit number; unique in all of The
                                      Gambia on its own (one national range per name)
  written   BAKAU 2512 · KANIFING     plates and forms: + zone name (information only)
  machine   GM-KMC-0012-2512-4        APIs and QR codes: zone key, place index, number, check digit
The official address is the government's: the Plus Code of the National
Digital Addressing Policy (2023), shown first, the home code beside it. The
check digit is Damm's (every single wrong digit and every swap of two
adjacent digits is caught). It exists only in the machine form: plates,
forms and anything people read show the name and number alone.
"""
import json, math, os, re, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, '..', '..', 'model')


def _load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------- check digit (Damm)
DAMM = ['0317598642', '7092154863', '4206871359', '1750983426', '6123045978',
        '3674209581', '5869720134', '8945362017', '9438617205', '2581436790']


def damm(digits):
    """Damm's check digit of a digit string: catches every single wrong digit
    and every swap of adjacent digits."""
    i = 0
    for ch in digits:
        i = int(DAMM[i][int(ch)])
    return i


def address_check(family_id, number):
    """SPEC 4: the check digit binds the name (its family id) and the number;
    the place follows from the frozen block table."""
    return damm(f'{family_id:05d}{number:05d}')


# ---------------------------------------------------------------- UTM zone 28N
# WGS 84 / UTM zone 28N (EPSG:32628): Kruger series to n^4 (Karney 2011),
# sub-millimetre across The Gambia (the eastern tip lies 1.25 degrees east of
# the central meridian, -15).
A_ = 6378137.0
F_ = 1 / 298.257223563
K0, LON0, FE = 0.9996, math.radians(-15.0), 500000.0
_n = F_ / (2 - F_)
_A = A_ / (1 + _n) * (1 + _n ** 2 / 4 + _n ** 4 / 64)
_al = [_n / 2 - 2 * _n ** 2 / 3 + 5 * _n ** 3 / 16 + 41 * _n ** 4 / 180,
       13 * _n ** 2 / 48 - 3 * _n ** 3 / 5 + 557 * _n ** 4 / 1440,
       61 * _n ** 3 / 240 - 103 * _n ** 4 / 140,
       49561 * _n ** 4 / 161280]
_be = [_n / 2 - 2 * _n ** 2 / 3 + 37 * _n ** 3 / 96 - _n ** 4 / 360,
       _n ** 2 / 48 + _n ** 3 / 15 - 437 * _n ** 4 / 1440,
       17 * _n ** 3 / 480 - 37 * _n ** 4 / 840,
       4397 * _n ** 4 / 161280]
_de = [2 * _n - 2 * _n ** 2 / 3 - 2 * _n ** 3 + 116 * _n ** 4 / 45,
       7 * _n ** 2 / 3 - 8 * _n ** 3 / 5 - 227 * _n ** 4 / 45,
       56 * _n ** 3 / 15 - 136 * _n ** 4 / 35,
       4279 * _n ** 4 / 630]
_e2n = 2 * math.sqrt(_n) / (1 + _n)


def utm_forward(lat, lon):
    phi, lam = math.radians(lat), math.radians(lon) - LON0
    t = math.sinh(math.atanh(math.sin(phi)) - _e2n * math.atanh(_e2n * math.sin(phi)))
    xi_, eta_ = math.atan2(t, math.cos(lam)), math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    xi, eta = xi_, eta_
    for j, a in enumerate(_al, 1):
        xi += a * math.sin(2 * j * xi_) * math.cosh(2 * j * eta_)
        eta += a * math.cos(2 * j * xi_) * math.sinh(2 * j * eta_)
    return FE + K0 * _A * eta, K0 * _A * xi


def utm_inverse(e, n):
    xi, eta = n / (K0 * _A), (e - FE) / (K0 * _A)
    xi_, eta_ = xi, eta
    for j, b in enumerate(_be, 1):
        xi_ -= b * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
        eta_ -= b * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
    chi = math.asin(math.sin(xi_) / math.cosh(eta_))
    phi = chi + sum(d * math.sin(2 * j * chi) for j, d in enumerate(_de, 1))
    lam = LON0 + math.atan2(math.sinh(eta_), math.cos(xi_))
    return math.degrees(phi), math.degrees(lam)


# ---------------------------------------------------------------- zones
class Zones:
    """The 7 frozen code zones (zones.json) and their outlines (zones.geojson)."""

    def __init__(self, model=MODEL):
        meta = _load_json(os.path.join(model, 'zones.json'))['zones']
        self.by_key = {z['key']: z for z in meta}
        self.by_index = {z['index']: z for z in meta}
        self.shapes = []
        gj = _load_json(os.path.join(model, 'zones.geojson'))
        for f in gj['features']:
            for poly in f['geometry']['coordinates']:
                xs = [p[0] for p in poly[0]]
                ys = [p[1] for p in poly[0]]
                self.shapes.append((f['properties']['key'], (min(xs), min(ys), max(xs), max(ys)), poly))

    @staticmethod
    def _in_ring(x, y, ring):
        inside = False
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
        return inside

    def lookup(self, lat, lon):
        """The zone holding a point (the lowest index on an overlap), else the
        zone with the nearest outline vertex within 2 km (the river banks, the
        coast), else None (outside The Gambia)."""
        hits = []
        for key, (x0, y0, x1, y1), poly in self.shapes:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and self._in_ring(lon, lat, poly[0]) \
                    and not any(self._in_ring(lon, lat, h) for h in poly[1:]):
                hits.append(self.by_key[key]['index'])
        if hits:
            return self.by_index[min(hits)]['key']
        best, bestd = None, 2000.0
        e0, n0 = utm_forward(lat, lon)
        for key, (x0, y0, x1, y1), poly in self.shapes:
            if not (x0 - 0.03 <= lon <= x1 + 0.03 and y0 - 0.03 <= lat <= y1 + 0.03):
                continue
            for x, y in poly[0]:
                if abs(x - lon) < 0.03 and abs(y - lat) < 0.03:
                    e, n = utm_forward(y, x)
                    d = math.hypot(e - e0, n - n0)
                    if d < bestd:
                        best, bestd = key, d
        return best


# ---------------------------------------------------------------- the national border (SPEC 2.1)
BORDER = os.path.join(HERE, '..', 'data', 'border.geojson')
BORDER_M = 300.0     # how far outside the national border an entrance may lie


class Border:
    """The national border (engine/data/border.geojson): the OpenStreetMap
    admin_level=2 boundary of The Gambia, simplified. A building more than
    BORDER_M outside it is in a neighbouring country and never has a code,
    whatever the zone outlines say. The file records the largest distance
    between the simplified line and the true one (maxDeviationM); the limit
    applied here is BORDER_M less that deviation, so nothing it accepts lies
    more than BORDER_M outside the true border."""

    CELL = 1000.0

    def __init__(self, path=BORDER, limit_m=None):
        gj = _load_json(path)
        props = gj.get('properties') or {}
        geom = gj['geometry'] if gj.get('type') == 'Feature' else gj
        polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
        dev = float(props.get('maxDeviationM', 0.0))
        self.limit = float(limit_m) if limit_m is not None else BORDER_M - math.ceil(dev)
        self.segs = []
        for poly in polys:
            for ring in poly:
                pts = [utm_forward(y, x) for x, y in ring]
                if pts and pts[0] == pts[-1]:
                    pts = pts[:-1]
                for i in range(len(pts)):
                    self.segs.append((pts[i - 1], pts[i]))
        c, r = self.CELL, self.limit
        self.bands = {}     # horizontal band -> segments crossing it (inside test)
        self.cells = {}     # grid cell -> segments within the limit of it (distance)
        for k, ((ax, ay), (bx, by)) in enumerate(self.segs):
            for b in range(int(min(ay, by) // c), int(max(ay, by) // c) + 1):
                self.bands.setdefault(b, []).append(k)
            for gx in range(int((min(ax, bx) - r) // c), int((max(ax, bx) + r) // c) + 1):
                for gy in range(int((min(ay, by) - r) // c), int((max(ay, by) + r) // c) + 1):
                    self.cells.setdefault((gx, gy), []).append(k)

    def _inside(self, e, n):
        inside = False
        for k in self.bands.get(int(n // self.CELL), ()):
            (ax, ay), (bx, by) = self.segs[k]
            if (ay > n) != (by > n) and e < (bx - ax) * (n - ay) / (by - ay) + ax:
                inside = not inside
        return inside

    def outside_m(self, lat, lon):
        """0 inside the border; else the metres to it, or infinity beyond the limit."""
        e, n = utm_forward(lat, lon)
        if self._inside(e, n):
            return 0.0
        best = math.inf
        for k in self.cells.get((int(e // self.CELL), int(n // self.CELL)), ()):
            (ax, ay), (bx, by) = self.segs[k]
            dx, dy = bx - ax, by - ay
            L = dx * dx + dy * dy
            t = 0.0 if L == 0 else max(0.0, min(1.0, ((e - ax) * dx + (n - ay) * dy) / L))
            best = min(best, math.hypot(e - ax - t * dx, n - ay - t * dy))
        return best if best <= self.limit else math.inf

    def holds(self, lat, lon):
        """True for a point inside the border or within the limit of it."""
        return self.outside_m(lat, lon) <= self.limit


# ---------------------------------------------------------------- the government's Plus Codes (SPEC 5)
OLC = '23456789CFGHJMPQRVWX'


def plus_code(lat, lon, length=11):
    """Open Location Code, the national digital address (MoCDE, 2023):
    10 characters (about 14 m) or 11 (about 3.5 x 2.8 m)."""
    lat = min(max(lat, -90), 90)
    lon = (lon + 180) % 360 - 180
    lat_v = math.floor(round((lat + 90) * 25000000, 6))
    lon_v = math.floor(round((lon + 180) * 8192000, 6))
    lat_v = min(lat_v, 180 * 25000000 - 1)
    code = ''
    if length > 10:
        for _ in range(5):
            code = OLC[(lat_v % 5) * 4 + lon_v % 4] + code
            lat_v //= 5
            lon_v //= 4
    else:
        lat_v //= 3125
        lon_v //= 1024
    for _ in range(5):
        code = OLC[lon_v % 20] + code
        code = OLC[lat_v % 20] + code
        lat_v //= 20
        lon_v //= 20
    return code[:8] + '+' + code[8:length]


def short_plus(lat, lon):
    """The short form people write in The Gambia (\"F889+WWH\"): the last 4+3 characters."""
    return plus_code(lat, lon)[4:]


def plus_decode(code):
    """The cell of a full Plus Code: (south, west, north, east) in degrees.
    Raises ValueError for anything that is not a full code."""
    c = code.strip().upper()
    if c.count('+') != 1 or c.index('+') != 8:
        raise ValueError('not a full Plus Code')
    digits = c.replace('+', '')
    if not digits or any(ch not in OLC for ch in digits) or len(digits) not in (8, 10, 11, 12, 13, 14, 15):
        raise ValueError('not a full Plus Code')
    lat, lon, res = -90.0, -180.0, 20.0
    for i in range(0, min(len(digits), 10), 2):
        lat += OLC.index(digits[i]) * res
        lon += OLC.index(digits[i + 1]) * res
        res /= 20
    lat_res, lon_res = res * 20, res * 20
    for ch in digits[10:]:
        lat_res, lon_res = lat_res / 5, lon_res / 4
        k = OLC.index(ch)
        lat += (k // 4) * lat_res
        lon += (k % 4) * lon_res
    return lat, lon, lat + lat_res, lon + lon_res


def plus_recover(short, ref_lat, ref_lon):
    """A short Plus Code ("C8W5+GV4") made whole with a reference point (the
    town written after it), by the Open Location Code rule: the nearest cell
    with that suffix to the reference."""
    s = short.strip().upper()
    if '+' not in s:
        raise ValueError('not a Plus Code')
    pad = 8 - s.index('+')
    if pad <= 0:
        return s
    if pad % 2:
        raise ValueError('not a Plus Code')
    res = 20.0 ** (2 - pad / 2)
    full = plus_code(ref_lat, ref_lon)[:pad] + s
    south, west, north, east = plus_decode(full)
    clat, clon = (south + north) / 2, (west + east) / 2
    if ref_lat + res / 2 < clat and clat - res >= -90:
        clat -= res
    elif ref_lat - res / 2 > clat and clat + res <= 90:
        clat += res
    if ref_lon + res / 2 < clon:
        clon -= res
    elif ref_lon - res / 2 > clon:
        clon += res
    return plus_code(clat, clon, min(11, max(10, len(s) - 1 + pad)))


# ---------------------------------------------------------------- name keys (SPEC 3.3.1)
# English, Mandinka, Wolof, Fula and Jola spellings of one place must share
# one national range: Kerr / Ker / Keur, Sukuta / Sukkuta, Serrekunda /
# Serekunda / Serre Kunda, Jambanjelly / Jambajelly, Ndungu Kebbeh / Ndungu Kebbe.
_DROP_LEAD = {'the', 'village', 'of'}
_DROP_TAIL = {'no', 'number', 'village', 'ward'}


def fold(s):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
                    .lower().replace('-', ' ').replace("'", ' ').split())


def name_key(s):
    """The national name key of a place word: two names with one key share
    one national number range. Generous on purpose: names people confuse by
    ear or in spelling never get the same home code twice."""
    s = s.replace('ñ', 'ny').replace('Ñ', 'ny').replace('ŋ', 'ng').replace('Ŋ', 'ng')
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).lower()
    toks = re.sub(r"[-'’.()/,·]", ' ', s).split()
    while toks and (toks[-1].isdigit() or toks[-1] in _DROP_TAIL) and len(toks) > 1:
        toks.pop()
    while toks and toks[-1].isdigit():
        toks.pop()
    while len(toks) > 1 and toks[0] in _DROP_LEAD:
        toks.pop(0)
    toks = ['ker' if t in ('kerr', 'keur', 'kerre') else t for t in toks]
    s = ''.join(toks)
    for a, b in ((r'ou', 'u'), (r'oo', 'u'), (r'ee', 'i'), (r'dj', 'j'), (r'kh', 'k'), (r'ph', 'f'),
                 (r'th', 't'), (r'c(?=[eiy])', 's'), (r'ck', 'k'), (r'c', 'k'), (r'q', 'k'), (r'y', 'i'),
                 (r'h', '')):
        s = re.sub(a, b, s)
    s = re.sub(r'(.)\1+', r'\1', s)
    s = re.sub(r'(?<=..)[eh]$', '', s)
    return s


def name_numeral(s):
    toks = fold(s).split()
    return toks[-1] if toks and toks[-1].isdigit() else ''


# ---------------------------------------------------------------- plate names (SPEC 3.2.1)
MAX_CHARS, MAX_WORDS = 12, 2
LINKING = {'and', 'of', 'the', 'de', 'la'}
GENERIC = {'village', 'ward', 'town', 'settlement', 'area', 'layout', 'quarters', 'island', 'islands', 'point', 'wharf',
           'phase', 'roundabout'}


def split_brackets(name):
    """'Busura (Kunkujang)' -> ('Busura', ['Kunkujang']): a second name in brackets is an alias."""
    alts = [a.strip() for a in re.findall(r'\(([^)]*)\)', name) if a.strip()]
    main = re.sub(r'\s*\([^)]*\)\s*', ' ', name).strip() or (alts.pop(0) if alts else name)
    return ' '.join(main.split()), alts


def split_numeral(name):
    """'Brusubi Phase 1' -> ('Brusubi Phase', '1'); 'Bakoteh' -> ('Bakoteh', '')."""
    m = re.match(r'^(.*?\D)\s*(\d{1,2})$', name.strip())
    return (m.group(1).strip(' -'), str(int(m.group(2)))) if m and re.search(r'[^\W\d]', m.group(1)) else (name.strip(), '')


def plate_words(name):
    return [w for w in re.split(r'[\s-]+', name) if w and w.lower() not in LINKING and not w.isdigit()]


def plate_ok(plate):
    """At most 12 characters and 2 words; a trailing number (\"Bakoteh 2\") counts in the characters only."""
    return len(unicodedata.normalize('NFC', plate)) <= MAX_CHARS and len(plate_words(plate)) <= MAX_WORDS


def derive_plate(official, freq=None):
    """(plate, rule, needsCouncilChoice, candidates). Generic words go; a name
    that still doesn't fit keeps its most distinctive words (the rarest among
    all Gambian place names, freq: word -> count) as a provisional plate and
    goes to its council (the Area Council or Municipal Council): "Balanghar
    Kerjuri" -> "Kerjuri", since six villages are Balanghar something."""
    freq = freq or {}
    name = ' '.join(official.split())
    if plate_ok(name):
        return name, 'as-is', False, []
    stem, num = split_numeral(name)
    tail = f' {num}' if num else ''
    words = [w for w in stem.split() if w.lower() not in GENERIC]
    cleaned = ' '.join(words) + tail
    if words and plate_ok(cleaned):
        return cleaned, 'cleaned', False, []
    cands = []
    for i in range(len(words)):
        for j in range(i + 1, min(i + 2, len(words)) + 1):
            c = ' '.join(words[i:j]) + tail
            if plate_words(c) and plate_ok(c) and c not in cands:
                cands.append(c)
    rarity = lambda c: sum(freq.get(w.lower(), 1) for w in plate_words(c)) / max(1, len(plate_words(c)))
    cands.sort(key=lambda c: (rarity(c), -len(plate_words(c)), -len(c)))
    if cands:
        return cands[0], 'council', True, cands[:3]
    return cleaned[:MAX_CHARS].strip(), 'council', True, []


SPARE_SHARE = 0.10



def block_grain(d):
    """Blocks start and end on round numbers: tens in 3-digit ranges, hundreds in 4- and 5-digit ranges."""
    return 10 if d == 3 else 100


def block_size(n_compounds, d):
    g = block_grain(d)
    return max(g, -(-HEADROOM * n_compounds // g) * g)


def allocatable(d):
    return int(round((1 - SPARE_SHARE) * 9 * 10 ** (d - 1)))   # 810, 8,100, 81,000


def family_digits(compound_counts):
    """Smallest d in {3,4,5} whose national range holds a block for every lieu of
    the name (3x headroom each) and still keeps 10 % spare; None if 5 digits
    are not enough (the name then needs a qualifier, SPEC 3.3.4)."""
    for d in (3, 4, 5):
        if sum(block_size(n, d) for n in compound_counts) <= allocatable(d):
            return d
    return None


def allocate_families(items, frozen=None, qualifiers=None):
    """First issue (and every rebuild before it): group lieux by name key, give
    each name a 5-digit family id and one national range, and cut one block per
    lieu in (zone key, lieu index) order from the bottom of the range. Sets on
    every item: placeWord, nameKey, family, digits, blocks [[lo, hi]].

    frozen: a previous allocation {key: {'id', 'digits', 'blocks': {"ZONE/index": [[lo, hi], ...]}}};
    its families and blocks are kept exactly (SPEC 3.3.5) and only new lieux get
    new blocks from their name's spare space. qualifiers: {(zone, index): qualifier}
    for names that do not fit 5 digits (SPEC 3.3.4)."""
    qualifiers = qualifiers or {}
    frozen = frozen or {}
    fam = {}
    for it in items:
        if not plate_ok(it['name']) and not it.get('needsCouncilChoice'):
            raise ValueError(f"plate name {it['name']!r} is over 12 characters or 2 words (SPEC 3.2.1)")
        q = qualifiers.get((it['zone'], it['index']))
        it['placeWord'] = it['name'] + (f' {q}' if q else '')
        it['nameKey'] = name_key(it['placeWord'])
        fam.setdefault(it['nameKey'], []).append(it)
    next_id = max([f['id'] for f in frozen.values()], default=-1) + 1
    out = {}
    for key in sorted(fam):
        members = sorted(fam[key], key=lambda it: (it['zone'], it['index']))
        if key in frozen:
            fz = frozen[key]
            fid, d = fz['id'], fz['digits']
            blocks = {k: [list(b) for b in v] for k, v in fz['blocks'].items()}
        else:
            fid, next_id = next_id, next_id + 1
            d = family_digits([it['compounds'] for it in members])
            if d is None:
                raise ValueError(f'name {members[0]["name"]!r}: {len(members)} lieux do not fit 5 digits; '
                                 f'give the largest a qualifier (SPEC 3.3.4)')
            blocks = {}
        top = max([b[1] for bl in blocks.values() for b in bl], default=10 ** (d - 1) - 1)
        for it in members:
            k = f"{it['zone']}/{it['index']}"
            if k not in blocks:
                size = block_size(it['compounds'], d)
                if top + size > 10 ** d - 1:
                    raise ValueError(f'name {it["name"]!r}: no spare room left for {k}; it needs a qualifier')
                blocks[k] = [[top + 1, top + size]]
                top += size
            it['family'], it['digits'], it['blocks'] = fid, d, blocks[k]
        out[key] = {'id': fid, 'digits': d, 'blocks': blocks}
    return out

# ---------------------------------------------------------------- place words (lieux)
def in_blocks(lieu, number):
    return any(lo <= number <= hi for lo, hi in lieu['blocks'])


class Lieux:
    """The place-word inventory (model/lieux.json): per zone, an index, a name,
    aliases, a position, and its name family: the family id, the number length
    shared by every lieu of the name, and the lieu's block(s) of the name's
    national range (SPEC 3.3), all frozen at first issue."""

    def __init__(self, model=MODEL, items=None):
        p = os.path.join(model, 'lieux.json')
        if items is None:
            items = _load_json(p)['lieux'] if os.path.exists(p) else []
        self.items = items
        self.by_zone = {}
        self.families = {}   # name key -> {'id', 'digits', 'lieux': [...]}
        self.names = {}      # name key of a name or alias -> set of family keys
        for it in self.items:
            self._index(it)

    def _index(self, it):
        self.by_zone.setdefault(it['zone'], {})[it['index']] = it
        f = self.families.setdefault(it['nameKey'], {'id': it['family'], 'digits': it['digits'], 'lieux': []})
        f['lieux'].append(it)
        for nm in [it['placeWord']] + it.get('aliases', []):
            self.names.setdefault(name_key(nm), set()).add(it['nameKey'])

    def get(self, zone, index):
        return self.by_zone[zone][index]

    def holder(self, key, number):
        """The one lieu of name family `key` whose block holds `number`, or None."""
        for it in self.families.get(key, {}).get('lieux', ()):
            if in_blocks(it, number):
                return it
        return None

    def spare_top(self, key):
        f = self.families[key]
        return max(b[1] for it in f['lieux'] for b in it['blocks'])

    def add_block(self, lieu, size=None):
        """Give a lieu one more block from its name's spare space (SPEC 3.3.5):
        when a new same-named lieu appears, or a lieu's own block is used up.
        Existing blocks never move. Returns the block, or None when the name's
        range is full (a new lieu then needs a qualifier)."""
        f = self.families[lieu['nameKey']]
        d = f['digits']
        size = size or block_grain(d)
        top = self.spare_top(lieu['nameKey'])
        if top + size > 10 ** d - 1:
            return None
        b = [top + 1, top + size]
        lieu['blocks'].append(b)
        return b

    def add_lieu(self, it):
        """A lieu created after first issue (curation, Extension): it joins its
        name's family and gets a block from the spare space, or starts a new
        family with the next family id."""
        if not plate_ok(it.get('placeWord') or it['name']) and not it.get('needsCouncilChoice'):
            raise ValueError(f"plate name {it.get('placeWord') or it['name']!r} is over 12 characters or 2 words")
        it.update(placeWord=it.get('placeWord') or it['name'], blocks=[])
        it['nameKey'] = name_key(it['placeWord'])
        self.by_zone.setdefault(it['zone'], {})[it['index']] = it
        self.items.append(it)
        if it['nameKey'] in self.families:
            f = self.families[it['nameKey']]
            it['family'], it['digits'] = f['id'], f['digits']
            f['lieux'].append(it)
            if self.add_block(it, block_size(it.get('compounds', 1), f['digits'])) is None:
                raise ValueError(f"no spare room left in {it['placeWord']!r}: the new lieu needs a qualifier (SPEC 3.3.4)")
        else:
            it['family'] = max(f['id'] for f in self.families.values()) + 1
            it['digits'] = it.get('digits') or 3
            it['blocks'] = [[10 ** (it['digits'] - 1), 10 ** (it['digits'] - 1) + block_size(it.get('compounds', 1), it['digits']) - 1]]
            self.families[it['nameKey']] = {'id': it['family'], 'digits': it['digits'], 'lieux': [it]}
        for nm in [it['placeWord']] + it.get('aliases', []):
            self.names.setdefault(name_key(nm), set()).add(it['nameKey'])
        return it

    def nearest(self, zone, e, n):
        """SPEC 3.2: the nearest place of any kind within 2.5 km (a town centre
        is its town, not the village next to it: most Gambian towns have no
        neighbourhoods mapped), else a town or city within 10 km, else the nearest."""
        cands = list(self.by_zone.get(zone, {}).values())
        for kinds, lim in (({'neighbourhood', 'suburb', 'village', 'locality', 'extension', 'town', 'city'}, 2500),
                           ({'town', 'city'}, 10000), (None, 1e12)):
            pool = [(math.hypot(c['e'] - e, c['n'] - n), c['index'], c) for c in cands
                    if (kinds is None or c['kind'] in kinds)]
            pool = [x for x in pool if x[0] <= lim]
            if pool:
                return min(pool)[2]
        return None

    def add_extension(self, parent):
        """When a name's whole national range is used up, a full lieu continues as
        '<name> Extension' (SPEC 7.4): a new name, so a new family with its own
        national range; new index in the zone, same number length."""
        zl = self.by_zone[parent['zone']]
        it = {k: v for k, v in parent.items() if k not in ('blocks', 'family', 'nameKey')}
        plate = f"{parent['placeWord']} Extension"
        it.update(index=max(zl) + 1, name=plate, placeWord=plate,
                  officialName=f"{parent.get('officialName', parent['placeWord'])} Extension",
                  kind='extension', coverage=parent.get('coverage', 'nways'), aliases=[],
                  source=f"extension-of:{parent['index']}", needsCouncilChoice=False,
                  compounds=(parent['blocks'][0][1] - parent['blocks'][0][0] + 1) // HEADROOM)
        for k in ('plateCandidates', 'plateReason', 'plateSource', 'aliasesDropped'):
            it.pop(k, None)
        if not plate_ok(plate):
            # 'Kanifing Extension' is over 12 characters: provisional, the council names it (SPEC 3.2.1)
            it.update(plateRule='council', needsCouncilChoice=True, plateCandidates=[plate],
                      plateReason='an extension whose name is over the limit: the council chooses its plate name')
        else:
            it['plateRule'] = 'as-is'
        return self.add_lieu(it)



# ---------------------------------------------------------------- forms and decoding (SPEC 3.1, 3.4)
_ONES = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve',
         'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen']
_TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']


def en_number(n):
    """English words for 0-999, as a house number is read."""
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, u = divmod(n, 10)
        return _TENS[t] + ('' if u == 0 else '-' + _ONES[u])
    h, r = divmod(n, 100)
    return _ONES[h] + ' hundred' + ('' if r == 0 else ' and ' + en_number(r))


def en_pair(p):
    """A two-digit group the way phone numbers are read: '07' -> 'oh seven'."""
    return f'oh {_ONES[int(p[1])]}' if p[0] == '0' else en_number(int(p))


def group_number(n):
    s = str(n)
    return s if len(s) <= 4 else f'{s[:2]} {s[2:]}'


def say_number(n):
    s = str(n)
    if len(s) == 3:
        return en_number(n)                                   # three hundred and twelve
    if len(s) == 4:
        return f'{en_pair(s[:2])}, {en_pair(s[2:])}'         # twenty-five, twelve
    tail = en_number(int(s[2:])) if s[2] != '0' else 'oh ' + en_pair(s[3:])
    return f'{en_pair(s[:2])}, {tail}'                       # forty-five, one hundred and twenty-eight


def address_forms(zones, lieu, number):
    z = zones.by_key[lieu['zone']]
    chk = address_check(lieu['family'], number)
    place = lieu['placeWord']
    return {
        'officialName': lieu.get('officialName', lieu['name']),
        'home': f'{place} {group_number(number)}',
        'written': f"{place.upper()} {group_number(number)} · {z['name'].upper()}",
        'machine': f"GM-{z['key']}-{lieu['index']:04d}-{number}-{chk}",
        'spoken': f'{place}, {say_number(number)}',
    }


MACHINE_RE = re.compile(r'^\s*GM-([A-Z]{3})-(\d{4})-(\d{3,5})-(\d)\s*$', re.I)


def validate(code, lieux):
    m = MACHINE_RE.match(code)
    if not m:
        return False, 'not an N-Ways Gambia home code'
    key, li, num_, chk = m.group(1).upper(), int(m.group(2)), int(m.group(3)), int(m.group(4))
    if m.group(3)[0] == '0':
        return False, 'numbers have 3-5 digits and never start with 0'
    lieu = lieux.by_zone.get(key, {}).get(li)
    if lieu is None:
        return False, f'no place {li} in zone {key}'
    if len(m.group(3)) != lieu['digits'] or not in_blocks(lieu, num_):
        return False, f"{num_} is not a number of {lieu['placeWord']} (wrong place or number)"
    if address_check(lieu['family'], num_) != chk:
        return False, 'check digit does not match: a digit is wrong or two are swapped'
    return True, 'home code'


def find(text, zones, lieux):
    """Resolve a typed home code ('Bakau 2512', 'BAKAU 25 12 · KANIFING · 4')
    with no context. A zone name or check digit, if given, is only checked."""
    t = text.replace('·', ',')
    parts = [p.strip() for p in t.split(',') if p.strip()]
    chk = None
    zone_name = None
    if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) == 1:
        chk = int(parts.pop())
    if len(parts) >= 2:
        zone_name = fold(parts.pop())
    head = parts[0].split() if parts else []
    digits = ''
    while head and head[-1].isdigit():
        digits = head.pop() + digits
    if not (head and digits):
        return []
    zk = None
    if zone_name:
        keyed = {fold(z['name']): k for k, z in zones.by_key.items()}
        keyed.update({fold(k): k for k in zones.by_key})
        zk = keyed.get(zone_name) or next((k for nm, k in keyed.items() if nm.startswith(zone_name)), None)
    out = []
    for fk in sorted(lieux.names.get(name_key(' '.join(head)), ())):
        d = lieux.families[fk]['digits']
        if len(digits) < d or digits[-d] == '0':
            continue
        number, extra = int(digits[-d:]), digits[:-d]
        lieu = lieux.holder(fk, number)
        if lieu is None:
            continue
        if extra and extra != name_numeral(lieu['placeWord']):
            continue
        if zk and lieu['zone'] != zk:
            continue
        if chk is not None and address_check(lieu['family'], number) != chk:
            continue
        out.append((lieu['zone'], lieu, number))
    return out


# ---------------------------------------------------------------- Hilbert order
def hilbert_d(order, x, y):
    """Index of cell (x, y) on a Hilbert curve covering 2^order x 2^order cells."""
    d, s = 0, 1 << (order - 1)
    while s > 0:
        rx = 1 if x & s else 0
        ry = 1 if y & s else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        s >>= 1
    return d


def hilbert_key(zone, e, n, order=16):
    side = zone['frameMetres'] / (1 << order)
    x = min((1 << order) - 1, max(0, int((e - zone['originE']) / side)))
    y = min((1 << order) - 1, max(0, int((n - zone['originN']) / side)))
    return hilbert_d(order, x, y)

# ---------------------------------------------------------------- building profile
# Use classes (SPEC.md section 6). OSM building=* values first, then
# amenity/shop/office/tourism/religion tags, then N-Ways places inside the
# footprint, then shape and height. Each rule gives a confidence.
OSM_BUILDING = {
    'house': 'res.maison', 'detached': 'res.maison', 'semidetached_house': 'res.maison', 'bungalow': 'res.maison',
    'residential': 'res.maison', 'terrace': 'res.maison', 'apartments': 'res.immeuble', 'dormitory': 'res.immeuble',
    'hut': 'res.case', 'farm': 'res.concession',
    'commercial': 'com.bureau', 'office': 'com.bureau', 'retail': 'com.boutique', 'kiosk': 'com.boutique',
    'supermarket': 'com.boutique', 'warehouse': 'com.entrepot', 'storage_tank': 'ind.usine',
    'industrial': 'ind.usine', 'factory': 'ind.usine', 'manufacture': 'ind.usine',
    'hotel': 'hot.hotel', 'government': 'gov.admin', 'public': 'gov.admin', 'civic': 'gov.admin',
    'school': 'edu.ecole', 'kindergarten': 'edu.ecole', 'university': 'edu.universite', 'college': 'edu.universite',
    'hospital': 'san.hopital', 'clinic': 'san.centre', 'mosque': 'rel.mosquee', 'church': 'rel.eglise',
    'cathedral': 'rel.eglise', 'chapel': 'rel.eglise', 'religious': 'rel.mosquee', 'shrine': 'rel.mausolee',
    'train_station': 'tra.gare', 'transportation': 'tra.gare', 'hangar': 'tra.gare',
    'barn': 'agr.magasin', 'farm_auxiliary': 'agr.magasin', 'granary': 'agr.grenier', 'greenhouse': 'agr.ferme',
    'stable': 'agr.ferme', 'cowshed': 'agr.ferme', 'construction': 'chantier', 'ruins': 'ruine',
    'market': 'com.marche', 'service': 'ind.usine', 'garage': 'res.annexe', 'garages': 'com.entrepot',
    'toilets': 'res.annexe', 'shed': 'res.annexe', 'roof': 'com.marche', 'sports_hall': 'edu.ecole',
    'stadium': 'gov.admin', 'fire_station': 'gov.admin', 'military': 'gov.admin',
}
OSM_AMENITY = {
    'townhall': 'gov.admin', 'courthouse': 'gov.admin', 'police': 'gov.admin', 'post_office': 'gov.admin',
    'prison': 'gov.admin', 'fire_station': 'gov.admin', 'school': 'edu.ecole', 'kindergarten': 'edu.ecole',
    'university': 'edu.universite', 'college': 'edu.universite', 'hospital': 'san.hopital', 'clinic': 'san.centre',
    'doctors': 'san.centre', 'pharmacy': 'san.pharmacie', 'place_of_worship': 'rel.mosquee',
    'marketplace': 'com.marche', 'bank': 'com.bureau', 'fuel': 'com.station', 'restaurant': 'hot.restaurant',
    'fast_food': 'hot.restaurant', 'cafe': 'hot.restaurant', 'bus_station': 'tra.gare', 'ferry_terminal': 'tra.gare',
}
PLACES = {  # N-Ways places categories
    'shop': 'com.boutique', 'supermarket': 'com.boutique', 'phones': 'com.boutique', 'salon': 'com.boutique',
    'pos': 'com.boutique', 'office': 'com.bureau', 'bank': 'com.bureau', 'school': 'edu.ecole',
    'hospital': 'san.centre', 'pharmacy': 'san.pharmacie', 'food': 'hot.restaurant', 'fastfood': 'hot.restaurant',
    'cafe': 'hot.restaurant', 'bar': 'hot.restaurant', 'hotel': 'hot.hotel', 'mosque': 'rel.mosquee',
    'church': 'rel.eglise', 'market': 'com.marche', 'petrol': 'com.station', 'police': 'gov.admin',
    'motorpark': 'tra.gare', 'mechanic': 'com.atelier', 'vulcanizer': 'com.atelier', 'carwash': 'com.atelier',
}
GROUPS = {  # class -> top-level group used in statistics
    'res': 'residential', 'com': 'commercial', 'hot': 'hospitality', 'gov': 'government', 'edu': 'education',
    'san': 'health', 'rel': 'religious', 'ind': 'industrial', 'tra': 'transport', 'pec': 'fishing',
    'agr': 'agricultural', 'mix': 'mixed-use', 'chantier': 'under construction', 'ruine': 'ruin',
    'inconnu': 'unknown',
}
FLOOR_M = 3.0  # storey height used to turn a height into floors (R+n = floors - 1)


def num(v):
    try:
        return float(str(v).replace(',', '.').split(';')[0].strip().rstrip('m').strip())
    except (TypeError, ValueError):
        return None


def size_profile(area, perimeter, h_ml, osm_height, osm_levels, h_measured=False):
    """Height, floors and floor area, with the source of each.

    Only measured heights count: OSM height, OSM building:levels, or a
    machine-learned height flagged as measured (h_measured). The heights that
    come with the machine-learned footprints of The Gambia are rendering
    placeholders, not measurements, so they are ignored and the height is
    unknown; floors then default to 1 with source 'default' (low confidence).
    """
    lv, hh = num(osm_levels), num(osm_height)
    if hh and 2 <= hh <= 250:
        height, hsrc = hh, 'osm:height'
    elif lv and 1 <= lv <= 60:
        height, hsrc = lv * FLOOR_M, 'osm:building:levels'
    elif h_measured and h_ml and h_ml > 0:
        height, hsrc = h_ml, 'ml:height'
    else:
        height, hsrc = None, None
    if lv and 1 <= lv <= 60:
        floors, fsrc = int(lv), 'osm:building:levels'
    elif height:
        floors, fsrc = max(1, round(height / FLOOR_M)), f'derived:{hsrc}'
    else:
        floors, fsrc = 1, 'default'
    return {'footprintM2': round(area, 1), 'perimeterM': round(perimeter, 1),
            'heightM': round(height, 1) if height else None, 'heightSource': hsrc,
            'floors': floors, 'floorsSource': fsrc, 'rPlus': f'R+{floors - 1}' if floors > 1 else 'RDC',
            'floorAreaM2': round(area * floors, 1), 'floorAreaIsEstimate': fsrc == 'default'}


def classify(t, area, floors, poi_cat=None, rural=False, in_multi=False, satellite=False):
    """(class, confidence, evidence) for one structure. t: dict of OSM tags."""
    b = (t.get('building') or '').lower()
    if b in ('construction',):
        return 'chantier', 0.9, 'osm:building=construction'
    if b in ('ruins',):
        return 'ruine', 0.9, 'osm:building=ruins'
    am = (t.get('amenity') or '').lower()
    if am == 'place_of_worship':
        rel = (t.get('religion') or '').lower()
        return ('rel.eglise' if rel == 'christian' else 'rel.mosquee'), 0.9, 'osm:amenity=place_of_worship'
    if am in OSM_AMENITY:
        return OSM_AMENITY[am], 0.9, f'osm:amenity={am}'
    if t.get('shop'):
        return ('mix.immeuble' if floors >= 3 else 'com.boutique'), 0.85, f'osm:shop={t["shop"]}'
    if t.get('office') or t.get('government'):
        if t.get('government') or (t.get('office') or '') == 'government':
            return 'gov.admin', 0.9, 'osm:office=government'
        return 'com.bureau', 0.85, f'osm:office={t.get("office")}'
    if t.get('tourism') in ('hotel', 'guest_house', 'motel', 'hostel', 'chalet', 'apartment'):
        return 'hot.hotel', 0.9, f'osm:tourism={t["tourism"]}'
    if t.get('healthcare'):
        return 'san.centre', 0.85, f'osm:healthcare={t["healthcare"]}'
    if t.get('industrial') or t.get('craft') == 'fishing' or t.get('man_made') == 'works':
        if (t.get('industrial') or '') in ('fishery', 'fish_processing'):
            return 'pec.quai', 0.8, 'osm:industrial=fishery'
        return 'ind.usine', 0.8, 'osm:industrial'
    if b in OSM_BUILDING:
        c = OSM_BUILDING[b]
        if c == 'res.maison' and floors >= 3:
            c = 'res.immeuble'
        return c, 0.85, f'osm:building={b}'
    if poi_cat in PLACES:
        c = PLACES[poi_cat]
        if c in ('com.boutique', 'hot.restaurant', 'com.atelier') and floors >= 3:
            return 'mix.immeuble', 0.6, f'places:{poi_cat}+floors'
        return c, 0.7, f'places:{poi_cat}'
    # Shape and height (no tag, no place).
    if satellite:
        return 'res.annexe', 0.4, 'shape:satellite'
    if floors >= 3 and area >= 60:
        return 'res.immeuble', 0.45, 'shape:floors>=3'
    if area < 25 and rural:
        return 'res.case', 0.5, 'shape:small+rural'
    if area >= 1500 and floors <= 2:
        return 'com.entrepot', 0.3, 'shape:large-low'
    if in_multi:
        return 'res.concession', 0.45, 'shape:multi-structure compound'
    if 25 <= area < 600:
        return 'res.maison', 0.45, 'shape:house-size'
    return 'inconnu', 0.2, 'none'


def compound_use(classes):
    """SPEC 6.3: the use of a compound from its structures' classes, main first."""
    if not classes:
        return 'unknown'
    group = lambda c: c.split('.', 1)[0]
    g = group(classes[0])
    mixed = any(group(c) not in (g, 'res', 'inconnu', 'chantier', 'ruine') for c in classes[1:])
    if g == 'res':
        return 'mixed' if mixed else 'residential'
    return {'com': 'commercial', 'hot': 'commercial', 'mix': 'commercial', 'gov': 'public', 'edu': 'public',
            'san': 'public', 'tra': 'public', 'rel': 'religious', 'ind': 'industrial', 'pec': 'industrial',
            'agr': 'industrial'}.get(g, 'unknown')

# ---------------------------------------------------------------- compounds
SATELLITE_M2 = 30.0       # kitchen, toilet, gatehouse, boys' quarters, store
SAT_GAP_URBAN = 4.0       # metres between equivalent circles
SAT_GAP_RURAL = 8.0
CASE_M2 = 120.0           # rural concession structures (cases, small houses)
CASE_GAP = 6.0
CASE_MAX = 30             # structures in one rural concession
URBAN_TILE = 250.0        # metres
URBAN_MIN = 100           # structures per 250 m tile (1,600 per km2) = urban fabric


def _ring_area(ring):
    return abs(sum(ring[i][0] * ring[i - 1][1] - ring[i - 1][0] * ring[i][1] for i in range(len(ring)))) / 2


def radius(a):
    return math.sqrt(max(a, 1.0) / math.pi)


def group_compounds(structs, enclosures=()):
    """Group structures into compounds (SPEC.md section 5).

    structs: list of dicts with e, n (UTM metres), area (m2), id.
    enclosures: list of (enclosure id, kind, [(e, n) ring]) - walls, fences,
    N-Ways sites; every structure whose centre lies inside one is that
    compound's. Returns list of compounds: dict(members=[ids], rule, conf,
    urban). Deterministic: input order does not matter.
    """
    structs = sorted(structs, key=lambda s: (s['e'], s['n'], s['id']))
    idx = {s['id']: i for i, s in enumerate(structs)}
    tiles = {}
    for s in structs:
        k = (int(s['e'] // URBAN_TILE), int(s['n'] // URBAN_TILE))
        tiles[k] = tiles.get(k, 0) + 1
    for s in structs:  # a precomputed tileCount (whole-zone density) wins over the local count
        s['urban'] = s.get('tileCount', tiles[(int(s['e'] // URBAN_TILE), int(s['n'] // URBAN_TILE))]) >= URBAN_MIN
    parent = list(range(len(structs)))
    size = [1] * len(structs)
    rule = ['single'] * len(structs)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        if a != b:
            lo, hi = min(a, b), max(a, b)
            parent[hi] = lo
            size[lo] += size[hi]

    # spatial hash for neighbour search
    G = 40.0
    grid = {}
    for i, s in enumerate(structs):
        grid.setdefault((int(s['e'] // G), int(s['n'] // G)), []).append(i)
    # R0 enclosures (smallest first, so a house wall inside an estate wins)
    enclosed = set()
    encl = sorted(enclosures, key=lambda x: _ring_area(x[2]))
    for _, _, ring in encl:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        cand = [i for gx in range(int(min(xs) // G), int(max(xs) // G) + 1)
                for gy in range(int(min(ys) // G), int(max(ys) // G) + 1) for i in grid.get((gx, gy), ())]
        inside = sorted(i for i in cand if i not in enclosed and Zones._in_ring(structs[i]['e'], structs[i]['n'], ring))
        for i in inside[1:]:
            union(inside[0], i)
        for i in inside:
            rule[i] = 'enclosure'
            enclosed.add(i)

    def near(i):
        s = structs[i]
        gx, gy = int(s['e'] // G), int(s['n'] // G)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((gx + dx, gy + dy), ()):
                    if j != i:
                        yield j

    def gap(i, j):
        a, b = structs[i], structs[j]
        return math.hypot(a['e'] - b['e'], a['n'] - b['n']) - radius(a['area']) - radius(b['area'])

    # R1 satellites: a small structure joins the nearest main structure
    for i, s in enumerate(structs):
        if i in enclosed or s['area'] >= SATELLITE_M2:
            continue
        lim = SAT_GAP_URBAN if s['urban'] else SAT_GAP_RURAL
        best = min(((gap(i, j), j) for j in near(i)
                    if structs[j]['area'] >= SATELLITE_M2 and j not in enclosed), default=None)
        if best and best[0] <= lim:
            union(i, best[1])
            rule[i] = 'satellite'
            s['satellite'] = True
    # R2 rural concessions: small structures single-linked in rural fabric
    for i, s in enumerate(structs):
        if i in enclosed or s['urban'] or s['area'] >= CASE_M2:
            continue
        for j in near(i):
            t = structs[j]
            if j in enclosed or t['urban'] or t['area'] >= CASE_M2 or j < i:
                continue
            if gap(i, j) <= CASE_GAP:
                a, b = find(i), find(j)
                if a != b and size[a] + size[b] <= CASE_MAX:
                    union(a, b)
                    for k in (i, j):
                        if rule[k] == 'single':
                            rule[k] = 'rural-concession'
    comps = {}
    for i in range(len(structs)):
        comps.setdefault(find(i), []).append(i)
    out = []
    for root, members in comps.items():
        rules = {rule[i] for i in members}
        r = 'enclosure' if 'enclosure' in rules else 'rural-concession' if 'rural-concession' in rules \
            else 'satellite' if 'satellite' in rules else 'single'
        conf = {'enclosure': 0.9, 'single': 0.7, 'satellite': 0.6, 'rural-concession': 0.5}[r]
        # main structure first (largest), then the rest by distance from it
        members.sort(key=lambda i: (-structs[i]['area'], structs[i]['id']))
        m0 = structs[members[0]]
        members[1:] = sorted(members[1:], key=lambda i: (math.hypot(structs[i]['e'] - m0['e'],
                                                                    structs[i]['n'] - m0['n']), structs[i]['id']))
        tot = sum(structs[i]['area'] for i in members)
        ce = sum(structs[i]['e'] * structs[i]['area'] for i in members) / tot
        cn = sum(structs[i]['n'] * structs[i]['area'] for i in members) / tot
        ext = max(math.hypot(structs[i]['e'] - ce, structs[i]['n'] - cn) + radius(structs[i]['area']) for i in members)
        out.append({'members': [structs[i]['id'] for i in members], 'rule': r, 'confidence': conf,
                    'urban': m0['urban'], 'e': ce, 'n': cn, 'extentM': round(ext, 1)})
    return out

# ---------------------------------------------------------------- registry
HEADROOM = 3  # numbers for three times today's compounds (urban growth ~3.7 %/yr -> about 30 years)


def number_lieu(zone, lieu, compounds):
    """First issue in one lieu: Hilbert order, numbers spread evenly over the lieu's block."""
    lo, hi = lieu['blocks'][0]   # the lieu's block of its name's national range (SPEC 3.3)
    span = hi - lo + 1
    comps = sorted(compounds, key=lambda c: (hilbert_key(zone, c['e'], c['n']), c['e'], c['n']))
    nb = len(comps)
    if HEADROOM * nb > span:
        raise ValueError(f"lieu {lieu['placeWord']}: {nb} compounds do not fit its block {lo}-{hi} with headroom")
    for i, c in enumerate(comps):
        c['number'] = lo + int((i + 0.5) * span / nb)
    return comps


def insert_in_lieu(zone, lieu, issued, e, n, lieux=None):
    """A new compound after first issue (SPEC 7.4): the free number midway
    between its Hilbert neighbours in the lieu's first block; else the lowest
    free number of the lieu's further blocks; else a new block from the name's
    spare space (needs `lieux`); else None (the caller then numbers it in
    '<lieu> Extension'). Issued numbers and blocks never change."""
    import bisect
    lo_r, hi_r = lieu['blocks'][0]
    used = {c['number'] for c in issued}
    first = [c for c in issued if lo_r <= c['number'] <= hi_r]
    h = hilbert_key(zone, e, n)
    seq = sorted(first, key=lambda c: (hilbert_key(zone, c['e'], c['n']), c['number']))
    keys = [hilbert_key(zone, c['e'], c['n']) for c in seq]
    k = bisect.bisect_right(keys, h)
    a = seq[k - 1]['number'] if k > 0 else lo_r - 1
    b = seq[k]['number'] if k < len(seq) else hi_r + 1
    if b - a >= 2:
        mid = (a + b) // 2
        if mid not in used and lo_r <= mid <= hi_r:
            return mid
    for lo, hi in lieu['blocks'][1:]:
        free = next((x for x in range(lo, hi + 1) if x not in used), None)
        if free is not None:
            return free
    if lieux is not None:
        blk = lieux.add_block(lieu)
        if blk:
            return blk[0]
    return None



# ---------------------------------------------------------------- vectors and selftest (SPEC 11)
POINTS = [  # (label, lat, lon): public places, positions from OpenStreetMap or hand-placed (approx.)
    ('Arch 22, Banjul', 13.4527, -16.5782),
    ('Westfield junction, Serrekunda', 13.4426, -16.6767),
    ('Bakau market (approx.)', 13.4783, -16.6787),
    ('Brikama market (approx.)', 13.2717, -16.6476),
    ('Farafenni (approx.)', 13.5667, -15.6000),
    ('Janjanbureh (approx.)', 13.5333, -14.7667),
    ('Basse Santa Su (approx.)', 13.3097, -14.2137),
]
SAME_NAME = ['Brikama', 'Sanchaba', 'Fula Kunda', 'Madina']   # typed names shared by several places
PLATES = ['Brusubi Phase 1', 'Balanghar Kerjuri', 'Busura']       # official names and their plate names


def _mid(lieu):
    lo, hi = lieu['blocks'][0]
    return lo + (hi - lo + 1) * 15 // 100


def vectors(zones, lieux):
    plus = [{'place': p, 'lat': la, 'lon': lo, 'plusCode': plus_code(la, lo), 'short': short_plus(la, lo), 'zone': zones.lookup(la, lo)}
            for p, la, lo in POINTS]
    checks = [{'family': f, 'number': n, 'payload': f'{f:05d}{n:05d}', 'digit': address_check(f, n)}
              for f, n in ((0, 100), (12, 2512), (1234, 45128), (99999, 99999))]
    numbers = [{'number': n, 'written': group_number(n), 'spoken': say_number(n)} for n in (120, 2512, 9071, 45128, 10307)]
    same = []
    for nm in SAME_NAME:
        fam = lieux.families.get(name_key(nm))
        if not fam:
            continue
        for lieu in sorted(fam['lieux'], key=lambda x: (x['zone'], x['index']))[:4]:
            n = _mid(lieu)
            f = address_forms(zones, lieu, n)
            same.append({'typed': f"{nm} {n}", 'lieu': f"{lieu['zone']}/{lieu['index']}", 'officialName': lieu['officialName'],
                         'family': lieu['family'], 'digits': lieu['digits'], 'block': lieu['blocks'][0], **f,
                         'decoded': [f"{z_}/{c['index']}" for z_, c, _ in find(f"{nm} {n}", zones, lieux)]})
    plates = []
    for off in PLATES:
        for lieu in [x for x in lieux.items if x.get('officialName') == off][:1]:
            n = _mid(lieu)
            f = address_forms(zones, lieu, n)
            plates.append({'officialName': off, 'plateName': lieu['placeWord'], 'rule': lieu.get('plateRule'),
                           'needsCouncilChoice': bool(lieu.get('needsCouncilChoice')), **f, 'lieu': f"{lieu['zone']}/{lieu['index']}",
                           'decodedPlate': [f"{z_}/{c['index']}" for z_, c, _ in find(f['home'], zones, lieux)],
                           'decodedOfficial': [f"{z_}/{c['index']}" for z_, c, _ in find(f"{off} {n}", zones, lieux)]})
    keys = [{'a': a, 'b': b, 'key': name_key(a), 'same': name_key(a) == name_key(b)}
            for a, b in (('Serrekunda', 'Serre Kunda'), ('Kerr Mbaye', 'Keur Mbaye'), ('Sukuta', 'Sukkuta'), ('Suwareh', 'Suware'),
                         ('Ndungu Kebbeh', 'Ndungu Kebbe'), ('Bakau', 'Bakoteh'), ('Brusubi 1', 'Brusubi'))]
    return {'plus': plus, 'check': checks, 'numbers': numbers, 'nameKeys': keys, 'sameName': same, 'plateNames': plates}


def selftest(zones, lieux):
    import random
    rnd = random.Random(220)
    for _ in range(2000):  # UTM round trip
        lat, lon = rnd.uniform(13.0, 13.9), rnd.uniform(-16.9, -13.7)
        la, lo = utm_inverse(*utm_forward(lat, lon))
        assert abs(la - lat) < 1e-9 and abs(lo - lon) < 1e-9
    for _ in range(3000):  # every single wrong digit and every adjacent swap is caught
        p = ''.join(rnd.choice('0123456789') for _ in range(10))
        c = damm(p)
        for k in range(10):
            for x in '0123456789':
                if x != p[k]:
                    assert damm(p[:k] + x + p[k + 1:]) != c
            if k + 1 < 10 and p[k] != p[k + 1]:
                assert damm(p[:k] + p[k + 1] + p[k] + p[k + 2:]) != c
    for a, b in (('Serrekunda', 'Serre Kunda'), ('Kerr Mbaye', 'Keur Mbaye'), ('Sukuta', 'Sukkuta'), ('Suwareh', 'Suware'),
                 ('Ndungu Kebbeh', 'Ndungu Kebbe'), ('Brusubi 1', 'Brusubi')):
        assert name_key(a) == name_key(b), (a, b)
    assert name_key('Bakau') != name_key('Bakoteh')
    assert plus_code(47.365590, 8.524997, 10) == '8FVC9G8F+6X'
    assert plus_recover('9G8F+6X', 47.4, 8.6) == '8FVC9G8F+6X'     # the Open Location Code specification's examples
    assert plus_recover('8F+6X', 47.4, 8.6) == '8FVCCJ8F+6X'
    for _ in range(2000):  # a Plus Code decodes to the cell that holds its point, and its short form recovers from the town
        lat, lon = rnd.uniform(13.0, 13.9), rnd.uniform(-16.9, -13.7)
        c = plus_code(lat, lon)
        s_, w_, n_, e_ = plus_decode(c)
        assert s_ <= lat < n_ + 1e-9 and w_ <= lon < e_ + 1e-9
        assert plus_recover(c[4:], lat + rnd.uniform(-0.2, 0.2), lon + rnd.uniform(-0.2, 0.2)) == c
    if lieux.items:  # every name one family, blocks disjoint, every place decodes on its own
        for key, f in lieux.families.items():
            assert len({it['family'] for it in f['lieux']}) == 1 and len({it['digits'] for it in f['lieux']}) == 1
            bl = sorted(b for it in f['lieux'] for b in it['blocks'])
            assert all(bl[i][1] < bl[i + 1][0] for i in range(len(bl) - 1)), key
        for it in lieux.items:
            assert plate_ok(it['placeWord']) or it.get('needsCouncilChoice'), it['placeWord']
            n = _mid(it)
            got = find(f"{it['placeWord']} {n}", zones, lieux)
            assert [(z_, c['index']) for z_, c, _ in got] == [(it['zone'], it['index'])], (it['placeWord'], n, got)
    vpath = os.path.join(HERE, 'vectors.json')
    if lieux.items and os.path.exists(vpath):
        want = _load_json(vpath)
        got = json.loads(json.dumps(vectors(zones, lieux), ensure_ascii=False))
        assert got == want, 'vectors.json differs from the engine output'
    print(f'selftest ok: UTM, Damm (all single errors and adjacent swaps), name keys, Plus Codes (encode, decode, recover), '
          f'{len(lieux.items)} places decode on their own, vectors')


def main(argv):
    zones, lieux = Zones(), Lieux()
    cmd = argv[1] if len(argv) > 1 else 'selftest'
    if cmd == 'find':
        for _, lieu, n in find(argv[2], zones, lieux):
            print(json.dumps(address_forms(zones, lieu, n), ensure_ascii=False))
    elif cmd == 'check':
        print(validate(argv[2], lieux))
    elif cmd == 'plus':
        print(plus_code(float(argv[2]), float(argv[3])))
    elif cmd == 'vectors':
        out = vectors(zones, lieux)
        if len(argv) > 2 and argv[2] == '--write':
            with open(os.path.join(HERE, 'vectors.json'), 'w', encoding='utf-8') as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        selftest(zones, lieux)


if __name__ == '__main__':
    main(sys.argv)
