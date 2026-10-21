"""The reference engine, loaded from engine/reference/gm_engine.py.

The server never re-implements an engine rule: parsing, check digits, forms,
Plus Codes, zones, places, Hilbert numbering and building classes all come
from the same file the specification names as its executable reference.
"""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_FILE = os.environ.get('ENGINE_FILE', os.path.join(ROOT, 'engine', 'reference', 'gm_engine.py'))
MODEL_DIR = os.environ.get('MODEL_DIR', os.path.join(ROOT, 'model'))
BORDER_FILE = os.environ.get('BORDER_FILE', os.path.join(ROOT, 'engine', 'data', 'border.geojson'))


def _load():
    spec = importlib.util.spec_from_file_location('gm_engine', ENGINE_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E = _load()

COUNTRY = 'GM'
COUNTRY_NAME = 'The Gambia'
CREDIT = 'N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)'
CREDIT_URL = 'https://github.com/n-ways/open-addresses-gambia'
SPEC = 'engine/SPEC.md 1.0'

# Limits of issuing on demand (the N-Ways issuer's values, SPEC 7.4).
MIN_AREA_M2 = 12.0           # smallest outline accepted for a new compound
MAX_AREA_M2 = 20000.0        # largest (2 ha)
EXISTS_M = 3.0               # a point this close to an issued compound is that compound
FOUND_M = 12.0               # GET /v1/at: the compound within this distance is the one at the point
CANDIDATE_M = 150.0          # entrances searched beyond FOUND_M for a footprint within it
DOOR_M = 80.0                # another door, or a moved entrance, stays within this of the entrance


# The ISO 3166-2 subdivisions of The Gambia. Kanifing Municipality has none of
# its own (zones.json gives it GM-KM in the same style); the API reports null.
ISO_3166_2 = {'GM-B', 'GM-L', 'GM-M', 'GM-N', 'GM-U', 'GM-W'}


def iso(zone):
    return zone.get('iso') if zone.get('iso') in ISO_3166_2 else None


def zones():
    return E.Zones(MODEL_DIR)


def border():
    """The national border (SPEC 2.1): a point more than 300 m outside it is
    in a neighbouring country and has no code, whatever the zones say."""
    return E.Border(BORDER_FILE)


def area_item(row):
    """An engine place (a lieu) from an `areas` row (the columns of lieux.csv)."""
    blocks = [[int(x) for x in b.split('-')] for b in row['blocks'].split('|') if b]
    aliases = [a for a in row['aliases'].split('|') if a]
    return {
        'zone': row['zone'], 'index': int(row['idx']), 'name': row['plate_name'], 'placeWord': row['plate_name'],
        'officialName': row['official_name'], 'kind': row['kind'], 'nameKey': row['name_key'],
        'family': int(row['family']), 'digits': int(row['digits']), 'blocks': blocks, 'aliases': aliases,
        'nearTown': row['near_town'] or None, 'coverage': row['coverage'],
        'needsCouncilChoice': row['needs_council_choice'] == 'true',
        'e': float(row['e_utm28n']), 'n': float(row['n_utm28n']),
    }


def area_ref(lieu):
    return f"{lieu['zone']}-{lieu['index']:04d}"


def blocks_text(lieu):
    return '|'.join(f'{lo}-{hi}' for lo, hi in lieu['blocks'])


def town_of(lieu):
    """The town written after the short Plus Code in the official address."""
    return lieu.get('officialName') or lieu['placeWord']


def official_address(lieu, lat, lng, council_address=''):
    """A council's street and number where one exists, else the government's
    Plus Code of the entrance with its town (SPEC 5)."""
    if council_address:
        return council_address
    return f'{E.short_plus(lat, lng)} {town_of(lieu)}'


def fold(s):
    """Case, accents, hyphens and spacing removed, for exact-name lookups."""
    return E.fold(s)


def home_key(text):
    """The remembered form as people type it: folded, the number's spaces closed."""
    toks = fold(text).replace(',', ' ').split()
    digits = ''
    while toks and toks[-1].isdigit():
        digits = toks.pop() + digits
    return ' '.join(toks) + (' ' + digits if digits else '')
