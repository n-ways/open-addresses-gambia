# The registry server

`server/` is a ready-to-deploy HTTP service for The Gambia's N-Ways home codes. It loads the published registry (`registry/`) into SQLite and serves it as a JSON API: look up a code in any of its forms, find the code of the compound at a point, list a zone or an area, decode a Plus Code. A deployment that has been designated as the issuer can also issue codes for new compounds, by exactly the rules the N-Ways issuer uses, so it gives the same numbers and the same forms.

It needs nothing but Python 3.9 or later: the standard library only (`http.server`, `sqlite3`, `json`, `gzip`, `hashlib`). Every engine rule (parsing, check digits, the forms, Plus Codes, zones, places, Hilbert numbering, building classes) comes from the reference engine, `engine/reference/gm_engine.py`; the server adds storage, geometry and HTTP around it.

The endpoints, with real requests and responses, are in [`docs/api.md`](../docs/api.md); the formal contract is [`openapi.yaml`](openapi.yaml).

## Deploy with Docker

From the repository root:

```sh
docker compose up -d
curl http://localhost:8080/v1/health
```

On its first start the container finds its data volume empty, imports the registry bundled in the image (about 20 seconds and 520 MB of disk for the 471,031 codes and 672,836 building footprints), and starts serving. Later starts reuse the database. The image runs as an unprivileged user, has a health check on `/v1/health`, and keeps its database in the `addresses-data` volume.

Without Compose:

```sh
docker build -t n-ways-addresses-gm .
docker run -d --name addresses -p 8080:8080 -v addresses-data:/data n-ways-addresses-gm
```

## Run with plain Python

```sh
python3 -m server import --registry registry --db data/addresses.sqlite
python3 -m server serve  --db data/addresses.sqlite --port 8080
```

`import` streams every `registry/*.csv.gz` into a new database, checks the SHA-256 of each file and every count against `registry/MANIFEST.json`, builds the indexes (machine code, remembered form, official address, zone, area and number, plus an R*Tree spatial index, or an integer grid where SQLite lacks R*Tree), and only then moves the new database into place. A mismatch stops it with the old database untouched. Running it again is safe; it refuses to replace a database that holds codes issued by that deployment unless `--replace` is given (export those first, below).

`python3 -m server run` does both: it imports when the database does not exist, then serves. It is the container's entry point.

To run it as a service on a Linux host, a systemd unit is enough:

```ini
[Unit]
Description=N-Ways Addressing for The Gambia: registry server
After=network.target

[Service]
User=addresses
WorkingDirectory=/opt/open-addresses-gambia
Environment=ADDRESSES_DB=/var/lib/addresses/addresses.sqlite PORT=8080
EnvironmentFile=-/etc/addresses.env
ExecStart=/usr/bin/python3 -m server run --quiet
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ADDRESSES_DB` | `data/addresses.sqlite` (`/data/addresses.sqlite` in the image) | The database |
| `REGISTRY_DIR` | `registry` | The registry that `import` and `run` load |
| `HOST`, `PORT` | `0.0.0.0`, `8080` | Where to listen |
| `ISSUE_KEYS` | empty | Comma-separated bearer keys allowed to issue and change codes. Empty means read-only |
| `ISSUE_PER_DAY` | `500` | Codes each key may issue in any 24 hours |
| `CORS_ORIGINS` | empty (`*` in `docker-compose.yml`) | Origins allowed to call the API from a browser, comma-separated, or `*` |

The same settings exist as flags (`--db`, `--registry`, `--host`, `--port`). Keys belong in the environment or a `.env` file that is never committed. Generate them with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Behind a reverse proxy with TLS

The server speaks plain HTTP. In production put it behind a proxy that terminates TLS, and keep port 8080 closed to the outside. With Caddy, which obtains certificates itself:

```
addresses.example.gm {
    reverse_proxy 127.0.0.1:8080
}
```

With nginx:

```nginx
server {
    listen 443 ssl http2;
    server_name addresses.example.gm;
    ssl_certificate     /etc/letsencrypt/live/addresses.example.gm/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/addresses.example.gm/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
    }
}
```

Read requests are cheap (a few milliseconds each) and can be cached by the proxy: successful `GET` responses carry `Cache-Control: public, max-age=60`.

## Back up and restore

The database is one SQLite file in WAL mode. Copy it while the server runs with SQLite's online backup, never with a plain file copy:

```sh
sqlite3 data/addresses.sqlite ".backup data/backup-$(date +%F).sqlite"
```

A read-only deployment needs no backup at all: it can always be rebuilt from `registry/`. An issuing deployment should also export its registry regularly; the export is the authoritative, portable copy:

```sh
python3 -m server export --db data/addresses.sqlite --out exports/$(date +%F)
```

`export` writes the registry in exactly the published format: the same files, columns, order and quoting, gzip without names or time stamps, and a `MANIFEST.json` with the counts and checksums. Exporting a database straight after importing the published registry gives files whose contents are identical to it, byte for byte once uncompressed (the checksums in `MANIFEST.json` match); codes issued or changed since are included, with any number block added since in `lieux.csv`. To restore, import the export.

## Update to a newer registry

A read-only deployment follows the published registry: pull the repository (or the new image), then

```sh
python3 -m server import --registry registry --db data/addresses.sqlite
```

and restart the server. With Docker, rebuild the image and remove the old volume (`docker compose down -v && docker compose up -d --build`), or run the import inside the container.

An issuing deployment is itself the source of new codes, so it is not updated from someone else's registry: it exports, and its export is what gets published.

## The issuer rule

**Each country has exactly one issuer at a time.** A deployment issues codes only if the State or N-WAYS LIMITED has designated it as The Gambia's issuer; every other deployment runs read-only, with `ISSUE_KEYS` left empty, and serves the registry as published.

The reason is arithmetic. A new compound takes the free number midway between its neighbours in its place's block, and a full block is extended from the name's spare range. Two issuers working from the same registry would compute the same "next free number" for two different compounds, and the country would have two homes called, say, `Bakau 2390`: the one thing an address system must never do. Uniqueness can only be kept by one numbering authority, with everyone else copying its registry. Handing over the issuer role is done by exporting the registry from the old issuer, importing it into the new one and switching the old one to read-only, in that order.

## How a code is issued

`POST /v1/codes` with `{"lat", "lng"}`, optionally `outline` (the building, as `[lng, lat]` pairs) or `of` (another door of an existing compound). The rules are the issuer's (engine/SPEC.md sections 3.2, 3.3 and 7.4):

1. The point must fall in one of the seven zones and lie inside the national border or within 300 m of it (SPEC 2.1). The border is OpenStreetMap's admin_level=2 boundary of The Gambia, shipped simplified in `engine/data/border.geojson`; a zone outline, or the 2 km reach of the zone rule along rivers and coasts, never carries a code into a neighbouring country. A point beyond it is refused with `422 outside`, and `GET /v1/at` answers `outside` there.
2. A new compound must not already have a code: no live compound's building footprint holds the point, and no live compound's entrance or footprint is within 3 m. With an outline, its area must be between 12 m² and 2 ha, and it must not share more than half of the smaller footprint with an issued building.
3. The new compound's place is the nearest place of its zone: any place within 2.5 km, else a town or city within 10 km, else the nearest one. Another door takes the place of the compound it belongs to and must be within 80 m of that compound's entrance.
4. Its number is the free number midway between its neighbours on the Hilbert curve, among every number the place holds (retired ones included), in the place's first block. When that gap is closed it takes the lowest free number of the place's further blocks, and when those are full a new block of one grain (ten numbers for 3-digit names, a hundred otherwise) is cut from the top of the name's national range and kept for good. When the name's whole range is used, issuing stops with `409 full`: the council then names an extension.
5. The code is `provisional`, issued `on-demand`, with its entrance and centre at the point, and its remembered, written and machine forms come from the engine. The written form never shows the check digit; only the machine form does.

Each key may issue `ISSUE_PER_DAY` codes in any 24 hours. `PATCH /v1/codes/{machine}` confirms a code, returns it to provisional or retires it (a retired code never returns and its number is never reused), or moves its entrance by up to 80 m, never across the border.

These rules have been checked against the N-Ways issuer: 500 issues in sequence across all seven zones, including 139 made after extension blocks had been cut, gave the same numbers, forms and blocks; 300 random points gave the same answer to `GET /v1/at`, with the same distances; and 51 random codes matched the issuer's own API field by field. `server/testdata/parity.json` keeps a set of these cases for the Banjul zone, and the tests replay them.

## Tests

```sh
python3 -m unittest server.tests.test_server
```

The tests run on `server/testdata/registry`, the real codes, areas and building footprints of the Banjul zone. They cover the import (checksums, counts, re-runs) and a byte-identical export, every endpoint with its errors, issuing (parity cases, extension blocks, the duplicate checks, outlines, the national border, the daily limit) and status changes.

## Files

| File | What it does |
|---|---|
| `__main__.py` | The command line: `import`, `serve`, `export`, `run` |
| `store.py` | The SQLite schema, the import and export, spatial look-ups |
| `registry.py` | Cards, look-ups, places, issuing and status changes |
| `geo.py` | Footprints (WKT), distances and the overlap test |
| `engine.py` | Loads the reference engine and holds the issuer's limits |
| `api.py` | The HTTP layer and the routes |
| `openapi.yaml` | The API contract |
| `testdata/` | The test registry (Banjul zone) and the parity cases |
