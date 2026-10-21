"""The JSON API under /v1 (server/openapi.yaml is its contract).

Every response is JSON. Errors are {"error": {"code", "message"}} with the
matching HTTP status; a few carry one more field (a 409 "exists" names the
code the building already has).
"""
import hmac
import json
import re
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import engine as G
from .registry import ApiError, Registry, dumps, key_id

MAX_BODY = 1 << 20


class Config:
    def __init__(self, db, port=8080, host='0.0.0.0', issue_keys=(), issue_per_day=500, cors=(), quiet=False):
        self.db, self.port, self.host = db, port, host
        self.issue_keys = [k for k in issue_keys if k]
        self.issue_per_day = issue_per_day
        self.cors = [c for c in cors if c]
        self.quiet = quiet


ROUTES = []


def route(method, pattern):
    rx = re.compile('^' + re.sub(r'\{(\w+)\}', r'(?P<\1>[^/]+)', pattern) + '$')

    def deco(fn):
        ROUTES.append((method, rx, fn))
        return fn
    return deco


def _float(qs, name, required=True):
    v = qs.get(name)
    if v is None or v == '':
        if required:
            raise ApiError(400, 'missing_' + name, f'{name} is required.')
        return None
    try:
        f = float(v)
    except ValueError:
        raise ApiError(400, 'bad_' + name, f'{name} must be a number.')
    if f != f or f in (float('inf'), float('-inf')):
        raise ApiError(400, 'bad_' + name, f'{name} must be a number.')
    return f


def _point(qs):
    lat, lng = _float(qs, 'lat'), _float(qs, 'lng')
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ApiError(400, 'bad_point', 'lat must be within ±90 and lng within ±180.')
    return lat, lng


def _int(qs, name, default, lo, hi):
    v = qs.get(name)
    if v is None or v == '':
        return default
    try:
        n = int(v)
    except ValueError:
        raise ApiError(400, 'bad_' + name, f'{name} must be a whole number.')
    if not lo <= n <= hi:
        raise ApiError(400, 'bad_' + name, f'{name} must be between {lo} and {hi}.')
    return n


# ---------------------------------------------------------------- handlers

@route('GET', '/v1/health')
def health(app, req, qs):
    n = app.reg.st.one('SELECT count(*) FROM codes')[0]
    return 200, {'status': 'ok', 'country': G.COUNTRY, 'codes': n, 'registryExported': app.reg.st.manifest.get('exported'),
                 'issuing': bool(app.cfg.issue_keys)}


@route('GET', '/v1/info')
def info(app, req, qs):
    st = app.reg.st
    by_status = {r['status']: r['n'] for r in st.q('SELECT status, count(*) AS n FROM codes GROUP BY status')}
    by_issue = {r['issued']: r['n'] for r in st.q('SELECT issued, count(*) AS n FROM codes GROUP BY issued')}
    return 200, {
        'country': G.COUNTRY, 'name': G.COUNTRY_NAME,
        'zones': app.reg.zone_list(),
        'counts': {'codes': sum(by_status.values()), 'byStatus': by_status, 'byIssue': by_issue,
                   'areas': len(app.reg.lieux.items), 'structures': st.one('SELECT count(*) FROM structures')[0]},
        'registry': {'exported': st.manifest.get('exported'), 'imported': st.meta.get('imported_at'),
                     'engine': st.manifest.get('engine')},
        'spec': G.SPEC,
        'licences': {'data': 'ODbL 1.0', 'code': 'Apache 2.0', 'documents': 'CC BY 4.0'},
        'credit': G.CREDIT, 'source': G.CREDIT_URL,
        'issuing': bool(app.cfg.issue_keys),
        'example': {'home': 'Bakau 2389', 'machine': 'GM-KMC-0001-2389-6'},
    }


@route('GET', '/v1/codes/{machine}')
def code(app, req, qs, machine):
    return 200, app.reg.get_card(urllib.parse.unquote(machine))


@route('GET', '/v1/find')
def find(app, req, qs):
    return 200, app.reg.find(qs.get('q'))


@route('GET', '/v1/at')
def at(app, req, qs):
    lat, lng = _point(qs)
    return 200, app.reg.at(lat, lng)


@route('GET', '/v1/near')
def near(app, req, qs):
    lat, lng = _point(qs)
    radius = _float(qs, 'radius', required=False)
    radius = 100.0 if radius is None else radius
    if not 0 < radius <= 500:
        raise ApiError(400, 'bad_radius', 'radius is in metres, more than 0 and at most 500.')
    limit = _int(qs, 'limit', 100, 1, 100)
    return 200, app.reg.near(lat, lng, radius, limit)


@route('GET', '/v1/verify')
def verify(app, req, qs):
    return 200, app.reg.verify(qs.get('code'))


@route('GET', '/v1/spot')
def spot(app, req, qs):
    lat, lng = _point(qs)
    return 200, app.reg.spot(lat, lng)


@route('GET', '/v1/spot/decode')
def spot_decode(app, req, qs):
    return 200, app.reg.spot_decode(qs.get('code'))


@route('GET', '/v1/zones')
def zones(app, req, qs):
    return 200, {'zones': app.reg.zone_list()}


@route('GET', '/v1/zones/{key}')
def zone(app, req, qs, key):
    return 200, app.reg.zone(key)


@route('GET', '/v1/zones/{key}/codes')
def zone_codes(app, req, qs, key):
    limit = _int(qs, 'limit', 100, 1, 1000)
    return 200, app.reg.zone_codes(key, qs.get('after', ''), limit)


@route('GET', '/v1/areas')
def areas(app, req, qs):
    name = (qs.get('name') or '').strip()
    if not name:
        raise ApiError(400, 'missing_name', 'Give name: a place name as on the plate or its official name.')
    counts = {}
    found = app.reg.areas_named(name)
    for lieu in found:
        ref = G.area_ref(lieu)
        counts[ref] = app.reg.st.one('SELECT count(*) FROM codes WHERE lieu = ?', (ref,))[0]
    return 200, {'name': name, 'areas': [app.reg.area_summary(l, counts) for l in found]}


@route('GET', '/v1/areas/{id}')
def area(app, req, qs, id):
    return 200, app.reg.area(urllib.parse.unquote(id))


@route('POST', '/v1/codes')
def issue(app, req, qs):
    kid = req.require_key()
    return 201, app.reg.issue(req.json_body(), kid)


@route('PATCH', '/v1/codes/{machine}')
def patch(app, req, qs, machine):
    req.require_key()
    return 200, app.reg.patch(urllib.parse.unquote(machine), req.json_body())


# ---------------------------------------------------------------- HTTP

class App:
    def __init__(self, cfg, store):
        self.cfg = cfg
        self.reg = Registry(store, cfg.issue_per_day)


class Handler(BaseHTTPRequestHandler):
    server_version = 'N-Ways-Addressing-GM'
    sys_version = ''
    protocol_version = 'HTTP/1.1'
    app = None

    def log_message(self, fmt, *args):
        if not self.app.cfg.quiet:
            sys.stderr.write('%s %s\n' % (time.strftime('%Y-%m-%dT%H:%M:%S'), fmt % args))

    def _cors(self):
        origin = self.headers.get('Origin')
        allowed = self.app.cfg.cors
        if origin and ('*' in allowed or origin in allowed):
            self.send_header('Access-Control-Allow-Origin', '*' if '*' in allowed else origin)
            self.send_header('Vary', 'Origin')

    def send_json(self, status, obj):
        body = (dumps(obj) + '\n').encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store' if self.command != 'GET' or status >= 400 else 'public, max-age=60')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self._cors()
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def require_key(self):
        keys = self.app.cfg.issue_keys
        if not keys:
            raise ApiError(403, 'read_only', 'This deployment is read-only: it serves the published registry and does not issue codes.')
        h = self.headers.get('Authorization', '')
        given = h[7:].strip() if h.lower().startswith('bearer ') else ''
        for k in keys:
            if given and hmac.compare_digest(given.encode(), k.encode()):
                return key_id(k)
        raise ApiError(401, 'unauthorized', 'A valid bearer key is required (Authorization: Bearer <key>).')

    def json_body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n > MAX_BODY:
            raise ApiError(413, 'too_large', 'The request body is over 1 MB.')
        raw = self.rfile.read(n) if n else b''
        self._body_read = True
        try:
            body = json.loads(raw.decode('utf-8') or 'null')
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, 'bad_json', 'The body is not valid JSON.')
        if not isinstance(body, dict):
            raise ApiError(400, 'bad_body', 'The body must be a JSON object.')
        return body

    def _dispatch(self, method):
        self._body_read = False
        # http.server decodes the request line as Latin-1; a client that sends
        # raw UTF-8 instead of percent-escapes gets its accents back here.
        try:
            target = self.path.encode('latin-1').decode('utf-8')
        except UnicodeError:
            target = self.path
        url = urllib.parse.urlsplit(target)
        qs = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query, keep_blank_values=True).items()}
        path = url.path.rstrip('/') or '/'
        try:
            allowed = []
            for m, rx, fn in ROUTES:
                mt = rx.match(path)
                if not mt:
                    continue
                allowed.append(m)
                if m == method or (method == 'HEAD' and m == 'GET'):
                    status, obj = fn(self.app, self, qs, **mt.groupdict())
                    return self.send_json(status, obj)
            if allowed:
                raise ApiError(405, 'method_not_allowed', f"{method} is not allowed here; use {', '.join(sorted(set(allowed)))}.")
            raise ApiError(404, 'not_found', f'There is no endpoint {path}. See /v1/info and server/openapi.yaml.')
        except ApiError as e:
            err = {'code': e.code, 'message': e.message}
            err.update(e.extra)
            self._drain()
            self.send_json(e.status, {'error': err})
        except Exception as e:  # never leak a stack trace to a client
            sys.stderr.write(f'error: {method} {self.path}: {e!r}\n')
            import traceback
            traceback.print_exc()
            self._drain()
            self.send_json(500, {'error': {'code': 'internal', 'message': 'Something went wrong on the server.'}})

    def _drain(self):
        if not self._body_read and self.command in ('POST', 'PATCH', 'PUT'):
            n = int(self.headers.get('Content-Length') or 0)
            if 0 < n <= MAX_BODY:
                self.rfile.read(n)
            elif n > MAX_BODY:
                self.close_connection = True
            self._body_read = True

    def do_GET(self):
        self._dispatch('GET')

    def do_HEAD(self):
        self._dispatch('HEAD')

    def do_POST(self):
        self._dispatch('POST')

    def do_PATCH(self):
        self._dispatch('PATCH')

    def do_PUT(self):
        self._dispatch('PUT')

    def do_DELETE(self):
        self._dispatch('DELETE')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
        self.send_header('Access-Control-Max-Age', '600')
        self.send_header('Content-Length', '0')
        self.end_headers()


def make_server(cfg, store):
    app = App(cfg, store)
    handler = type('BoundHandler', (Handler,), {'app': app})
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), handler)
    httpd.daemon_threads = True
    httpd.app = app
    return httpd
