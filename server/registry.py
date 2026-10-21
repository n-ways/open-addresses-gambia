"""What the API answers: cards, look-ups, places, and issuing on demand.

Issuing follows the N-Ways issuer's rules exactly (engine/SPEC.md 7.4 and the
limits in server/engine.py), so a designated deployment numbers a new
compound as the issuer itself would:

1. The point must lie in a zone (E.Zones.lookup) and inside the national
   border or within 300 m of it (E.Border, SPEC 2.1): a zone outline that
   spills over the border never decides.
2. A new compound (no `of`) must not already have a code: no issued
   compound's footprint holds the point and no entrance or footprint is
   within 3 m; with an outline, the outline must be 12 m² to 2 ha and must
   not cover more than half of an issued footprint (or the reverse).
3. Its place is the nearest place of its zone (E.Lieux.nearest); another
   door (`of`) takes the place of the code it belongs to and must be within
   80 m of that code's entrance.
4. Its number is E.insert_in_lieu over every number the place holds,
   retired ones included, ordered by the compounds' centres; when the place's
   blocks are full a new block of one grain is cut from the name's spare
   range and kept; when the name's whole range is used, issuing stops there.
5. The code is provisional, issued on demand, its entrance and centre the
   point, and the forms come from E.address_forms.
"""
import hashlib
import json
import math
import re
import threading

from . import engine as G
from . import geo
from .engine import E
from .store import col, now_utc, ZONE_COLUMNS, STRUCTURE_COLUMNS


class ApiError(Exception):
    def __init__(self, status, code, message, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def _num(t):
    if t is None or t == '':
        return None
    f = float(t)
    return int(f) if f.is_integer() and 'e' not in t.lower() and '.' not in t else f


class Registry:
    def __init__(self, store, issue_per_day=500):
        self.st = store
        self.zones = G.zones()
        self.border = G.border()
        self.issue_lock = threading.Lock()
        self.issue_per_day = issue_per_day
        self.reload_areas()

    def reload_areas(self):
        rows = self.st.q('SELECT * FROM areas ORDER BY ord')
        self.lieux = E.Lieux(G.MODEL_DIR, items=[G.area_item(r) for r in rows])
        self.areas = {G.area_ref(l): l for l in self.lieux.items}

    def lieu(self, ref):
        return self.areas.get(ref)

    def zone_name(self, key):
        return self.zones.by_key[key]['name']

    # ------------------------------------------------------------ cards
    def card(self, row, full=True):
        lieu = self.lieu(row['lieu'])
        z = self.zones.by_key[lieu['zone']]
        lat, lng = row['lat'], row['lng']
        forms = E.address_forms(self.zones, lieu, row['number'])
        out = {
            'machine': row['machine'], 'home': row['home'], 'written': row['written'], 'spoken': forms['spoken'],
            'status': row['status'], 'issued': row['issued'], 'issuedAt': row['issued_at'],
            'officialAddress': G.official_address(lieu, lat, lng, row['official_address']),
            # The Plus Code with its town is the official address everywhere; a council's
            # street address, where the registry has one, takes its place.
            'coverage': row['coverage'] or 'official',
            'area': {'id': row['lieu'], 'plateName': lieu['placeWord'], 'officialName': lieu.get('officialName') or None,
                     'nameProvisional': bool(lieu.get('needsCouncilChoice')), 'nearTown': lieu.get('nearTown')},
            'zone': {'key': z['key'], 'name': z['name'], 'iso': G.iso(z)},
            'number': row['number'], 'check': int(row['check_digit']),
            'entrance': {'lat': lat, 'lng': lng, 'kind': row['entrance_kind']},
            'plusCode': row['plus_code'],
            'spot': {'code': row['plus_code'], 'short': row['plus_code'][4:],
                     'withTown': f"{row['plus_code'][4:]} {G.town_of(lieu)}"},
        }
        if row['anchor_lat']:
            out['centre'] = {'lat': float(row['anchor_lat']), 'lng': float(row['anchor_lng'])}
        if not full:
            return out
        out['compound'] = {'class': row['class_'] or None, 'use': row['use_'], 'kind': row['kind'],
                           'structures': int(row['structures'] or 0), 'floorAreaM2': float(row['floor_area_m2'] or 0),
                           'rule': row['rule'] or None, 'enclosed': row['enclosed'] == 'true'}
        out['postcode'] = row['postcode'] or None
        sts = []
        for s in self.st.q('SELECT * FROM structures WHERE machine = ? ORDER BY idx_n', (row['machine'],)):
            d = {'index': s['idx_n'], 'id': s['structure_id'], 'use': s['use_'], 'confidence': _num(s['confidence']),
                 'source': s['class_source'], 'status': s['status'], 'footprintM2': _num(s['footprint_m2']),
                 'perimeterM': _num(s['perimeter_m']), 'floors': int(s['floors']), 'floorAreaM2': _num(s['floor_area_m2']),
                 'data': s['data']}
            if s['height_m']:
                d['heightM'] = _num(s['height_m'])
            if s['height_source']:
                d['heightSource'] = s['height_source']
            if s['name']:
                d['name'] = s['name']
            sts.append(d)
        out['structures'] = sts
        reg = {}
        for c in ZONE_COLUMNS:
            v = row['number'] if c == 'number' else row[col(c)]
            reg[c] = str(v) if v is not None else ''
        out['registry'] = reg
        out['credit'] = G.CREDIT
        return out

    def code_row(self, machine):
        return self.st.one('SELECT * FROM codes WHERE machine = ?', (machine.strip().upper(),))

    def get_card(self, machine):
        ok, why = E.validate(machine, self.lieux)
        if not ok:
            raise self._invalid(machine, why)
        row = self.code_row(machine)
        if row is None:
            raise ApiError(404, 'not_issued', f'{machine.strip().upper()} is a valid code but no compound has it.')
        return self.card(row)

    def _invalid(self, code, why):
        if why.startswith('check digit'):
            return ApiError(422, 'bad_check', f'{code.strip()}: the check digit does not match. A digit is wrong or two are swapped; '
                                              'the code is refused rather than guessed.')
        if why.startswith('not an N-Ways'):
            return ApiError(400, 'not_a_code', f'{code.strip()!r} is not a machine code. Machine codes look like GM-KMC-0001-2389-6.')
        return ApiError(422, 'invalid_code', f'{code.strip()}: {why}.')

    # ------------------------------------------------------------ find
    def find(self, q):
        text = (q or '').strip()
        if not text:
            raise ApiError(400, 'missing_query', 'Give q: a home code ("Bakau 2389"), a machine code, an official address or a Plus Code.')
        if E.MACHINE_RE.match(text):
            return {'query': text, 'kind': 'machine', 'results': [self.get_card(text)]}
        if text.upper().startswith(G.COUNTRY + '-'):
            raise self._invalid(text, 'not an N-Ways Gambia home code')
        plus = self._plus_results(text)
        if plus is not None:
            kind, rows = plus
            if not rows:
                raise ApiError(404, 'not_found', f'No compound has its entrance in the Plus Code cell {text}. '
                                                 'Use /v1/at with the point to find the compound around it.')
            return {'query': text, 'kind': kind, 'results': [self.card(r) for r in rows]}
        rows = self.st.q('SELECT * FROM codes WHERE official_key = ? AND official_key <> ? ORDER BY machine', (G.fold(text), ''))
        if rows:
            return {'query': text, 'kind': 'official', 'results': [self.card(r) for r in rows]}
        found = E.find(text, self.zones, self.lieux)
        if not found:
            base = re.split(r'[,\u00b7]', text)[0].strip()
            again = E.find(base, self.zones, self.lieux) if base != text else []
            if again:
                where = ', '.join(sorted({self.zones.by_key[z]['name'] for z, _, _ in again}))
                raise ApiError(404, 'unknown', f'{base} is in {where}; what follows it in {text!r} '
                                               '(a zone or a check digit) does not match.')
            raise ApiError(404, 'unknown', f'No place in {G.COUNTRY_NAME} has the home code {text}. '
                                           'Check the place name and the number on the plate.')
        results, missing = [], []
        for _, lieu, number in found:
            r = self.st.one('SELECT * FROM codes WHERE family = ? AND number = ?', (lieu['family'], number))
            if r is None:
                missing.append((lieu, number))
            elif r['status'] == 'retired':
                missing.append((lieu, number))
            else:
                results.append(self.card(r))
        if not results:
            lieu, number = missing[0]
            r = self.st.one('SELECT status, home FROM codes WHERE family = ? AND number = ?', (lieu['family'], number))
            if r is not None:
                raise ApiError(410, 'retired', f"{r['home']} was retired: there is no compound there any more. A retired number is never given again.")
            home = f"{lieu['placeWord']} {E.group_number(number)}"
            raise ApiError(404, 'not_issued', f"No compound has {home} yet (the number is in the range of {lieu['placeWord']}, "
                                              f"{self.zone_name(lieu['zone'])}).")
        return {'query': text, 'kind': 'remembered', 'results': results}

    def _plus_results(self, text):
        """(kind, rows) when the text is a Plus Code, full or short with its town; None otherwise."""
        t = text.strip()
        head = t.split()[0].upper() if t.split() else ''
        if '+' not in head or any(ch not in E.OLC + '+0' for ch in head):
            return None
        rest = t[len(head):].strip(' ,')
        if head.index('+') == 8:
            try:
                E.plus_decode(head)
            except ValueError:
                raise ApiError(400, 'bad_plus_code', f'{head} is not a valid Plus Code.')
            return 'plus', self.st.q("SELECT * FROM codes WHERE plus_code = ? AND status <> 'retired' ORDER BY machine", (head,))
        if not rest:
            raise ApiError(400, 'short_plus_code', f'{head} is a short Plus Code: give the town after it, as in "{head} Bakau".')
        towns = self.areas_named(rest)
        if not towns:
            raise ApiError(404, 'unknown_town', f'No place in {G.COUNTRY_NAME} is called {rest!r}.')
        rows, seen = [], set()
        for lieu in towns:
            lat, lng = E.utm_inverse(lieu['e'], lieu['n'])
            try:
                full = E.plus_recover(head, lat, lng)
            except ValueError:
                raise ApiError(400, 'bad_plus_code', f'{head} is not a valid Plus Code.')
            for r in self.st.q("SELECT * FROM codes WHERE plus_code = ? AND status <> 'retired' ORDER BY machine", (full,)):
                if r['machine'] not in seen:
                    seen.add(r['machine'])
                    rows.append(r)
        return 'official', rows

    # ------------------------------------------------------------ places
    def areas_named(self, name):
        """Places whose plate name, official name or an alias is this name (by name key)."""
        k = E.name_key(name)
        out = []
        for fk in sorted(self.lieux.names.get(k, ())):
            for lieu in self.lieux.families[fk]['lieux']:
                if lieu not in out:
                    out.append(lieu)
        f = G.fold(name)
        for r in self.st.q('SELECT id FROM areas WHERE official_key = ? ORDER BY ord', (f,)):
            lieu = self.lieu(r['id'])
            if lieu not in out:
                out.append(lieu)
        return sorted(out, key=lambda l: (l['zone'], l['index']))

    def area_summary(self, lieu, counts=None):
        lat, lng = E.utm_inverse(lieu['e'], lieu['n'])
        out = {'id': G.area_ref(lieu), 'zone': lieu['zone'], 'plateName': lieu['placeWord'],
               'officialName': lieu.get('officialName') or None, 'kind': lieu['kind'],
               'position': {'lat': round(lat, 6), 'lng': round(lng, 6)}}
        if counts is not None:
            out['codes'] = counts.get(G.area_ref(lieu), 0)
        return out

    def area(self, ref):
        lieu = self.lieu(ref.strip().upper())
        if lieu is None:
            raise ApiError(404, 'unknown_area', f'There is no area {ref}. Area ids look like KMC-0001.')
        ref = G.area_ref(lieu)
        counts = {r['status']: r['n'] for r in self.st.q('SELECT status, count(*) AS n FROM codes WHERE lieu = ? GROUP BY status', (ref,))}
        lo_hi = [list(b) for b in lieu['blocks']]
        capacity = sum(hi - lo + 1 for lo, hi in lo_hi)
        used = self.st.one('SELECT count(*) FROM codes WHERE lieu = ?', (ref,))[0]
        siblings = [G.area_ref(l) for l in self.lieux.families[lieu['nameKey']]['lieux'] if l is not lieu]
        out = self.area_summary(lieu)
        out.update({
            'zoneName': self.zone_name(lieu['zone']), 'aliases': lieu.get('aliases', []), 'nearTown': lieu.get('nearTown'),
            'nameProvisional': bool(lieu.get('needsCouncilChoice')), 'coverage': lieu.get('coverage') or None,
            'nameKey': lieu['nameKey'], 'family': lieu['family'], 'digits': lieu['digits'], 'blocks': lo_hi,
            'sameName': sorted(siblings),
            'codes': {'total': used, 'provisional': counts.get('provisional', 0), 'confirmed': counts.get('confirmed', 0),
                      'retired': counts.get('retired', 0)},
            'numbers': {'capacity': capacity, 'used': used, 'free': capacity - used},
        })
        return out

    def zone_counts(self):
        return {r['zone']: r['n'] for r in self.st.q('SELECT zone, count(*) AS n FROM codes GROUP BY zone')}

    def zone_list(self):
        counts = self.zone_counts()
        areas = {}
        for l in self.lieux.items:
            areas[l['zone']] = areas.get(l['zone'], 0) + 1
        return [{'key': z['key'], 'index': z['index'], 'name': z['name'], 'iso': G.iso(z),
                 'codes': counts.get(z['key'], 0), 'areas': areas.get(z['key'], 0)}
                for z in sorted(self.zones.by_key.values(), key=lambda z: z['index'])]

    def zone(self, key):
        k = key.strip().upper()
        if k not in self.zones.by_key:
            raise ApiError(404, 'unknown_zone', f"There is no zone {key}. The zones are {', '.join(sorted(self.zones.by_key))}.")
        z = [x for x in self.zone_list() if x['key'] == k][0]
        counts = {r['lieu']: r['n'] for r in self.st.q('SELECT lieu, count(*) AS n FROM codes WHERE zone = ? GROUP BY lieu', (k,))}
        z['areas'] = [self.area_summary(l, counts) for l in sorted(self.lieux.by_zone.get(k, {}).values(), key=lambda l: l['index'])]
        return z

    def zone_codes(self, key, after='', limit=100):
        k = key.strip().upper()
        if k not in self.zones.by_key:
            raise ApiError(404, 'unknown_zone', f'There is no zone {key}.')
        rows = self.st.q('SELECT * FROM codes WHERE zone = ? AND machine > ? ORDER BY machine LIMIT ?', (k, after.strip().upper(), limit + 1))
        more = len(rows) > limit
        rows = rows[:limit]
        return {'zone': k, 'codes': [self.card(r, full=False) for r in rows],
                'next': rows[-1]['machine'] if more else None}

    # ------------------------------------------------------------ points
    def _structure_polys(self, row):
        return geo.parse_wkt(row['footprint_wkt'])

    def code_at(self, lat, lng, max_m):
        """The issuer's rule for "the compound at a point": a live compound whose
        footprint holds the point (the lowest machine code if several), else the
        live compound whose entrance or footprint is nearest within max_m."""
        hits = []
        for s in self.st.structures_in_box(lng, lat, lng, lat):
            if geo.contains(self._structure_polys(s), lng, lat):
                hits.append(s['machine'])
        if hits:
            for m in sorted(set(hits)):
                r = self.code_row(m)
                if r is not None and r['status'] != 'retired':
                    return r, 0.0
        reach = max_m + G.CANDIDATE_M
        dlat = reach / 110000.0
        dlng = reach / (110000.0 * math.cos(math.radians(lat)))
        best = None
        near_st = None
        for r in self.st.codes_in_box(lng - dlng, lat - dlat, lng + dlng, lat + dlat):
            if r['status'] == 'retired':
                continue
            if geo.metres(lat, lng, r['lat'], r['lng']) > reach:
                continue
            d = geo.metres(lat, lng, r['lat'], r['lng'])
            if near_st is None:
                near_st = {}
                for s in self.st.structures_in_box(lng - 0.001, lat - 0.001, lng + 0.001, lat + 0.001):
                    near_st.setdefault(s['machine'], []).append(s)
            for s in near_st.get(r['machine'], ()):
                d = min(d, geo.footprint_distance(self._structure_polys(s), lat, lng))
            if d <= max_m and (best is None or (d, r['machine']) < (best[1], best[0]['machine'])):
                best = (r, d)
        return best if best else (None, None)

    def zone_at(self, lat, lng):
        """The zone of a point, or None outside The Gambia: in no zone, or more
        than 300 m outside the national border whatever the zones say."""
        zk = self.zones.lookup(lat, lng)
        if zk is None or not self.border.holds(lat, lng):
            return None
        return zk

    def place_of(self, lat, lng):
        zk = self.zone_at(lat, lng)
        if zk is None:
            return None, None
        e, n = E.utm_forward(lat, lng)
        return zk, self.lieux.nearest(zk, e, n)

    def at(self, lat, lng):
        zk, lieu = self.place_of(lat, lng)
        if zk is None:
            return {'status': 'outside', 'point': {'lat': lat, 'lng': lng},
                    'message': f'The point is outside {G.COUNTRY_NAME}.'}
        zone = {'key': zk, 'name': self.zone_name(zk)}
        row, d = self.code_at(lat, lng, G.FOUND_M)
        if row is not None:
            return {'status': 'found', 'distanceM': round(d), 'code': self.card(row), 'zone': zone}
        return {'status': 'none', 'zone': zone, 'area': self.area_summary(lieu) if lieu else None,
                'spot': self.spot(lat, lng)}

    def near(self, lat, lng, radius, limit):
        dlat = radius / 110000.0
        dlng = radius / (110000.0 * math.cos(math.radians(lat)))
        out = []
        for r in self.st.codes_in_box(lng - dlng, lat - dlat, lng + dlng, lat + dlat):
            d = geo.metres(lat, lng, r['lat'], r['lng'])
            if d <= radius:
                out.append((d, r['machine'], r))
        out.sort(key=lambda x: (x[0], x[1]))
        return {'point': {'lat': lat, 'lng': lng}, 'radiusM': radius, 'count': min(len(out), limit),
                'codes': [dict(self.card(r, full=False), distanceM=round(d, 1)) for d, _, r in out[:limit]]}

    def spot(self, lat, lng):
        code = E.plus_code(lat, lng)
        zk, lieu = self.place_of(lat, lng)
        s, w, n, e = E.plus_decode(code)
        out = {'code': code, 'short': code[4:], 'withTown': f'{code[4:]} {G.town_of(lieu)}' if lieu else None,
               'zone': zk, 'area': G.area_ref(lieu) if lieu else None,
               'cell': {'south': round(s, 7), 'west': round(w, 7), 'north': round(n, 7), 'east': round(e, 7)}}
        return out

    def spot_decode(self, code):
        t = (code or '').strip()
        if not t:
            raise ApiError(400, 'missing_code', 'Give code: a full Plus Code ("7C55F8HC+8GF") or a short one with its town ("F8HC+8GF Bakau").')
        head = t.split()[0].upper()
        rest = t[len(head):].strip(' ,')
        try:
            if head.index('+') == 8:
                fulls = [head]
            else:
                if not rest:
                    raise ApiError(400, 'short_plus_code', f'{head} is a short Plus Code: give the town after it, as in "{head} Bakau".')
                towns = self.areas_named(rest)
                if not towns:
                    raise ApiError(404, 'unknown_town', f'No place in {G.COUNTRY_NAME} is called {rest!r}.')
                fulls = []
                for lieu in towns:
                    lat, lng = E.utm_inverse(lieu['e'], lieu['n'])
                    f = E.plus_recover(head, lat, lng)
                    if f not in fulls:
                        fulls.append(f)
            out = []
            for f in fulls:
                s, w, n, e = E.plus_decode(f)
                clat, clng = (s + n) / 2, (w + e) / 2
                zk, lieu = self.place_of(clat, clng)
                rows = self.st.q("SELECT * FROM codes WHERE plus_code = ? AND status <> 'retired' ORDER BY machine", (f,))
                out.append({'code': f, 'centre': {'lat': round(clat, 7), 'lng': round(clng, 7)},
                            'cell': {'south': round(s, 7), 'west': round(w, 7), 'north': round(n, 7), 'east': round(e, 7)},
                            'zone': zk, 'area': G.area_ref(lieu) if lieu else None,
                            'codes': [self.card(r, full=False) for r in rows]})
        except ValueError:
            raise ApiError(400, 'bad_plus_code', f'{head} is not a valid Plus Code.')
        return {'query': t, 'cells': out}

    def verify(self, code):
        t = (code or '').strip()
        if not t:
            raise ApiError(400, 'missing_code', 'Give code: a machine code such as GM-KMC-0001-2389-6.')
        ok, why = E.validate(t, self.lieux)
        out = {'code': t.upper(), 'valid': ok, 'reason': why if not ok else None, 'issued': False, 'status': None}
        if ok:
            r = self.code_row(t)
            if r is not None:
                out.update(issued=True, status=r['status'], home=r['home'], written=r['written'])
        return out

    # ------------------------------------------------------------ issuing
    def issued_today(self, key_id):
        since = _iso_minus_day()
        return self.st.one('SELECT count(*) FROM codes WHERE issued_by = ? AND issued_at >= ?', (key_id, since))[0]

    def issue(self, body, key_id):
        lat, lng = _point(body)
        of = (body.get('of') or '').strip().upper()
        outline = body.get('outline')
        if outline is not None and (not isinstance(outline, list) or any(
                not isinstance(p, (list, tuple)) or len(p) != 2 or not all(isinstance(v, (int, float)) for v in p) for p in outline)):
            raise ApiError(400, 'bad_outline', 'outline is a list of [lng, lat] pairs.')
        n = self.issued_today(key_id)
        if n >= self.issue_per_day:
            raise ApiError(429, 'limit', f'This key has issued {n} codes in the last 24 hours, its daily limit. Try again later.')
        with self.issue_lock, self.st.write_lock:
            zk = self.zone_at(lat, lng)
            if zk is None:
                raise ApiError(422, 'outside', f'That point is outside {G.COUNTRY_NAME}, so it cannot have a code.')
            ring, area, per = None, 0.0, 0.0
            if not of:
                row, _ = self.code_at(lat, lng, G.EXISTS_M)
                if row is not None:
                    raise ApiError(409, 'exists', f"This building already has its code: {row['home']}.", existing=self.card(row))
                if outline and len(outline) >= 3:
                    ring = [(float(x), float(y)) for x, y in outline]
                    if ring[0] == ring[-1]:
                        ring = ring[:-1]
                    area, per = geo.ring_area_m2(ring), geo.ring_perimeter_m(ring)
                    if len(ring) < 3 or area < G.MIN_AREA_M2 or area > G.MAX_AREA_M2:
                        raise ApiError(422, 'bad_outline', f"That outline is {area:.0f} m², but a compound's building is between "
                                                           f"{G.MIN_AREA_M2:.0f} m² and {G.MAX_AREA_M2 / 10000:.0f} ha.")
                    box = (min(x for x, _ in ring), min(y for _, y in ring), max(x for x, _ in ring), max(y for _, y in ring))
                    for s in sorted(self.st.structures_in_box(*box), key=lambda s: s['machine']):
                        if geo.same_building(self._structure_polys(s), ring):
                            r = self.code_row(s['machine'])
                            if r is not None and r['status'] != 'retired':
                                raise ApiError(409, 'exists', f"This building already has its code: {r['home']}.", existing=self.card(r))
            e, nn = E.utm_forward(lat, lng)
            if of:
                parent = self.code_row(of)
                if parent is None:
                    ok, why = E.validate(of, self.lieux)
                    if not ok:
                        raise self._invalid(of, why)
                    raise ApiError(404, 'unknown', f'There is no code {of} to add a door to.')
                if geo.dist_m(parent['lat'], parent['lng'], lat, lng) > G.DOOR_M:
                    raise ApiError(422, 'far', f"That door is more than {G.DOOR_M:.0f} m from {parent['home']}'s entrance.")
                lieu = self.lieu(parent['lieu'])
            else:
                lieu = self.lieux.nearest(zk, e, nn)
            if lieu is None:
                raise ApiError(422, 'outside', 'There is no place name for this point yet.')
            ref = G.area_ref(lieu)
            zone = self.zones.by_key[lieu['zone']]
            issued = []
            for r in self.st.q('SELECT number, lat, lng, anchor_lat, anchor_lng FROM codes WHERE lieu = ?', (ref,)):
                alat = float(r['anchor_lat']) if r['anchor_lat'] else r['lat']
                alng = float(r['anchor_lng']) if r['anchor_lng'] else r['lng']
                ae, an = E.utm_forward(alat, alng)
                issued.append({'e': ae, 'n': an, 'number': r['number']})
            before = [list(b) for b in lieu['blocks']]
            number = E.insert_in_lieu(zone, lieu, issued, e, nn, self.lieux)
            if number is None:
                raise ApiError(409, 'full', f"{lieu['placeWord']} has used every number of its name. Its council names the "
                                            f"extension before more compounds there get a code.")
            forms = E.address_forms(self.zones, lieu, number)
            chk = E.address_check(lieu['family'], number)
            kind = 'door' if of else 'centre'
            structure = None
            if ring:
                sz_area = _round1(area)
                cls, conf, ev = E.classify({}, area, 1, None, False, False, False)
                structure = {'machine': forms['machine'], 'index': '1', 'structure_id': 'people:' + forms['machine'], 'use': cls,
                             'confidence': _short(_f32round(conf, 100)), 'class_source': ev, 'status': 'existing',
                             'footprint_m2': _short(_f32round(sz_area, 10)), 'perimeter_m': _short(_f32round(_round1(per), 10)),
                             'height_m': '', 'height_source': '', 'floors': '1',
                             'floor_area_m2': _short(_f32round(sz_area, 10)), 'name': '', 'data': 'people',
                             'footprint_wkt': geo.ring_wkt(ring)}
                classes, floor_area = [cls], sz_area
            else:
                classes, floor_area = [], 0.0
            ckind = 'door' if of else 'un_batiment'
            vals = {
                'machine': forms['machine'], 'home': forms['home'], 'written': forms['written'], 'lieu': ref,
                'official_name': lieu.get('officialName', ''), 'check': str(chk), 'status': 'provisional',
                'issued': 'on-demand', 'issued_at': now_utc(), 'entrance_lat': f'{lat:.7f}', 'entrance_lng': f'{lng:.7f}',
                'entrance_kind': kind, 'plus_code': E.plus_code(lat, lng), 'class': classes[0] if classes else '',
                'use': E.compound_use(classes), 'kind': ckind, 'structures': str(len(classes)),
                'floor_area_m2': f'{_round1(floor_area):.1f}', 'postcode': '', 'coverage': '', 'official_address': '',
                'anchor_lat': f'{lat:.7f}', 'anchor_lng': f'{lng:.7f}', 'rule': '', 'enclosed': 'false',
            }
            c = self.st.conn()
            c.execute('BEGIN IMMEDIATE')
            try:
                cols = [k for k in ZONE_COLUMNS if k != 'number']
                cur = c.execute(
                    f"INSERT INTO codes ({', '.join(col(k) for k in cols)}, number, zone, family, lat, lng, home_key, official_key, issued_by) "
                    f"VALUES ({','.join('?' * (len(cols) + 8))})",
                    [vals[k] for k in cols] + [number, lieu['zone'], lieu['family'], lat, lng, G.home_key(forms['home']), '', key_id])
                self.st.index_code(c, cur.lastrowid, lat, lng)
                if structure:
                    polys = geo.parse_wkt(structure['footprint_wkt'])
                    box = geo.bbox(polys)
                    cur = c.execute(f"INSERT INTO structures ({', '.join(col(k) for k in STRUCTURE_COLUMNS)}, idx_n, minlng, minlat, maxlng, maxlat) "
                                    f"VALUES ({','.join('?' * (len(STRUCTURE_COLUMNS) + 5))})",
                                    [structure[k] for k in STRUCTURE_COLUMNS] + [1] + list(box))
                    self.st.index_structure(c, cur.lastrowid, box)
                if lieu['blocks'] != before:
                    c.execute('UPDATE areas SET blocks = ? WHERE id = ?', (G.blocks_text(lieu), ref))
                c.execute("UPDATE meta SET value = ? WHERE key = 'changed'", (now_utc(),))
                c.execute('COMMIT')
            except BaseException:
                c.execute('ROLLBACK')
                lieu['blocks'] = before
                raise
        return self.card(self.code_row(forms['machine']))

    def patch(self, machine, body):
        if not isinstance(body, dict) or not ({'status', 'entrance'} & set(body)):
            raise ApiError(400, 'bad_body', 'Send status ("confirmed", "provisional" or "retired") and/or entrance {"lat", "lng"}.')
        ok, why = E.validate(machine, self.lieux)
        if not ok:
            raise self._invalid(machine, why)
        with self.st.write_lock:
            row = self.code_row(machine)
            if row is None:
                raise ApiError(404, 'not_issued', f'{machine.upper()} is a valid code but no compound has it.')
            if row['status'] == 'retired':
                raise ApiError(409, 'retired', f"{row['home']} is retired. A retired code never comes back and its number is never reused.")
            sets = {}
            if 'status' in body:
                s = body['status']
                allowed = {'provisional': ('confirmed', 'retired'), 'confirmed': ('provisional', 'retired')}[row['status']]
                if s == row['status']:
                    pass
                elif s not in allowed:
                    raise ApiError(422, 'bad_status', f"A {row['status']} code can become {' or '.join(allowed)}, not {s!r}.")
                else:
                    sets['status'] = s
            if 'entrance' in body:
                lat, lng = _point(body['entrance'])
                if geo.dist_m(row['lat'], row['lng'], lat, lng) > G.DOOR_M:
                    raise ApiError(422, 'far', f'An entrance moves at most {G.DOOR_M:.0f} m; that point is further from the current one.')
                if self.zone_at(lat, lng) is None:
                    raise ApiError(422, 'outside', f'That point is outside {G.COUNTRY_NAME}.')
                sets.update(entrance_lat=f'{lat:.7f}', entrance_lng=f'{lng:.7f}', entrance_kind='gate',
                            plus_code=E.plus_code(lat, lng), lat=lat, lng=lng)
            if sets:
                c = self.st.conn()
                c.execute('BEGIN IMMEDIATE')
                try:
                    c.execute(f"UPDATE codes SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", list(sets.values()) + [row['id']])
                    if 'lat' in sets:
                        self.st.index_code(c, row['id'], sets['lat'], sets['lng'])
                    c.execute("UPDATE meta SET value = ? WHERE key = 'changed'", (now_utc(),))
                    c.execute('COMMIT')
                except BaseException:
                    c.execute('ROLLBACK')
                    raise
        return self.card(self.code_row(machine))


def _point(body):
    if not isinstance(body, dict):
        raise ApiError(400, 'bad_body', 'Send a JSON object with lat and lng.')
    try:
        lat, lng = float(body['lat']), float(body['lng'])
    except (KeyError, TypeError, ValueError):
        raise ApiError(400, 'bad_point', 'lat and lng are required numbers (WGS 84 degrees).')
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or math.isnan(lat) or math.isnan(lng):
        raise ApiError(400, 'bad_point', 'lat must be within ±90 and lng within ±180.')
    return lat, lng


def _round1(x):
    """Round half to even at one decimal, as the issuer stores sizes."""
    return round(x * 10) / 10


def _f32round(x, scale):
    """A value stored as a 32-bit real and read back rounded (the issuer's store)."""
    import struct
    f = struct.unpack('f', struct.pack('f', x))[0]
    return int(f * scale + 0.5) / scale


def _short(x):
    s = repr(float(x))
    return s[:-2] if s.endswith('.0') else s


def _iso_minus_day():
    import datetime
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    return t.strftime('%Y-%m-%dT%H:%M:%SZ')


def key_id(key):
    """A stable, non-secret id for a bearer key (its SHA-256, shortened)."""
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
