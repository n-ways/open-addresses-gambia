"""Tests of the registry server on the fixture in server/testdata (the real
codes, areas and footprints of the Banjul zone).

  python3 -m unittest server.tests.test_server
"""
import gzip
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from server import store as S
from server.api import Config, make_server
from server.registry import ApiError, Registry

HERE = os.path.dirname(os.path.abspath(__file__))
TESTDATA = os.path.join(os.path.dirname(HERE), 'testdata')
FIXTURE = os.path.join(TESTDATA, 'registry')
KEY = 'test-key-1'

FIRST = 'GM-BJL-0000-10001-2'          # Banjul 10 001, the first code of the zone
FIRST_AT = (13.4343654, -16.578024)    # its entrance
COUNCIL = ('GM-BJL-0000-19459-5', '30A Mam Mberry Njie Street')
# Points with no compound within 3 m, more than 10 m apart (where new codes go).
FREE = [(13.4468483, -16.575647), (13.4596002, -16.5776241), (13.4548329, -16.5843484), (13.4448591, -16.5742254),
        (13.4429915, -16.5767474), (13.4554616, -16.5810971), (13.4594467, -16.5769814)]


def quiet(*a, **k):
    pass


class Base(unittest.TestCase):
    """One imported fixture database, copied for each server or test that writes."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='gm-server-test-')
        cls.db = os.path.join(cls.tmp, 'fixture.sqlite')
        S.import_registry(FIXTURE, cls.db, log=quiet)

    @classmethod
    def tearDownClass(cls):
        for srv in getattr(cls, 'servers', []):
            srv.shutdown()
            srv.server_close()
            srv.app.reg.st.close()
        shutil.rmtree(cls.tmp)

    @classmethod
    def copy_db(cls, name):
        path = os.path.join(cls.tmp, name)
        shutil.copy(cls.db, path)
        return path

    @classmethod
    def start(cls, db, keys=(), per_day=500, cors=()):
        srv = make_server(Config(db, port=0, host='127.0.0.1', issue_keys=keys, issue_per_day=per_day, cors=cors, quiet=True), S.Store(db))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        cls.servers = getattr(cls, 'servers', []) + [srv]
        return f'http://127.0.0.1:{srv.server_address[1]}'

    def call(self, base, path, method='GET', body=None, key=None, headers=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(base + path, data=data, method=method)
        if data is not None:
            req.add_header('Content-Type', 'application/json')
        if key:
            req.add_header('Authorization', 'Bearer ' + key)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read()), dict(r.headers)
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read()), dict(e.headers)

    def registry(self, db, per_day=10 ** 6):
        st = S.Store(db)
        self.addCleanup(st.close)
        return Registry(st, per_day)

    def error(self, status, body, code):
        self.assertIn('error', body)
        self.assertEqual(body['error']['code'], code, body)
        self.assertTrue(body['error']['message'])
        return status


# ---------------------------------------------------------------- import and export

class TestImportExport(Base):
    def test_round_trip_is_byte_identical(self):
        out = os.path.join(self.tmp, 'export')
        man = S.export_registry(self.db, out, log=quiet)
        for name in ('lieux.csv', 'BJL.csv', 'structures/BJL.csv'):
            with gzip.open(os.path.join(FIXTURE, name + '.gz'), 'rb') as a, gzip.open(os.path.join(out, name + '.gz'), 'rb') as b:
                self.assertEqual(a.read(), b.read(), name)
        with open(os.path.join(FIXTURE, 'MANIFEST.json'), 'rb') as a, open(os.path.join(out, 'MANIFEST.json'), 'rb') as b:
            self.assertEqual(a.read(), b.read())
        self.assertEqual(man['homeCodes'], 4320)

    def test_import_is_indexed(self):
        c = sqlite3.connect(self.db)
        idx = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type IN ('index', 'table')")}
        for name in ('codes_machine', 'codes_home', 'codes_official', 'codes_zone', 'codes_area', 'codes_number'):
            self.assertIn(name, idx)
        self.assertTrue({'codes_rt', 'structures_rt'} <= idx or {'codes_grid', 'structures_grid'} <= idx)
        self.assertEqual(c.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
        c.close()

    def _broken_copy(self, name):
        d = os.path.join(self.tmp, name)
        if os.path.exists(d):
            shutil.rmtree(d)
        shutil.copytree(FIXTURE, d)
        return d

    def test_refuses_a_changed_file(self):
        d = self._broken_copy('bad-sha')
        p = os.path.join(d, 'BJL.csv.gz')
        with gzip.open(p, 'rb') as f:
            data = f.read()
        with gzip.open(p, 'wb') as f:
            f.write(data.replace(b'Banjul 10 001', b'Banjul 10 002', 1))
        with self.assertRaisesRegex(S.ImportError_, 'SHA-256'):
            S.import_registry(d, os.path.join(self.tmp, 'bad.sqlite'), log=quiet)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'bad.sqlite')))

    def test_refuses_a_wrong_count(self):
        d = self._broken_copy('bad-count')
        p = os.path.join(d, 'MANIFEST.json')
        with open(p, encoding='utf-8') as f:
            m = json.load(f)
        m['byZone']['BJL'] += 1
        m['homeCodes'] += 1
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(m, f)
        with self.assertRaisesRegex(S.ImportError_, 'MANIFEST'):
            S.import_registry(d, os.path.join(self.tmp, 'bad2.sqlite'), log=quiet)

    def test_rerun_and_protects_local_codes(self):
        db = self.copy_db('rerun.sqlite')
        S.import_registry(FIXTURE, db, log=quiet)          # a plain re-import replaces it safely
        reg = self.registry(db)
        reg.issue({'lat': FREE[0][0], 'lng': FREE[0][1]}, 'k')
        with self.assertRaisesRegex(S.ImportError_, 'issued by this deployment'):
            S.import_registry(FIXTURE, db, log=quiet)
        S.import_registry(FIXTURE, db, replace=True, log=quiet)


# ---------------------------------------------------------------- read endpoints

class TestRead(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base = cls.start(cls.copy_db('read.sqlite'), cors=('https://example.org',))

    def get(self, path):
        return self.call(self.base, path)

    def test_health_and_info(self):
        s, b, _ = self.get('/v1/health')
        self.assertEqual((s, b['status'], b['country'], b['codes'], b['issuing']), (200, 'ok', 'GM', 4320, False))
        s, b, _ = self.get('/v1/info')
        self.assertEqual(s, 200)
        self.assertEqual(len(b['zones']), 7)
        self.assertEqual(b['counts']['codes'], 4320)
        self.assertEqual(b['counts']['areas'], 2347)
        self.assertIn('N-WAYS LIMITED', b['credit'])

    def test_card(self):
        s, b, _ = self.get('/v1/codes/' + FIRST)
        self.assertEqual(s, 200)
        self.assertEqual(b['home'], 'Banjul 10 001')
        self.assertEqual(b['written'], 'BANJUL 10 001 · BANJUL')
        self.assertEqual(b['area']['id'], 'BJL-0000')
        self.assertEqual(b['zone']['name'], 'Banjul')
        self.assertEqual(b['plusCode'], '7C55CCMC+PQX')
        self.assertEqual(b['officialAddress'], 'CCMC+PQX Banjul')
        self.assertEqual(len(b['structures']), 1)
        self.assertEqual(set(b['registry']), set(S.ZONE_COLUMNS))
        self.assertEqual(b['registry']['machine'], FIRST)

    def test_card_council_address(self):
        s, b, _ = self.get('/v1/codes/' + COUNCIL[0])
        self.assertEqual(b['officialAddress'], COUNCIL[1])

    def test_card_errors(self):
        self.error(*self.get('/v1/codes/GM-BJL-0000-10001-3')[:2], 'bad_check')
        self.error(*self.get('/v1/codes/GM-BJL-0000-10002-' + str(__import__('server.engine', fromlist=['E']).E.address_check(109, 10002)))[:2], 'not_issued')
        self.error(*self.get('/v1/codes/hello')[:2], 'not_a_code')
        s, b, _ = self.get('/v1/codes/GM-BJL-0000-10001-3')
        self.assertEqual(s, 422)

    def test_find_remembered(self):
        for q in ('Banjul 10 001', 'banjul 10001', 'BANJUL 10 001 · BANJUL', '  bánjul   10 001 '):
            s, b, _ = self.get('/v1/find?q=' + urllib.request.quote(q))
            self.assertEqual(s, 200, q)
            self.assertEqual(b['kind'], 'remembered')
            self.assertEqual([r['machine'] for r in b['results']], [FIRST], q)

    def test_find_other_forms(self):
        s, b, _ = self.get('/v1/find?q=' + FIRST.lower())
        self.assertEqual((s, b['kind'], b['results'][0]['machine']), (200, 'machine', FIRST))
        s, b, _ = self.get('/v1/find?q=' + urllib.request.quote('CCMC+PQX Banjul'))
        self.assertEqual((s, b['kind'], b['results'][0]['machine']), (200, 'official', FIRST))
        s, b, _ = self.get('/v1/find?q=' + urllib.request.quote('7C55CCMC+PQX'))
        self.assertEqual((s, b['kind'], b['results'][0]['machine']), (200, 'plus', FIRST))
        s, b, _ = self.get('/v1/find?q=' + urllib.request.quote(COUNCIL[1].upper()))
        self.assertEqual((s, b['kind'], b['results'][0]['machine']), (200, 'official', COUNCIL[0]))

    def test_find_errors(self):
        self.assertEqual(self.error(*self.get('/v1/find?q=')[:2], 'missing_query'), 400)
        self.assertEqual(self.error(*self.get('/v1/find?q=Nowhereville%201234')[:2], 'unknown'), 404)
        self.assertEqual(self.error(*self.get('/v1/find?q=Banjul%2010%20002')[:2], 'not_issued'), 404)
        self.assertEqual(self.error(*self.get('/v1/find?q=GM-BJL-0000-10001-3')[:2], 'bad_check'), 422)
        self.assertEqual(self.error(*self.get('/v1/find?q=CCMC%2BPQX')[:2], 'short_plus_code'), 400)
        s, b, _ = self.get('/v1/find?q=' + urllib.request.quote('Banjul 10 001, West Coast'))
        self.assertEqual(self.error(s, b, 'unknown'), 404)
        self.assertIn('is in Banjul', b['error']['message'])

    def test_raw_utf8_query(self):
        # A client that sends UTF-8 bytes unescaped still has its accents read correctly.
        import socket
        host, port = self.base[len('http://'):].split(':')
        with socket.create_connection((host, int(port))) as sock:
            sock.sendall('GET /v1/find?q=b\u00e1njul+10001 HTTP/1.0\r\nHost: x\r\n\r\n'.encode('utf-8'))
            raw = b''
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                raw += chunk
        head, body = raw.split(b'\r\n\r\n', 1)
        b = json.loads(body)
        self.assertEqual((head.split()[1], b['results'][0]['machine']), (b'200', FIRST))

    def test_at(self):
        s, b, _ = self.get('/v1/at?lat=%s&lng=%s' % FIRST_AT)
        self.assertEqual((s, b['status'], b['code']['machine'], b['distanceM']), (200, 'found', FIRST, 0))
        s, b, _ = self.get('/v1/at?lat=13.4497&lng=-16.5802')
        self.assertEqual((s, b['status'], b['zone']['key'], b['area']['id']), (200, 'none', 'BJL', 'BJL-0000'))
        s, b, _ = self.get('/v1/at?lat=14.5&lng=-16.0')
        self.assertEqual(b['status'], 'outside')
        self.assertEqual(self.error(*self.get('/v1/at?lat=13.4')[:2], 'missing_lng'), 400)
        self.assertEqual(self.error(*self.get('/v1/at?lat=abc&lng=1')[:2], 'bad_lat'), 400)

    def test_near(self):
        s, b, _ = self.get('/v1/near?lat=%s&lng=%s&radius=40' % FIRST_AT)
        self.assertEqual(s, 200)
        self.assertEqual(b['codes'][0]['machine'], FIRST)
        self.assertTrue(all(c['distanceM'] <= 40 for c in b['codes']))
        d = [c['distanceM'] for c in b['codes']]
        self.assertEqual(d, sorted(d))
        s, b, _ = self.get('/v1/near?lat=13.4530&lng=-16.5790&radius=500&limit=100')
        self.assertEqual(len(b['codes']), 100)
        self.assertEqual(self.error(*self.get('/v1/near?lat=13.43&lng=-16.57&radius=501')[:2], 'bad_radius'), 400)
        self.assertEqual(self.error(*self.get('/v1/near?lat=13.43&lng=-16.57&limit=101')[:2], 'bad_limit'), 400)

    def test_verify(self):
        s, b, _ = self.get('/v1/verify?code=' + FIRST)
        self.assertEqual((b['valid'], b['issued'], b['status']), (True, True, 'provisional'))
        s, b, _ = self.get('/v1/verify?code=GM-BJL-0000-10001-3')
        self.assertEqual((s, b['valid'], b['issued']), (200, False, False))
        self.assertIn('check digit', b['reason'])
        s, b, _ = self.get('/v1/verify?code=GM-BJL-0000-99999-0')
        self.assertFalse(b['valid'])
        self.assertEqual(self.error(*self.get('/v1/verify')[:2], 'missing_code'), 400)

    def test_spot(self):
        s, b, _ = self.get('/v1/spot?lat=%s&lng=%s' % FIRST_AT)
        self.assertEqual((s, b['code'], b['withTown'], b['zone']), (200, '7C55CCMC+PQX', 'CCMC+PQX Banjul', 'BJL'))
        s, b, _ = self.get('/v1/spot/decode?code=' + urllib.request.quote('CCMC+PQX Banjul'))
        self.assertEqual(s, 200)
        self.assertEqual(b['cells'][0]['code'], '7C55CCMC+PQX')
        self.assertEqual(b['cells'][0]['codes'][0]['machine'], FIRST)
        s, b, _ = self.get('/v1/spot/decode?code=' + urllib.request.quote('7C55CCMC+PQX'))
        self.assertEqual(b['cells'][0]['zone'], 'BJL')
        self.assertEqual(self.error(*self.get('/v1/spot/decode?code=CCMC%2BPQX')[:2], 'short_plus_code'), 400)
        self.assertEqual(self.error(*self.get('/v1/spot/decode?code=7C55CCMC%2BPQ1')[:2], 'bad_plus_code'), 400)
        self.assertEqual(self.error(*self.get('/v1/spot/decode?code=')[:2], 'missing_code'), 400)

    def test_zones_and_areas(self):
        s, b, _ = self.get('/v1/zones')
        self.assertEqual([z['key'] for z in b['zones']], ['BJL', 'CRR', 'KMC', 'LRR', 'NBR', 'URR', 'WCR'])
        s, b, _ = self.get('/v1/zones/bjl')
        self.assertEqual((s, b['codes'], b['areas'][0]['id'], b['areas'][0]['codes']), (200, 4320, 'BJL-0000', 4320))
        self.assertEqual(self.error(*self.get('/v1/zones/XYZ')[:2], 'unknown_zone'), 404)
        s, b, _ = self.get('/v1/areas/BJL-0000')
        self.assertEqual((b['plateName'], b['digits'], b['blocks'], b['codes']['total']), ('Banjul', 5, [[10000, 22999]], 4320))
        self.assertEqual(self.error(*self.get('/v1/areas/BJL-9999')[:2], 'unknown_area'), 404)
        s, b, _ = self.get('/v1/areas?name=brikama')
        self.assertGreater(len(b['areas']), 1)
        self.assertTrue(all(a['plateName'] == 'Brikama' for a in b['areas']))
        self.assertEqual(self.error(*self.get('/v1/areas?name=')[:2], 'missing_name'), 400)

    def test_paging(self):
        s, b, _ = self.get('/v1/zones/BJL/codes?limit=3')
        self.assertEqual(len(b['codes']), 3)
        s2, b2, _ = self.get('/v1/zones/BJL/codes?limit=3&after=' + b['next'])
        self.assertGreater(b2['codes'][0]['machine'], b['codes'][-1]['machine'])
        seen, after = 0, ''
        while True:
            _, p, _ = self.get(f'/v1/zones/BJL/codes?limit=1000&after={after}')
            seen += len(p['codes'])
            if not p['next']:
                break
            after = p['next']
        self.assertEqual(seen, 4320)
        self.assertEqual(self.error(*self.get('/v1/zones/BJL/codes?limit=0')[:2], 'bad_limit'), 400)

    def test_http_errors_and_cors(self):
        self.assertEqual(self.error(*self.get('/v1/nothing')[:2], 'not_found'), 404)
        s, b, _ = self.call(self.base, '/v1/health', method='POST', body={})
        self.assertEqual(self.error(s, b, 'method_not_allowed'), 405)
        s, b, h = self.call(self.base, '/v1/health', headers={'Origin': 'https://example.org'})
        self.assertEqual(h.get('Access-Control-Allow-Origin'), 'https://example.org')
        s, b, h = self.call(self.base, '/v1/health', headers={'Origin': 'https://other.example'})
        self.assertNotIn('Access-Control-Allow-Origin', h)

    def test_read_only_refuses_issuing(self):
        s, b, _ = self.call(self.base, '/v1/codes', method='POST', body={'lat': 13.45, 'lng': -16.58}, key=KEY)
        self.assertEqual(self.error(s, b, 'read_only'), 403)


# ---------------------------------------------------------------- issuing

class TestIssue(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.issue_db = cls.copy_db('issue.sqlite')
        cls.base = cls.start(cls.issue_db, keys=(KEY,))

    def post(self, body, key=KEY):
        return self.call(self.base, '/v1/codes', method='POST', body=body, key=key)

    def test_parity_with_the_issuer(self):
        """The fixture's parity cases, issued in order, give the issuer's numbers, forms and blocks."""
        reg = self.registry(self.copy_db('parity.sqlite'))
        with open(os.path.join(TESTDATA, 'parity.json'), encoding='utf-8') as f:
            cases = json.load(f)['cases']
        extended = 0
        for case in cases:
            c = reg.issue(dict(case['step']), 'parity')
            w = case['expect']
            self.assertEqual((c['machine'], c['home'], c['written'], c['number'], c['area']['id']),
                             (w['machine'], w['home'], w['written'], w['number'], w['lieu']), case['step'])
            self.assertEqual(reg.lieu(c['area']['id'])['blocks'], [list(b) for b in w['blocks']])
            self.assertEqual((c['status'], c['issued']), ('provisional', 'on-demand'))
            extended += len(w['blocks']) > 1
        self.assertGreater(extended, 0, 'the cases must reach an extension block')

    def test_extension_blocks_persist_and_export(self):
        db = self.copy_db('ext.sqlite')
        reg = self.registry(db)
        for _ in range(8):                     # doors at one spot: the gap closes, then a new block opens
            reg.issue({'lat': FIRST_AT[0], 'lng': FIRST_AT[1], 'of': FIRST}, 'k')
        blocks = reg.lieu('BJL-0000')['blocks']
        self.assertEqual(blocks[0], [10000, 22999])
        self.assertGreater(len(blocks), 1)
        self.assertEqual(self.registry(db).lieu('BJL-0000')['blocks'], blocks)   # kept in the database
        out = os.path.join(self.tmp, 'ext-export')
        man = S.export_registry(db, out, log=quiet)
        self.assertEqual(man['homeCodes'], 4328)
        with gzip.open(os.path.join(out, 'lieux.csv.gz'), 'rt', encoding='utf-8') as f:
            row = [l for l in f if l.startswith('BJL-0000,')][0]
        self.assertIn('|'.join(f'{a}-{b}' for a, b in blocks), row)
        with gzip.open(os.path.join(out, 'BJL.csv.gz'), 'rt', encoding='utf-8') as f:
            doors = [l for l in f if ',on-demand,' in l]
        self.assertEqual(len(doors), 8)
        self.assertTrue(all(',door,' in l for l in doors))
        # The export imports again.
        S.import_registry(out, os.path.join(self.tmp, 'ext-again.sqlite'), log=quiet)

    def test_issue_over_http(self):
        s, b, _ = self.post({'lat': FREE[1][0], 'lng': FREE[1][1]})
        self.assertEqual(s, 201, b)
        self.assertEqual((b['status'], b['issued'], b['entrance']['kind']), ('provisional', 'on-demand', 'centre'))
        self.assertTrue(b['machine'].startswith('GM-BJL-0000-'))
        self.assertNotIn(str(b['check']), b['written'].split()[-1])
        s, again, _ = self.call(self.base, '/v1/codes/' + b['machine'])
        self.assertEqual(again['home'], b['home'])

    def test_duplicates(self):
        s, b, _ = self.post({'lat': FIRST_AT[0], 'lng': FIRST_AT[1]})
        self.assertEqual(self.error(s, b, 'exists'), 409)
        self.assertEqual(b['error']['existing']['machine'], FIRST)
        s, b, _ = self.post({'lat': FIRST_AT[0] + 0.00002, 'lng': FIRST_AT[1]})            # about 2 m away
        self.assertEqual(self.error(s, b, 'exists'), 409)
        # An outline that covers an issued footprint is that building.
        ring = [[-16.5780161, 13.4344019], [-16.5779906, 13.434347], [-16.578032, 13.4343288], [-16.5780575, 13.4343837]]
        s, b, _ = self.post({'lat': 13.43436, 'lng': -16.57802 + 0.0004, 'outline': ring})
        self.assertEqual(self.error(s, b, 'exists'), 409)

    def test_outline_limits(self):
        lat, lng = FREE[6]
        tiny = [[lng, lat], [lng + 0.00001, lat], [lng + 0.00001, lat + 0.00001]]
        s, b, _ = self.post({'lat': lat, 'lng': lng, 'outline': tiny})
        self.assertEqual(self.error(s, b, 'bad_outline'), 422)
        s, b, _ = self.post({'lat': lat, 'lng': lng, 'outline': 'x'})
        self.assertEqual(self.error(s, b, 'bad_outline'), 400)

    def test_outline_is_kept(self):
        lat, lng = FREE[2]
        d = 0.00002
        ring = [[lng - d, lat - d], [lng + d, lat - d], [lng + d, lat + d], [lng - d, lat + d]]
        s, b, _ = self.post({'lat': lat, 'lng': lng, 'outline': ring})
        self.assertEqual(s, 201, b)
        self.assertEqual(b['compound']['structures'], 1)
        self.assertEqual(b['structures'][0]['data'], 'people')
        self.assertEqual(b['structures'][0]['id'], 'people:' + b['machine'])
        s, b2, _ = self.post({'lat': lat + d / 2, 'lng': lng + d / 2})    # inside the new footprint
        self.assertEqual(self.error(s, b2, 'exists'), 409)

    def test_issue_errors(self):
        s, b, _ = self.post({'lat': 13.45, 'lng': -16.58}, key=None)
        self.assertEqual(self.error(s, b, 'unauthorized'), 401)
        s, b, _ = self.post({'lat': 13.45, 'lng': -16.58}, key='wrong')
        self.assertEqual(self.error(s, b, 'unauthorized'), 401)
        s, b, _ = self.post({'lat': 14.6, 'lng': -16.0})
        self.assertEqual(self.error(s, b, 'outside'), 422)
        s, b, _ = self.post({'lat': 'x'})
        self.assertEqual(self.error(s, b, 'bad_point'), 400)
        s, b, _ = self.post({'lat': 13.4300, 'lng': -16.5800, 'of': FIRST})
        self.assertEqual(self.error(s, b, 'far'), 422)
        s, b, _ = self.post({'lat': 13.4300, 'lng': -16.5800, 'of': 'GM-BJL-0000-10002-0'})
        self.assertEqual(self.error(s, b, 'unknown'), 404)
        s, b, _ = self.post({'lat': 13.4300, 'lng': -16.5800, 'of': 'GM-BJL-0000-10001-3'})
        self.assertEqual(self.error(s, b, 'bad_check'), 422)
        req = urllib.request.Request(self.base + '/v1/codes', data=b'{not json', method='POST', headers={'Authorization': 'Bearer ' + KEY})
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            with e:
                self.assertEqual((e.code, json.loads(e.read())['error']['code']), (400, 'bad_json'))

    def test_the_border_decides(self):
        """A point the zone rule accepts (within 2 km of a Central River outline
        vertex) but which lies about 1.2 km across the national border, in a
        neighbouring country, is refused; inside the border, and within 300 m
        of it, a code is issued."""
        across, near, inside = (13.585, -15.1), (13.595, -15.1), (13.7, -15.1)
        reg = self.registry(self.copy_db('border.sqlite'))
        self.assertEqual(reg.zones.lookup(*across), 'CRR')
        self.assertFalse(reg.border.holds(*across))
        s, b, _ = self.post({'lat': across[0], 'lng': across[1]})
        self.assertEqual(self.error(s, b, 'outside'), 422)
        s, b, _ = self.call(self.base, '/v1/at?lat=%s&lng=%s' % across)
        self.assertEqual((s, b['status']), (200, 'outside'))
        self.assertGreater(reg.border.outside_m(*near), 0)        # about 120 m outside the line
        for lat, lng in (inside, near):
            s, b, _ = self.post({'lat': lat, 'lng': lng})
            self.assertEqual(s, 201, b)
            self.assertTrue(b['machine'].startswith('GM-CRR-'), b['machine'])

    def test_daily_limit(self):
        reg = self.registry(self.copy_db('limit.sqlite'), per_day=2)
        reg.issue({'lat': FREE[3][0], 'lng': FREE[3][1]}, 'k1')
        reg.issue({'lat': FREE[4][0], 'lng': FREE[4][1]}, 'k1')
        with self.assertRaises(ApiError) as cm:
            reg.issue({'lat': FREE[5][0], 'lng': FREE[5][1]}, 'k1')
        self.assertEqual((cm.exception.status, cm.exception.code), (429, 'limit'))
        reg.issue({'lat': FREE[5][0], 'lng': FREE[5][1]}, 'k2')       # another key has its own limit


class TestContract(unittest.TestCase):
    def test_openapi_lists_every_route(self):
        from server.api import ROUTES
        with open(os.path.join(os.path.dirname(HERE), 'openapi.yaml'), encoding='utf-8') as f:
            text = f.read()
        ops, path = {}, None
        for line in text.splitlines():
            if line.startswith('  /v1/') or line.startswith('  "/v1/'):
                path = line.strip().rstrip(':').strip('"')
                ops[path] = set()
            elif path and line.startswith('    ') and not line.startswith('     '):
                ops[path].add(line.strip().rstrip(':'))
            elif not line.startswith('  '):
                path = None
        for method, rx, fn in ROUTES:
            route = rx.pattern.strip('^$').replace('(?P<', '{').replace('>[^/]+)', '}')
            self.assertIn(route, ops)
            self.assertIn(method.lower(), ops[route], route)


class TestPatch(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base = cls.start(cls.copy_db('patch.sqlite'), keys=(KEY,))

    def patch(self, machine, body, key=KEY):
        return self.call(self.base, '/v1/codes/' + machine, method='PATCH', body=body, key=key)

    def test_status_life(self):
        m = 'GM-BJL-0000-10004-8'
        s, b, _ = self.patch(m, {'status': 'confirmed'})
        self.assertEqual((s, b['status']), (200, 'confirmed'))
        s, b, _ = self.patch(m, {'status': 'banana'})
        self.assertEqual(self.error(s, b, 'bad_status'), 422)
        s, b, _ = self.patch(m, {'status': 'retired'})
        self.assertEqual((s, b['status']), (200, 'retired'))
        s, b, _ = self.patch(m, {'status': 'confirmed'})
        self.assertEqual(self.error(s, b, 'retired'), 409)
        s, b, _ = self.call(self.base, '/v1/find?q=' + urllib.request.quote('Banjul 10 004'))
        self.assertEqual(self.error(s, b, 'retired'), 410)

    def test_move_entrance(self):
        m = 'GM-BJL-0000-10007-3'
        _, before, _ = self.call(self.base, '/v1/codes/' + m)
        lat, lng = before['entrance']['lat'] + 0.0002, before['entrance']['lng']      # about 22 m
        s, b, _ = self.patch(m, {'entrance': {'lat': lat, 'lng': lng}})
        self.assertEqual((s, b['entrance']['kind'], b['entrance']['lat']), (200, 'gate', round(lat, 7)))
        self.assertNotEqual(b['plusCode'], before['plusCode'])
        s, b, _ = self.call(self.base, '/v1/at?lat=%s&lng=%s' % (lat, lng))
        self.assertEqual(b['code']['machine'], m)
        s, b, _ = self.patch(m, {'entrance': {'lat': lat + 0.001, 'lng': lng}})
        self.assertEqual(self.error(s, b, 'far'), 422)

    def test_patch_errors(self):
        s, b, _ = self.patch(FIRST, {'status': 'confirmed'}, key=None)
        self.assertEqual(self.error(s, b, 'unauthorized'), 401)
        s, b, _ = self.patch(FIRST, {})
        self.assertEqual(self.error(s, b, 'bad_body'), 400)
        s, b, _ = self.patch('GM-BJL-0000-10001-3', {'status': 'confirmed'})
        self.assertEqual(self.error(s, b, 'bad_check'), 422)


if __name__ == '__main__':
    unittest.main()
