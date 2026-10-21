"""The SQLite database of a deployment: import from the published registry,
export back to it byte for byte, and the lookups the API needs.

Every registry column is kept as the exact text of the published file, so an
export reproduces it; typed copies (number, family, coordinates, folded names)
exist only for indexes and arithmetic.
"""
import csv
import datetime
import gzip
import hashlib
import io
import json
import os
import sqlite3
import threading

from . import engine as G

csv.field_size_limit(1 << 30)

ZONE_COLUMNS = ['machine', 'home', 'written', 'lieu', 'official_name', 'number', 'check', 'status', 'issued', 'issued_at',
                'entrance_lat', 'entrance_lng', 'entrance_kind', 'plus_code', 'class', 'use', 'kind', 'structures',
                'floor_area_m2', 'postcode', 'coverage', 'official_address', 'anchor_lat', 'anchor_lng', 'rule', 'enclosed']
AREA_COLUMNS = ['lieu', 'zone', 'index', 'plate_name', 'official_name', 'kind', 'name_key', 'family', 'digits', 'blocks',
                'needs_council_choice', 'aliases', 'near_town', 'coverage', 'e_utm28n', 'n_utm28n']
STRUCTURE_COLUMNS = ['machine', 'index', 'structure_id', 'use', 'confidence', 'class_source', 'status', 'footprint_m2',
                     'perimeter_m', 'height_m', 'height_source', 'floors', 'floor_area_m2', 'name', 'data', 'footprint_wkt']
# SQL names of the registry columns (a few are SQL keywords).
SQL = {'check': 'check_digit', 'index': 'idx', 'lieu': 'lieu', 'class': 'class_', 'use': 'use_'}


def col(c):
    return SQL.get(c, c)


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS areas (
  {', '.join(('id' if c == 'lieu' else col(c)) + ' TEXT' for c in AREA_COLUMNS)},
  ord INTEGER NOT NULL, family_n INTEGER NOT NULL, plate_key TEXT NOT NULL, official_key TEXT NOT NULL,
  PRIMARY KEY (id));
CREATE INDEX IF NOT EXISTS areas_zone ON areas (zone, ord);
CREATE INDEX IF NOT EXISTS areas_family ON areas (family_n);
CREATE INDEX IF NOT EXISTS areas_plate ON areas (plate_key);
CREATE INDEX IF NOT EXISTS areas_official ON areas (official_key);
CREATE TABLE IF NOT EXISTS codes (
  id INTEGER PRIMARY KEY,
  {', '.join(col(c) + ' TEXT' for c in ZONE_COLUMNS if c != 'number')},
  number INTEGER NOT NULL, zone TEXT NOT NULL, family INTEGER NOT NULL, lat REAL NOT NULL, lng REAL NOT NULL,
  home_key TEXT NOT NULL, official_key TEXT NOT NULL, issued_by TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS codes_machine ON codes (machine);
CREATE UNIQUE INDEX IF NOT EXISTS codes_number ON codes (family, number);
CREATE INDEX IF NOT EXISTS codes_home ON codes (home_key);
CREATE INDEX IF NOT EXISTS codes_official ON codes (official_key);
CREATE INDEX IF NOT EXISTS codes_plus ON codes (plus_code);
CREATE INDEX IF NOT EXISTS codes_zone ON codes (zone, family, number);
CREATE INDEX IF NOT EXISTS codes_area ON codes (lieu, number);
CREATE INDEX IF NOT EXISTS codes_issued_by ON codes (issued_by, issued_at);
CREATE TABLE IF NOT EXISTS structures (
  id INTEGER PRIMARY KEY,
  {', '.join(col(c) + ' TEXT' for c in STRUCTURE_COLUMNS)},
  idx_n INTEGER NOT NULL, minlng REAL, minlat REAL, maxlng REAL, maxlat REAL);
CREATE INDEX IF NOT EXISTS structures_machine ON structures (machine, idx_n);
"""

RTREE = """
CREATE VIRTUAL TABLE IF NOT EXISTS codes_rt USING rtree(id, minlng, maxlng, minlat, maxlat);
CREATE VIRTUAL TABLE IF NOT EXISTS structures_rt USING rtree(id, minlng, maxlng, minlat, maxlat);
"""
# Without R*Tree support, an integer grid of 0.001 degree cells (about 110 m).
GRID = """
CREATE TABLE IF NOT EXISTS codes_grid (cell INTEGER NOT NULL, id INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS codes_grid_cell ON codes_grid (cell);
CREATE TABLE IF NOT EXISTS structures_grid (cell INTEGER NOT NULL, id INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS structures_grid_cell ON structures_grid (cell);
"""
CELL = 0.001


def has_rtree():
    try:
        c = sqlite3.connect(':memory:')
        c.execute('CREATE VIRTUAL TABLE t USING rtree(id, a, b, c, d)')
        c.close()
        return True
    except sqlite3.OperationalError:
        return False


def cells(minlng, minlat, maxlng, maxlat):
    for gx in range(int(minlng // CELL), int(maxlng // CELL) + 1):
        for gy in range(int(minlat // CELL), int(maxlat // CELL) + 1):
            yield gx * 1000000 + gy


class ImportError_(Exception):
    pass


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def connect(path, readonly=False):
    if readonly:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=10000')
    return conn


# ---------------------------------------------------------------- CSV in the issuer's format

def _field(s):
    """One field as the issuer's CSV writer prints it (quoted only when needed)."""
    if s == '':
        return s
    if any(c in s for c in ',"\r\n') or s[0] in ' \t\n\v\f\r\u0085 ' or s == '\\.':
        return '"' + s.replace('"', '""') + '"'
    return s


def csv_line(fields):
    return ','.join(_field(f) for f in fields) + '\n'


def _read_gz(path):
    """Rows of a gzip CSV and the SHA-256 of its uncompressed bytes, streamed."""
    h = hashlib.sha256()

    class Tee(io.RawIOBase):
        def __init__(self, f):
            self.f = f

        def readable(self):
            return True

        def readinto(self, b):
            data = self.f.read(len(b))
            h.update(data)
            b[:len(data)] = data
            return len(data)

    raw = gzip.open(path, 'rb')
    text = io.TextIOWrapper(io.BufferedReader(Tee(raw), 1 << 20), encoding='utf-8', newline='')
    return csv.reader(text), h, raw


# ---------------------------------------------------------------- import

def import_registry(registry, db_path, replace=False, log=print):
    """Load registry/ into a new database next to db_path, verify it against
    MANIFEST.json, then move it into place. The old database stays untouched
    until every check has passed."""
    man_path = os.path.join(registry, 'MANIFEST.json')
    with open(man_path, encoding='utf-8') as f:
        manifest = json.load(f)
    if manifest.get('country') != G.COUNTRY:
        raise ImportError_(f"the registry is for {manifest.get('country')!r}, not {G.COUNTRY}")
    if os.path.exists(db_path) and not replace:
        old = connect(db_path, readonly=True)
        try:
            n = old.execute('SELECT count(*) FROM codes WHERE issued_by IS NOT NULL').fetchone()[0]
        except sqlite3.DatabaseError:
            n = 0
        old.close()
        if n:
            raise ImportError_(f'{db_path} holds {n} codes issued by this deployment; export them first, or pass --replace')
    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or '.', exist_ok=True)
    tmp = db_path + '.importing'
    for p in (tmp, tmp + '-wal', tmp + '-shm'):
        if os.path.exists(p):
            os.remove(p)
    conn = connect(tmp)
    rtree = has_rtree()
    conn.executescript(SCHEMA + (RTREE if rtree else GRID))
    sums = manifest.get('sha256', {})
    headers = {}
    got = {}

    def check(name, h):
        want = sums.get(name)
        if want is None:
            raise ImportError_(f'{name} is not listed in MANIFEST.json')
        if h.hexdigest() != want:
            raise ImportError_(f'{name}: SHA-256 {h.hexdigest()} does not match MANIFEST.json ({want})')

    try:
        conn.execute('BEGIN')
        # The areas (the frozen place table).
        rows, h, raw = _read_gz(os.path.join(registry, 'lieux.csv.gz'))
        head = next(rows)
        if head != AREA_COLUMNS:
            raise ImportError_(f'lieux.csv: unexpected columns {head}')
        headers['lieux.csv'] = head
        area_family = {}
        batch = []
        for i, r in enumerate(rows):
            d = dict(zip(head, r))
            area_family[d['lieu']] = int(d['family'])
            batch.append(r + [i, int(d['family']), G.E.name_key(d['plate_name']), G.fold(d['official_name'])])
        raw.close()
        check('lieux.csv', h)
        conn.executemany(f"INSERT INTO areas VALUES ({','.join('?' * (len(AREA_COLUMNS) + 4))})", batch)
        got['areas'] = len(batch)
        log(f'lieux.csv: {len(batch)} areas')

        zones = sorted(manifest.get('byZone', {}))
        cols = [c for c in ZONE_COLUMNS if c != 'number']
        insert = (f"INSERT INTO codes ({', '.join(col(c) for c in cols)}, number, zone, family, lat, lng, home_key, official_key) "
                  f"VALUES ({','.join('?' * (len(cols) + 7))})")
        total = 0
        for z in zones:
            rows, h, raw = _read_gz(os.path.join(registry, f'{z}.csv.gz'))
            head = next(rows)
            if head[:22] != ZONE_COLUMNS[:22] or any(c not in ZONE_COLUMNS for c in head):
                raise ImportError_(f'{z}.csv: unexpected columns {head}')
            headers[f'{z}.csv'] = head
            n, batch = 0, []
            for r in rows:
                d = dict(zip(head, r))
                if d['lieu'] not in area_family:
                    raise ImportError_(f"{z}.csv: {d['machine']} names an unknown area {d['lieu']}")
                if not d['machine'].startswith(f'{G.COUNTRY}-{z}-'):
                    raise ImportError_(f"{z}.csv: {d['machine']} is not a code of zone {z}")
                batch.append([d.get(c, '') for c in cols] + [
                    int(d['number']), z, area_family[d['lieu']], float(d['entrance_lat']), float(d['entrance_lng']),
                    G.home_key(d['home']), G.fold(d['official_address'])])
                n += 1
                if len(batch) >= 20000:
                    conn.executemany(insert, batch)
                    batch = []
            conn.executemany(insert, batch)
            raw.close()
            check(f'{z}.csv', h)
            if manifest['byZone'][z] != n:
                raise ImportError_(f"{z}.csv has {n} codes, MANIFEST.json says {manifest['byZone'][z]}")
            total += n
            log(f'{z}.csv: {n} codes')
        if manifest.get('homeCodes') != total:
            raise ImportError_(f"the zone files hold {total} codes, MANIFEST.json says {manifest.get('homeCodes')}")
        got['codes'] = total

        # Structures and footprints (optional: a registry without them still serves codes).
        st_total = 0
        for z in sorted(manifest.get('structuresByZone', {})):
            name = f'structures/{z}.csv'
            rows, h, raw = _read_gz(os.path.join(registry, 'structures', f'{z}.csv.gz'))
            head = next(rows)
            if head != STRUCTURE_COLUMNS:
                raise ImportError_(f'{name}: unexpected columns {head}')
            headers[name] = head
            n, batch = 0, []
            ins = (f"INSERT INTO structures ({', '.join(col(c) for c in STRUCTURE_COLUMNS)}, idx_n, minlng, minlat, maxlng, maxlat) "
                   f"VALUES ({','.join('?' * (len(STRUCTURE_COLUMNS) + 5))})")
            for r in rows:
                box = _wkt_box(r[-1])
                batch.append(r + [int(r[1])] + list(box))
                n += 1
                if len(batch) >= 20000:
                    conn.executemany(ins, batch)
                    batch = []
            conn.executemany(ins, batch)
            raw.close()
            check(name, h)
            if manifest['structuresByZone'][z] != n:
                raise ImportError_(f"{name} has {n} structures, MANIFEST.json says {manifest['structuresByZone'][z]}")
            st_total += n
            log(f'{name}: {n} structures')
        if 'structures' in manifest and manifest['structures'] != st_total:
            raise ImportError_(f"the structure files hold {st_total}, MANIFEST.json says {manifest['structures']}")
        got['structures'] = st_total
        missing = set(sums) - set(headers)
        if missing:
            raise ImportError_(f'MANIFEST.json lists files that were not imported: {sorted(missing)}')

        bad = conn.execute('SELECT machine FROM codes c WHERE NOT EXISTS (SELECT 1 FROM areas a WHERE a.id = c.lieu) LIMIT 1').fetchone()
        if bad:
            raise ImportError_(f'{bad[0]}: unknown area')
        bad = conn.execute('SELECT machine FROM structures s WHERE NOT EXISTS (SELECT 1 FROM codes c WHERE c.machine = s.machine) LIMIT 1').fetchone()
        if bad:
            raise ImportError_(f'structure of {bad[0]}: no such code')

        log('spatial index' + (' (R*Tree)' if rtree else ' (grid)'))
        if rtree:
            conn.execute('INSERT INTO codes_rt SELECT id, lng, lng, lat, lat FROM codes')
            conn.execute('INSERT INTO structures_rt SELECT id, minlng, maxlng, minlat, maxlat FROM structures WHERE minlng IS NOT NULL')
        else:
            for cid, lng, lat in conn.execute('SELECT id, lng, lat FROM codes').fetchall():
                conn.execute('INSERT INTO codes_grid VALUES (?, ?)', (next(cells(lng, lat, lng, lat)), cid))
            for sid, a, b, c, d in conn.execute('SELECT id, minlng, minlat, maxlng, maxlat FROM structures WHERE minlng IS NOT NULL').fetchall():
                conn.executemany('INSERT INTO structures_grid VALUES (?, ?)', [(k, sid) for k in cells(a, b, c, d)])
        meta = {'manifest': json.dumps(manifest, ensure_ascii=False), 'headers': json.dumps(headers),
                'spatial': 'rtree' if rtree else 'grid', 'imported_at': now_utc(), 'changed': ''}
        conn.executemany('INSERT INTO meta VALUES (?, ?)', list(meta.items()))
        conn.execute('COMMIT')
    except BaseException:
        conn.close()
        for p in (tmp, tmp + '-wal', tmp + '-shm'):
            if os.path.exists(p):
                os.remove(p)
        raise
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    conn.execute('ANALYZE')
    conn.close()
    for p in (db_path + '-wal', db_path + '-shm'):
        if os.path.exists(p):
            os.remove(p)
    os.replace(tmp, db_path)
    log(f"imported {got['codes']} codes, {got['areas']} areas, {got['structures']} structures into {db_path}")
    return got


def _wkt_box(wkt):
    if not wkt:
        return (None, None, None, None)
    from .geo import parse_wkt, bbox
    polys = parse_wkt(wkt)
    return bbox(polys) if polys else (None, None, None, None)


# ---------------------------------------------------------------- export

def export_registry(db_path, out, log=print):
    """Write the registry in the published format: the same columns, order and
    quoting, gzip without a name or time stamp, and MANIFEST.json."""
    conn = connect(db_path, readonly=True)
    meta = {r['key']: r['value'] for r in conn.execute('SELECT key, value FROM meta')}
    manifest = json.loads(meta['manifest'])
    headers = json.loads(meta['headers'])
    os.makedirs(out, exist_ok=True)
    sums = {}

    def write(name, lines):
        h = hashlib.sha256()
        path = os.path.join(out, name + '.gz')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.tmp', 'wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=9) as gz:
                buf = []
                for ln in lines:
                    buf.append(ln)
                    if len(buf) >= 5000:
                        b = ''.join(buf).encode('utf-8')
                        h.update(b)
                        gz.write(b)
                        buf = []
                b = ''.join(buf).encode('utf-8')
                h.update(b)
                gz.write(b)
        os.replace(path + '.tmp', path)
        sums[name] = h.hexdigest()

    head = headers['lieux.csv']

    def area_lines():
        yield csv_line(head)
        for r in conn.execute(f"SELECT {', '.join('id' if c == 'lieu' else col(c) for c in head)} FROM areas ORDER BY ord"):
            yield csv_line(list(r))
    write('lieux.csv', area_lines())
    counts = {}
    for z in sorted(manifest['byZone']):
        head = headers[f'{z}.csv']
        n = [0]

        def code_lines(z=z, head=head, n=n):
            yield csv_line(head)
            sel = ', '.join('CAST(number AS TEXT)' if c == 'number' else col(c) for c in head)
            for r in conn.execute(f'SELECT {sel} FROM codes WHERE zone = ? ORDER BY family, number', (z,)):
                n[0] += 1
                yield csv_line(list(r))
        write(f'{z}.csv', code_lines())
        counts[z] = n[0]
        log(f'{z}.csv: {n[0]} codes')
    st_counts = {}
    for z in sorted(manifest.get('structuresByZone', {})):
        name = f'structures/{z}.csv'
        head = headers[name]
        n = [0]

        def st_lines(z=z, head=head, n=n):
            yield csv_line(head)
            sel = ', '.join('s.' + col(c) for c in head)
            q = (f'SELECT {sel} FROM structures s JOIN codes c ON c.machine = s.machine WHERE c.zone = ? '
                 f'ORDER BY c.family, c.number, s.idx_n')
            for r in conn.execute(q, (z,)):
                n[0] += 1
                yield csv_line(list(r))
        write(name, st_lines())
        st_counts[z] = n[0]
    # Zones that gained their first codes here.
    for (z,) in conn.execute('SELECT DISTINCT zone FROM codes'):
        if z not in counts:
            raise RuntimeError(f'zone {z} has codes but no registry file; it is not one of the published zones')
    man = dict(manifest)
    man['byZone'] = counts
    man['homeCodes'] = sum(counts.values())
    if 'structuresByZone' in manifest:
        man['structuresByZone'] = st_counts
        man['structures'] = sum(st_counts.values())
    man['sha256'] = dict(sorted(sums.items()))
    if meta.get('changed'):
        man['exported'] = now_utc()
    with open(os.path.join(out, 'MANIFEST.json'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(dict(sorted(man.items())), ensure_ascii=False, indent=2) + '\n')
    conn.close()
    log(f"exported {man['homeCodes']} codes to {out}")
    return man


# ---------------------------------------------------------------- read access

class Store:
    """Thread-safe access: one SQLite connection per thread, writes serialised."""

    def __init__(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f'{path}: no database; run `python3 -m server import` first')
        self.path = path
        self.local = threading.local()
        self.write_lock = threading.Lock()
        self._conns, self._conns_lock = [], threading.Lock()
        c = self.conn()
        self.meta = {r['key']: r['value'] for r in c.execute('SELECT key, value FROM meta')}
        self.manifest = json.loads(self.meta['manifest'])
        self.spatial = self.meta.get('spatial', 'rtree')

    def conn(self):
        c = getattr(self.local, 'c', None)
        if c is None:
            c = self.local.c = connect(self.path)
            with self._conns_lock:
                self._conns.append(c)
        return c

    def close(self):
        with self._conns_lock:
            for c in self._conns:
                c.close()
            self._conns = []
        self.local = threading.local()

    def q(self, sql, args=()):
        return self.conn().execute(sql, args).fetchall()

    def one(self, sql, args=()):
        return self.conn().execute(sql, args).fetchone()

    # spatial candidates -------------------------------------------------
    def codes_in_box(self, minlng, minlat, maxlng, maxlat):
        if self.spatial == 'rtree':
            return self.q('SELECT c.* FROM codes_rt r JOIN codes c ON c.id = r.id '
                          'WHERE r.minlng <= ? AND r.maxlng >= ? AND r.minlat <= ? AND r.maxlat >= ?',
                          (maxlng, minlng, maxlat, minlat))
        ks = list(cells(minlng, minlat, maxlng, maxlat))
        out = []
        for i in range(0, len(ks), 500):
            part = ks[i:i + 500]
            out += self.q(f"SELECT c.* FROM codes_grid g JOIN codes c ON c.id = g.id WHERE g.cell IN ({','.join('?' * len(part))}) "
                          f"AND c.lng BETWEEN ? AND ? AND c.lat BETWEEN ? AND ?", part + [minlng, maxlng, minlat, maxlat])
        return out

    def structures_in_box(self, minlng, minlat, maxlng, maxlat):
        if self.spatial == 'rtree':
            return self.q('SELECT s.* FROM structures_rt r JOIN structures s ON s.id = r.id '
                          'WHERE r.minlng <= ? AND r.maxlng >= ? AND r.minlat <= ? AND r.maxlat >= ?',
                          (maxlng, minlng, maxlat, minlat))
        ks = list(cells(minlng, minlat, maxlng, maxlat))
        seen, out = set(), []
        for i in range(0, len(ks), 500):
            part = ks[i:i + 500]
            for r in self.q(f"SELECT s.* FROM structures_grid g JOIN structures s ON s.id = g.id WHERE g.cell IN ({','.join('?' * len(part))}) "
                            f"AND s.minlng <= ? AND s.maxlng >= ? AND s.minlat <= ? AND s.maxlat >= ?", part + [maxlng, minlng, maxlat, minlat]):
                if r['id'] not in seen:
                    seen.add(r['id'])
                    out.append(r)
        return out

    def index_code(self, c, rowid, lat, lng):
        if self.spatial == 'rtree':
            c.execute('DELETE FROM codes_rt WHERE id = ?', (rowid,))
            c.execute('INSERT INTO codes_rt VALUES (?, ?, ?, ?, ?)', (rowid, lng, lng, lat, lat))
        else:
            c.execute('DELETE FROM codes_grid WHERE id = ?', (rowid,))
            c.execute('INSERT INTO codes_grid VALUES (?, ?)', (next(cells(lng, lat, lng, lat)), rowid))

    def index_structure(self, c, rowid, box):
        if self.spatial == 'rtree':
            c.execute('INSERT INTO structures_rt VALUES (?, ?, ?, ?, ?)', (rowid, box[0], box[2], box[1], box[3]))
        else:
            c.executemany('INSERT INTO structures_grid VALUES (?, ?)', [(k, rowid) for k in cells(*box)])
