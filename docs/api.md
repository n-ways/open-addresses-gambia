# The registry API

This is the reference for the HTTP API of the registry server in `server/`. Every request and response below was made against a server holding the complete published registry of The Gambia (471,031 codes); the issuing examples come from a copy of that database with an issuing key. The formal contract is [`server/openapi.yaml`](../server/openapi.yaml), and [`server/README.md`](../server/README.md) explains how to deploy the server.

## Conventions

- Base path `/v1`. Requests and responses are JSON in UTF-8. Field names are stable: new fields may be added, existing ones are never renamed or removed within `/v1`.
- Coordinates are WGS 84 degrees, `lat` and `lng`. Distances are metres.
- A code has three forms. The **remembered** form is what people say and write (`Bakau 2389`). The **written** form adds the zone for plates and forms (`BAKAU 2389 · KANIFING`). The **machine** form is for systems and QR codes (`GM-KMC-0001-2389-6`) and is the only one that carries the check digit.
- The **official address** is the government's Plus Code of the entrance with its town (`F8HC+9G6 Bakau`), or a council's street address where the registry has one.
- An **area** is a place whose name appears in codes (a town, village or neighbourhood), identified as `<zone>-<index>` (`KMC-0001`). A **zone** is one of the seven code zones (`BJL`, `KMC`, `WCR`, `NBR`, `LRR`, `CRR`, `URR`).
- Errors always have the shape `{"error": {"code": "...", "message": "..."}}` with the matching HTTP status. `code` is stable and meant for programs; `message` is meant for people. A `409 exists` error also carries `existing`, the card of the code the building already has.
- `POST` and `PATCH` need `Authorization: Bearer <key>` and work only on a deployment started with `ISSUE_KEYS` (see the issuer rule in `server/README.md`). A read-only deployment answers them with `403 read_only`.

| HTTP status | Error codes |
|---|---|
| 400 | `missing_query`, `missing_code`, `missing_name`, `missing_lat`, `missing_lng`, `bad_lat`, `bad_lng`, `bad_point`, `bad_radius`, `bad_limit`, `not_a_code`, `short_plus_code`, `bad_plus_code`, `bad_json`, `bad_body`, `bad_outline` (not a list of points) |
| 401 | `unauthorized` |
| 403 | `read_only` |
| 404 | `not_found`, `unknown`, `not_issued`, `unknown_zone`, `unknown_area`, `unknown_town` |
| 405 | `method_not_allowed` |
| 409 | `exists`, `full`, `retired` (on `PATCH`) |
| 410 | `retired` (on `/v1/find`) |
| 413 | `too_large` |
| 422 | `bad_check`, `invalid_code`, `outside`, `bad_outline` (area out of limits), `far`, `bad_status` |
| 429 | `limit` |
| 500 | `internal` |

## The code card

`GET /v1/codes/{machine}`, `/v1/find`, `/v1/at` and the issuing endpoints return the full card of a code:

| Field | Meaning |
|---|---|
| `machine`, `home`, `written`, `spoken` | The machine, remembered and written forms, and the number as it is read aloud |
| `status` | `provisional`, `confirmed` or `retired` |
| `issued`, `issuedAt` | `bulk` (the first issue) or `on-demand`, and when (UTC) |
| `officialAddress`, `coverage` | The official address and where it comes from (`official`) |
| `area` | The area: `id`, `plateName` (the name in the code), `officialName`, `nameProvisional` (the council has still to confirm the short name), `nearTown` |
| `zone` | `key`, `name`, `iso` (ISO 3166-2) |
| `number`, `check` | The number and the check digit of the machine form |
| `entrance` | The gate or door the code leads to (`kind`: `gate`, `door` or `centre`) |
| `centre` | The compound's centre, from which numbers are ordered |
| `plusCode`, `spot` | The Plus Code of the entrance: full, short, and short with its town |
| `compound` | `class`, `use`, `kind`, `structures`, `floorAreaM2`, `rule`, `enclosed` (engine/SPEC.md section 6) |
| `structures` | Each building of the compound: id, use class, confidence and source, size, floors, data source. A home is never named |
| `postcode` | Always null: The Gambia has no postcodes |
| `registry` | Every column of the code's row in `registry/<zone>.csv.gz`, as published |
| `credit` | The credit line the licence asks for |

Lists (`/v1/near`, `/v1/zones/{key}/codes`, `/v1/spot/decode`) return a shorter card without `compound`, `structures`, `registry` and `credit`; fetch `/v1/codes/{machine}` for the rest.

## GET /v1/health

Liveness and the size of the registry served. Use it for load-balancer and container health checks.

```sh
curl 'http://localhost:8080/v1/health'
```

`200 OK`

```json
{
  "status": "ok",
  "country": "GM",
  "codes": 471031,
  "registryExported": "2026-10-20T15:53:35Z",
  "issuing": false
}
```

## GET /v1/info

The country, its zones with their counts, what the deployment holds and serves, the licences and the credit line.

```sh
curl 'http://localhost:8080/v1/info'
```

`200 OK`

```json
{
  "country": "GM",
  "name": "The Gambia",
  "zones": [
    {
      "key": "BJL",
      "index": 0,
      "name": "Banjul",
      "iso": "GM-B",
      "codes": 4320,
      "areas": 1
    },
    {
      "key": "CRR",
      "index": 1,
      "name": "Central River",
      "iso": "GM-M",
      "codes": 54222,
      "areas": 803
    },
    {
      "key": "KMC",
      "index": 2,
      "name": "Kanifing",
      "iso": null,
      "codes": 45338,
      "areas": 35
    },
    {
      "key": "LRR",
      "index": 3,
      "name": "Lower River",
      "iso": "GM-L",
      "codes": 19377,
      "areas": 181
    },
    {
      "key": "NBR",
      "index": 4,
      "name": "North Bank",
      "iso": "GM-N",
      "codes": 53630,
      "areas": 431
    },
    {
      "key": "URR",
      "index": 5,
      "name": "Upper River",
      "iso": "GM-U",
      "codes": 48103,
      "areas": 478
    },
    {
      "key": "WCR",
      "index": 6,
      "name": "West Coast",
      "iso": "GM-W",
      "codes": 246041,
      "areas": 418
    }
  ],
  "counts": {
    "codes": 471031,
    "byStatus": {
      "provisional": 471031
    },
    "byIssue": {
      "bulk": 471030,
      "on-demand": 1
    },
    "areas": 2347,
    "structures": 672836
  },
  "registry": {
    "exported": "2026-10-20T15:53:35Z",
    "imported": "2026-10-21T13:35:04Z",
    "engine": "internal/addressing/gm (SPEC v1.0)"
  },
  "spec": "engine/SPEC.md 1.0",
  "licences": {
    "data": "ODbL 1.0",
    "code": "Apache 2.0",
    "documents": "CC BY 4.0"
  },
  "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)",
  "source": "https://github.com/n-ways/open-addresses-gambia",
  "issuing": false,
  "example": {
    "home": "Bakau 2389",
    "machine": "GM-KMC-0001-2389-6"
  }
}
```

## GET /v1/codes/{machine}

The full card of one code, by its machine form. The machine form is checked first: a wrong check digit is refused, never corrected to a nearby code.

```sh
curl 'http://localhost:8080/v1/codes/GM-KMC-0001-2389-6'
```

`200 OK`

```json
{
  "machine": "GM-KMC-0001-2389-6",
  "home": "Bakau 2389",
  "written": "BAKAU 2389 · KANIFING",
  "spoken": "Bakau, twenty-three, eighty-nine",
  "status": "provisional",
  "issued": "bulk",
  "issuedAt": "2026-10-20T05:00:52Z",
  "officialAddress": "F8HC+9G6 Bakau",
  "coverage": "official",
  "area": {
    "id": "KMC-0001",
    "plateName": "Bakau",
    "officialName": "Bakau",
    "nameProvisional": false,
    "nearTown": null
  },
  "zone": {
    "key": "KMC",
    "name": "Kanifing",
    "iso": null
  },
  "number": 2389,
  "check": 6,
  "entrance": {
    "lat": 13.47841,
    "lng": -16.6787355,
    "kind": "centre"
  },
  "plusCode": "7C55F8HC+9G6",
  "spot": {
    "code": "7C55F8HC+9G6",
    "short": "F8HC+9G6",
    "withTown": "F8HC+9G6 Bakau"
  },
  "centre": {
    "lat": 13.4784103,
    "lng": -16.6787356
  },
  "compound": {
    "class": "res.maison",
    "use": "residential",
    "kind": "un_batiment",
    "structures": 1,
    "floorAreaM2": 113.1,
    "rule": "single",
    "enclosed": false
  },
  "postcode": null,
  "structures": [
    {
      "index": 1,
      "id": "osm:way/933561063",
      "use": "res.maison",
      "confidence": 0.85,
      "source": "osm:building=residential",
      "status": "existing",
      "footprintM2": 113.1,
      "perimeterM": 43,
      "floors": 1,
      "floorAreaM2": 113.1,
      "data": "osm"
    }
  ],
  "registry": {
    "machine": "GM-KMC-0001-2389-6",
    "home": "Bakau 2389",
    "written": "BAKAU 2389 · KANIFING",
    "lieu": "KMC-0001",
    "official_name": "Bakau",
    "number": "2389",
    "check": "6",
    "status": "provisional",
    "issued": "bulk",
    "issued_at": "2026-10-20T05:00:52Z",
    "entrance_lat": "13.4784100",
    "entrance_lng": "-16.6787355",
    "entrance_kind": "centre",
    "plus_code": "7C55F8HC+9G6",
    "class": "res.maison",
    "use": "residential",
    "kind": "un_batiment",
    "structures": "1",
    "floor_area_m2": "113.1",
    "postcode": "",
    "coverage": "",
    "official_address": "",
    "anchor_lat": "13.4784103",
    "anchor_lng": "-16.6787356",
    "rule": "single",
    "enclosed": "false"
  },
  "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
}
```

Where a council has numbered the door, its street address is the official address:

```sh
curl 'http://localhost:8080/v1/codes/GM-BJL-0000-19459-5'
```

`200 OK`

```json
{
  "machine": "GM-BJL-0000-19459-5",
  "home": "Banjul 19 459",
  "written": "BANJUL 19 459 · BANJUL",
  "spoken": "Banjul, nineteen, four hundred and fifty-nine",
  "status": "provisional",
  "issued": "bulk",
  "issuedAt": "2026-10-20T05:00:45Z",
  "officialAddress": "30A Mam Mberry Njie Street",
  "coverage": "official",
  "area": {
    "id": "BJL-0000",
    "plateName": "Banjul",
    "officialName": "Banjul",
    "nameProvisional": false,
    "nearTown": null
  },
  "zone": {
    "key": "BJL",
    "name": "Banjul",
    "iso": "GM-B"
  },
  "number": 19459,
  "check": 5,
  "entrance": {
    "lat": 13.4525239,
    "lng": -16.5779543,
    "kind": "centre"
  },
  "plusCode": "7C55FC3C+2R3",
  "spot": {
    "code": "7C55FC3C+2R3",
    "short": "FC3C+2R3",
    "withTown": "FC3C+2R3 Banjul"
  },
  "centre": {
    "lat": 13.4525236,
    "lng": -16.5779546
  },
  "compound": {
    "class": "ind.usine",
    "use": "industrial",
    "kind": "un_batiment",
    "structures": 1,
    "floorAreaM2": 73.7,
    "rule": "single",
    "enclosed": false
  },
  "postcode": null,
  "structures": [
    {
      "index": 1,
      "id": "osm:way/638146319",
      "use": "ind.usine",
      "confidence": 0.85,
      "source": "osm:building=service",
      "status": "existing",
      "footprintM2": 73.7,
      "perimeterM": 34.4,
      "floors": 1,
      "floorAreaM2": 73.7,
      "data": "osm",
      "name": "Republic of The Gambia Nurses and Midwives Council"
    }
  ],
  "registry": {
    "machine": "GM-BJL-0000-19459-5",
    "home": "Banjul 19 459",
    "written": "BANJUL 19 459 · BANJUL",
    "lieu": "BJL-0000",
    "official_name": "Banjul",
    "number": "19459",
    "check": "5",
    "status": "provisional",
    "issued": "bulk",
    "issued_at": "2026-10-20T05:00:45Z",
    "entrance_lat": "13.4525239",
    "entrance_lng": "-16.5779543",
    "entrance_kind": "centre",
    "plus_code": "7C55FC3C+2R3",
    "class": "ind.usine",
    "use": "industrial",
    "kind": "un_batiment",
    "structures": "1",
    "floor_area_m2": "73.7",
    "postcode": "",
    "coverage": "official",
    "official_address": "30A Mam Mberry Njie Street",
    "anchor_lat": "13.4525236",
    "anchor_lng": "-16.5779546",
    "rule": "single",
    "enclosed": "false"
  },
  "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
}
```

A wrong check digit:

```sh
curl 'http://localhost:8080/v1/codes/GM-KMC-0001-2389-7'
```

`422 Unprocessable Entity`

```json
{
  "error": {
    "code": "bad_check",
    "message": "GM-KMC-0001-2389-7: the check digit does not match. A digit is wrong or two are swapped; the code is refused rather than guessed."
  }
}
```

A well-formed code that no compound has:

```sh
curl 'http://localhost:8080/v1/codes/GM-KMC-0001-2390-6'
```

`404 Not Found`

```json
{
  "error": {
    "code": "not_issued",
    "message": "GM-KMC-0001-2390-6 is a valid code but no compound has it."
  }
}
```

Anything that is not a machine form:

```sh
curl 'http://localhost:8080/v1/codes/Bakau%202389'
```

`400 Bad Request`

```json
{
  "error": {
    "code": "not_a_code",
    "message": "'Bakau 2389' is not a machine code. Machine codes look like GM-KMC-0001-2389-6."
  }
}
```

## GET /v1/find?q=

Resolves whatever a person or a system has: a remembered code as it is said or typed (any case, accents or spacing, with or without the zone), a machine code, an official address (short Plus Code and town, or a council address), or a full Plus Code. `kind` says how the query was read. A remembered code is unique in the whole country, so no town or region is needed; a zone typed after a comma is only checked.

```sh
curl 'http://localhost:8080/v1/find?q=bakau%2023%2089'
```

`200 OK`

```json
{
  "query": "bakau 23 89",
  "kind": "remembered",
  "results": [
    {
      "machine": "GM-KMC-0001-2389-6",
      "home": "Bakau 2389",
      "written": "BAKAU 2389 · KANIFING",
      "spoken": "Bakau, twenty-three, eighty-nine",
      "status": "provisional",
      "issued": "bulk",
      "issuedAt": "2026-10-20T05:00:52Z",
      "officialAddress": "F8HC+9G6 Bakau",
      "coverage": "official",
      "area": {
        "id": "KMC-0001",
        "plateName": "Bakau",
        "officialName": "Bakau",
        "nameProvisional": false,
        "nearTown": null
      },
      "zone": {
        "key": "KMC",
        "name": "Kanifing",
        "iso": null
      },
      "number": 2389,
      "check": 6,
      "entrance": {
        "lat": 13.47841,
        "lng": -16.6787355,
        "kind": "centre"
      },
      "plusCode": "7C55F8HC+9G6",
      "spot": {
        "code": "7C55F8HC+9G6",
        "short": "F8HC+9G6",
        "withTown": "F8HC+9G6 Bakau"
      },
      "centre": {
        "lat": 13.4784103,
        "lng": -16.6787356
      },
      "compound": {
        "class": "res.maison",
        "use": "residential",
        "kind": "un_batiment",
        "structures": 1,
        "floorAreaM2": 113.1,
        "rule": "single",
        "enclosed": false
      },
      "postcode": null,
      "structures": [
        {
          "index": 1,
          "id": "osm:way/933561063",
          "use": "res.maison",
          "confidence": 0.85,
          "source": "osm:building=residential",
          "status": "existing",
          "footprintM2": 113.1,
          "perimeterM": 43,
          "floors": 1,
          "floorAreaM2": 113.1,
          "data": "osm"
        }
      ],
      "registry": {
        "machine": "GM-KMC-0001-2389-6",
        "home": "Bakau 2389",
        "written": "BAKAU 2389 · KANIFING",
        "lieu": "KMC-0001",
        "official_name": "Bakau",
        "number": "2389",
        "check": "6",
        "status": "provisional",
        "issued": "bulk",
        "issued_at": "2026-10-20T05:00:52Z",
        "entrance_lat": "13.4784100",
        "entrance_lng": "-16.6787355",
        "entrance_kind": "centre",
        "plus_code": "7C55F8HC+9G6",
        "class": "res.maison",
        "use": "residential",
        "kind": "un_batiment",
        "structures": "1",
        "floor_area_m2": "113.1",
        "postcode": "",
        "coverage": "",
        "official_address": "",
        "anchor_lat": "13.4784103",
        "anchor_lng": "-16.6787356",
        "rule": "single",
        "enclosed": "false"
      },
      "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
    }
  ]
}
```

Several places share the name Brikama; the number alone tells them apart:

```sh
curl 'http://localhost:8080/v1/find?q=Brikama%202513'
```

`200 OK`

```json
{
  "query": "Brikama 2513",
  "kind": "remembered",
  "results": [
    {
      "machine": "GM-WCR-0055-2513-6",
      "home": "Brikama 2513",
      "written": "BRIKAMA 2513 · WEST COAST",
      "spoken": "Brikama, twenty-five, thirteen",
      "status": "provisional",
      "issued": "bulk",
      "issuedAt": "2026-10-20T05:01:08Z",
      "officialAddress": "79C4+GRP Brikama",
      "coverage": "official",
      "area": {
        "id": "WCR-0055",
        "plateName": "Brikama",
        "officialName": "Brikama",
        "nameProvisional": false,
        "nearTown": null
      },
      "zone": {
        "key": "WCR",
        "name": "West Coast",
        "iso": "GM-W"
      },
      "number": 2513,
      "check": 6,
      "entrance": {
        "lat": 13.2713373,
        "lng": -16.6429189,
        "kind": "centre"
      },
      "plusCode": "7C5579C4+GRP",
      "spot": {
        "code": "7C5579C4+GRP",
        "short": "79C4+GRP",
        "withTown": "79C4+GRP Brikama"
      },
      "centre": {
        "lat": 13.2713388,
        "lng": -16.6429254
      },
      "compound": {
        "class": "res.concession",
        "use": "residential",
        "kind": "concession",
        "structures": 2,
        "floorAreaM2": 213.3,
        "rule": "satellite",
        "enclosed": false
      },
      "postcode": null,
      "structures": [
        {
          "index": 1,
          "id": "nw:29531130119b",
          "use": "res.concession",
          "confidence": 0.45,
          "source": "shape:multi-structure compound",
          "status": "existing",
          "footprintM2": 198.9,
          "perimeterM": 59.6,
          "floors": 1,
          "floorAreaM2": 198.9,
          "data": "ml"
        },
        {
          "index": 2,
          "id": "nw:e6f9d3501f65",
          "use": "res.annexe",
          "confidence": 0.4,
          "source": "shape:satellite",
          "status": "existing",
          "footprintM2": 14.4,
          "perimeterM": 15.4,
          "floors": 1,
          "floorAreaM2": 14.4,
          "data": "ml"
        }
      ],
      "registry": {
        "machine": "GM-WCR-0055-2513-6",
        "home": "Brikama 2513",
        "written": "BRIKAMA 2513 · WEST COAST",
        "lieu": "WCR-0055",
        "official_name": "Brikama",
        "number": "2513",
        "check": "6",
        "status": "provisional",
        "issued": "bulk",
        "issued_at": "2026-10-20T05:01:08Z",
        "entrance_lat": "13.2713373",
        "entrance_lng": "-16.6429189",
        "entrance_kind": "centre",
        "plus_code": "7C5579C4+GRP",
        "class": "res.concession",
        "use": "residential",
        "kind": "concession",
        "structures": "2",
        "floor_area_m2": "213.3",
        "postcode": "",
        "coverage": "",
        "official_address": "",
        "anchor_lat": "13.2713388",
        "anchor_lng": "-16.6429254",
        "rule": "satellite",
        "enclosed": "false"
      },
      "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
    }
  ]
}
```

The official address:

```sh
curl 'http://localhost:8080/v1/find?q=F8HC%2B9G6%20Bakau'
```

`200 OK`

```json
{
  "query": "F8HC+9G6 Bakau",
  "kind": "official",
  "results": [
    {
      "machine": "GM-KMC-0001-2389-6",
      "home": "Bakau 2389",
      "written": "BAKAU 2389 · KANIFING",
      "spoken": "Bakau, twenty-three, eighty-nine",
      "status": "provisional",
      "issued": "bulk",
      "issuedAt": "2026-10-20T05:00:52Z",
      "officialAddress": "F8HC+9G6 Bakau",
      "coverage": "official",
      "area": {
        "id": "KMC-0001",
        "plateName": "Bakau",
        "officialName": "Bakau",
        "nameProvisional": false,
        "nearTown": null
      },
      "zone": {
        "key": "KMC",
        "name": "Kanifing",
        "iso": null
      },
      "number": 2389,
      "check": 6,
      "entrance": {
        "lat": 13.47841,
        "lng": -16.6787355,
        "kind": "centre"
      },
      "plusCode": "7C55F8HC+9G6",
      "spot": {
        "code": "7C55F8HC+9G6",
        "short": "F8HC+9G6",
        "withTown": "F8HC+9G6 Bakau"
      },
      "centre": {
        "lat": 13.4784103,
        "lng": -16.6787356
      },
      "compound": {
        "class": "res.maison",
        "use": "residential",
        "kind": "un_batiment",
        "structures": 1,
        "floorAreaM2": 113.1,
        "rule": "single",
        "enclosed": false
      },
      "postcode": null,
      "structures": [
        {
          "index": 1,
          "id": "osm:way/933561063",
          "use": "res.maison",
          "confidence": 0.85,
          "source": "osm:building=residential",
          "status": "existing",
          "footprintM2": 113.1,
          "perimeterM": 43,
          "floors": 1,
          "floorAreaM2": 113.1,
          "data": "osm"
        }
      ],
      "registry": {
        "machine": "GM-KMC-0001-2389-6",
        "home": "Bakau 2389",
        "written": "BAKAU 2389 · KANIFING",
        "lieu": "KMC-0001",
        "official_name": "Bakau",
        "number": "2389",
        "check": "6",
        "status": "provisional",
        "issued": "bulk",
        "issued_at": "2026-10-20T05:00:52Z",
        "entrance_lat": "13.4784100",
        "entrance_lng": "-16.6787355",
        "entrance_kind": "centre",
        "plus_code": "7C55F8HC+9G6",
        "class": "res.maison",
        "use": "residential",
        "kind": "un_batiment",
        "structures": "1",
        "floor_area_m2": "113.1",
        "postcode": "",
        "coverage": "",
        "official_address": "",
        "anchor_lat": "13.4784103",
        "anchor_lng": "-16.6787356",
        "rule": "single",
        "enclosed": "false"
      },
      "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
    }
  ]
}
```

A full Plus Code:

```sh
curl 'http://localhost:8080/v1/find?q=7C55F8HC%2B9G6'
```

`200 OK`

```json
{
  "query": "7C55F8HC+9G6",
  "kind": "plus",
  "results": [
    {
      "machine": "GM-KMC-0001-2389-6",
      "home": "Bakau 2389",
      "written": "BAKAU 2389 · KANIFING",
      "spoken": "Bakau, twenty-three, eighty-nine",
      "status": "provisional",
      "issued": "bulk",
      "issuedAt": "2026-10-20T05:00:52Z",
      "officialAddress": "F8HC+9G6 Bakau",
      "coverage": "official",
      "area": {
        "id": "KMC-0001",
        "plateName": "Bakau",
        "officialName": "Bakau",
        "nameProvisional": false,
        "nearTown": null
      },
      "zone": {
        "key": "KMC",
        "name": "Kanifing",
        "iso": null
      },
      "number": 2389,
      "check": 6,
      "entrance": {
        "lat": 13.47841,
        "lng": -16.6787355,
        "kind": "centre"
      },
      "plusCode": "7C55F8HC+9G6",
      "spot": {
        "code": "7C55F8HC+9G6",
        "short": "F8HC+9G6",
        "withTown": "F8HC+9G6 Bakau"
      },
      "centre": {
        "lat": 13.4784103,
        "lng": -16.6787356
      },
      "compound": {
        "class": "res.maison",
        "use": "residential",
        "kind": "un_batiment",
        "structures": 1,
        "floorAreaM2": 113.1,
        "rule": "single",
        "enclosed": false
      },
      "postcode": null,
      "structures": [
        {
          "index": 1,
          "id": "osm:way/933561063",
          "use": "res.maison",
          "confidence": 0.85,
          "source": "osm:building=residential",
          "status": "existing",
          "footprintM2": 113.1,
          "perimeterM": 43,
          "floors": 1,
          "floorAreaM2": 113.1,
          "data": "osm"
        }
      ],
      "registry": {
        "machine": "GM-KMC-0001-2389-6",
        "home": "Bakau 2389",
        "written": "BAKAU 2389 · KANIFING",
        "lieu": "KMC-0001",
        "official_name": "Bakau",
        "number": "2389",
        "check": "6",
        "status": "provisional",
        "issued": "bulk",
        "issued_at": "2026-10-20T05:00:52Z",
        "entrance_lat": "13.4784100",
        "entrance_lng": "-16.6787355",
        "entrance_kind": "centre",
        "plus_code": "7C55F8HC+9G6",
        "class": "res.maison",
        "use": "residential",
        "kind": "un_batiment",
        "structures": "1",
        "floor_area_m2": "113.1",
        "postcode": "",
        "coverage": "",
        "official_address": "",
        "anchor_lat": "13.4784103",
        "anchor_lng": "-16.6787356",
        "rule": "single",
        "enclosed": "false"
      },
      "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
    }
  ]
}
```

A council street address:

```sh
curl 'http://localhost:8080/v1/find?q=30A%20Mam%20Mberry%20Njie%20Street'
```

`200 OK`

```json
{
  "query": "30A Mam Mberry Njie Street",
  "kind": "official",
  "results": [
    {
      "machine": "GM-BJL-0000-19459-5",
      "home": "Banjul 19 459",
      "written": "BANJUL 19 459 · BANJUL",
      "spoken": "Banjul, nineteen, four hundred and fifty-nine",
      "status": "provisional",
      "issued": "bulk",
      "issuedAt": "2026-10-20T05:00:45Z",
      "officialAddress": "30A Mam Mberry Njie Street",
      "coverage": "official",
      "area": {
        "id": "BJL-0000",
        "plateName": "Banjul",
        "officialName": "Banjul",
        "nameProvisional": false,
        "nearTown": null
      },
      "zone": {
        "key": "BJL",
        "name": "Banjul",
        "iso": "GM-B"
      },
      "number": 19459,
      "check": 5,
      "entrance": {
        "lat": 13.4525239,
        "lng": -16.5779543,
        "kind": "centre"
      },
      "plusCode": "7C55FC3C+2R3",
      "spot": {
        "code": "7C55FC3C+2R3",
        "short": "FC3C+2R3",
        "withTown": "FC3C+2R3 Banjul"
      },
      "centre": {
        "lat": 13.4525236,
        "lng": -16.5779546
      },
      "compound": {
        "class": "ind.usine",
        "use": "industrial",
        "kind": "un_batiment",
        "structures": 1,
        "floorAreaM2": 73.7,
        "rule": "single",
        "enclosed": false
      },
      "postcode": null,
      "structures": [
        {
          "index": 1,
          "id": "osm:way/638146319",
          "use": "ind.usine",
          "confidence": 0.85,
          "source": "osm:building=service",
          "status": "existing",
          "footprintM2": 73.7,
          "perimeterM": 34.4,
          "floors": 1,
          "floorAreaM2": 73.7,
          "data": "osm",
          "name": "Republic of The Gambia Nurses and Midwives Council"
        }
      ],
      "registry": {
        "machine": "GM-BJL-0000-19459-5",
        "home": "Banjul 19 459",
        "written": "BANJUL 19 459 · BANJUL",
        "lieu": "BJL-0000",
        "official_name": "Banjul",
        "number": "19459",
        "check": "5",
        "status": "provisional",
        "issued": "bulk",
        "issued_at": "2026-10-20T05:00:45Z",
        "entrance_lat": "13.4525239",
        "entrance_lng": "-16.5779543",
        "entrance_kind": "centre",
        "plus_code": "7C55FC3C+2R3",
        "class": "ind.usine",
        "use": "industrial",
        "kind": "un_batiment",
        "structures": "1",
        "floor_area_m2": "73.7",
        "postcode": "",
        "coverage": "official",
        "official_address": "30A Mam Mberry Njie Street",
        "anchor_lat": "13.4525236",
        "anchor_lng": "-16.5779546",
        "rule": "single",
        "enclosed": "false"
      },
      "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
    }
  ]
}
```

The machine form:

```sh
curl 'http://localhost:8080/v1/find?q=GM-KMC-0001-2389-6'
```

`200 OK`

```json
{
  "query": "GM-KMC-0001-2389-6",
  "kind": "machine",
  "results": [
    {
      "machine": "GM-KMC-0001-2389-6",
      "home": "Bakau 2389",
      "written": "BAKAU 2389 · KANIFING",
      "spoken": "Bakau, twenty-three, eighty-nine",
      "status": "provisional",
      "issued": "bulk",
      "issuedAt": "2026-10-20T05:00:52Z",
      "officialAddress": "F8HC+9G6 Bakau",
      "coverage": "official",
      "area": {
        "id": "KMC-0001",
        "plateName": "Bakau",
        "officialName": "Bakau",
        "nameProvisional": false,
        "nearTown": null
      },
      "zone": {
        "key": "KMC",
        "name": "Kanifing",
        "iso": null
      },
      "number": 2389,
      "check": 6,
      "entrance": {
        "lat": 13.47841,
        "lng": -16.6787355,
        "kind": "centre"
      },
      "plusCode": "7C55F8HC+9G6",
      "spot": {
        "code": "7C55F8HC+9G6",
        "short": "F8HC+9G6",
        "withTown": "F8HC+9G6 Bakau"
      },
      "centre": {
        "lat": 13.4784103,
        "lng": -16.6787356
      },
      "compound": {
        "class": "res.maison",
        "use": "residential",
        "kind": "un_batiment",
        "structures": 1,
        "floorAreaM2": 113.1,
        "rule": "single",
        "enclosed": false
      },
      "postcode": null,
      "structures": [
        {
          "index": 1,
          "id": "osm:way/933561063",
          "use": "res.maison",
          "confidence": 0.85,
          "source": "osm:building=residential",
          "status": "existing",
          "footprintM2": 113.1,
          "perimeterM": 43,
          "floors": 1,
          "floorAreaM2": 113.1,
          "data": "osm"
        }
      ],
      "registry": {
        "machine": "GM-KMC-0001-2389-6",
        "home": "Bakau 2389",
        "written": "BAKAU 2389 · KANIFING",
        "lieu": "KMC-0001",
        "official_name": "Bakau",
        "number": "2389",
        "check": "6",
        "status": "provisional",
        "issued": "bulk",
        "issued_at": "2026-10-20T05:00:52Z",
        "entrance_lat": "13.4784100",
        "entrance_lng": "-16.6787355",
        "entrance_kind": "centre",
        "plus_code": "7C55F8HC+9G6",
        "class": "res.maison",
        "use": "residential",
        "kind": "un_batiment",
        "structures": "1",
        "floor_area_m2": "113.1",
        "postcode": "",
        "coverage": "",
        "official_address": "",
        "anchor_lat": "13.4784103",
        "anchor_lng": "-16.6787356",
        "rule": "single",
        "enclosed": "false"
      },
      "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
    }
  ]
}
```

A number of the place that no compound has yet:

```sh
curl 'http://localhost:8080/v1/find?q=Bakau%202390'
```

`404 Not Found`

```json
{
  "error": {
    "code": "not_issued",
    "message": "No compound has Bakau 2390 yet (the number is in the range of Bakau, Kanifing)."
  }
}
```

A name no place has:

```sh
curl 'http://localhost:8080/v1/find?q=Nowhereville%201234'
```

`404 Not Found`

```json
{
  "error": {
    "code": "unknown",
    "message": "No place in The Gambia has the home code Nowhereville 1234. Check the place name and the number on the plate."
  }
}
```

A home code with the wrong zone after it (the zone is checked, never used to pick another code):

```sh
curl 'http://localhost:8080/v1/find?q=Bakau%202389%2C%20Banjul'
```

`404 Not Found`

```json
{
  "error": {
    "code": "unknown",
    "message": "Bakau 2389 is in Kanifing; what follows it in 'Bakau 2389, Banjul' (a zone or a check digit) does not match."
  }
}
```

A machine form with a wrong check digit:

```sh
curl 'http://localhost:8080/v1/find?q=GM-KMC-0001-2389-7'
```

`422 Unprocessable Entity`

```json
{
  "error": {
    "code": "bad_check",
    "message": "GM-KMC-0001-2389-7: the check digit does not match. A digit is wrong or two are swapped; the code is refused rather than guessed."
  }
}
```

```sh
curl 'http://localhost:8080/v1/find?q='
```

`400 Bad Request`

```json
{
  "error": {
    "code": "missing_query",
    "message": "Give q: a home code (\"Bakau 2389\"), a machine code, an official address or a Plus Code."
  }
}
```

## GET /v1/at?lat=&lng=

The code of the compound at a point, by the issuer's rule: the compound whose building footprint holds the point, else the one whose entrance or footprint is nearest within 12 m (`distanceM`). With none, `status` is `none` and the response gives the zone, the area a new code there would take, and the point's Plus Code. Outside the country, `status` is `outside`: in no zone, or more than 300 m outside the national border whatever the zones say (SPEC 2.1).

```sh
curl 'http://localhost:8080/v1/at?lat=13.47841&lng=-16.67874'
```

`200 OK`

```json
{
  "status": "found",
  "distanceM": 0,
  "code": {
    "machine": "GM-KMC-0001-2389-6",
    "home": "Bakau 2389",
    "written": "BAKAU 2389 · KANIFING",
    "spoken": "Bakau, twenty-three, eighty-nine",
    "status": "provisional",
    "issued": "bulk",
    "issuedAt": "2026-10-20T05:00:52Z",
    "officialAddress": "F8HC+9G6 Bakau",
    "coverage": "official",
    "area": {
      "id": "KMC-0001",
      "plateName": "Bakau",
      "officialName": "Bakau",
      "nameProvisional": false,
      "nearTown": null
    },
    "zone": {
      "key": "KMC",
      "name": "Kanifing",
      "iso": null
    },
    "number": 2389,
    "check": 6,
    "entrance": {
      "lat": 13.47841,
      "lng": -16.6787355,
      "kind": "centre"
    },
    "plusCode": "7C55F8HC+9G6",
    "spot": {
      "code": "7C55F8HC+9G6",
      "short": "F8HC+9G6",
      "withTown": "F8HC+9G6 Bakau"
    },
    "centre": {
      "lat": 13.4784103,
      "lng": -16.6787356
    },
    "compound": {
      "class": "res.maison",
      "use": "residential",
      "kind": "un_batiment",
      "structures": 1,
      "floorAreaM2": 113.1,
      "rule": "single",
      "enclosed": false
    },
    "postcode": null,
    "structures": [
      {
        "index": 1,
        "id": "osm:way/933561063",
        "use": "res.maison",
        "confidence": 0.85,
        "source": "osm:building=residential",
        "status": "existing",
        "footprintM2": 113.1,
        "perimeterM": 43,
        "floors": 1,
        "floorAreaM2": 113.1,
        "data": "osm"
      }
    ],
    "registry": {
      "machine": "GM-KMC-0001-2389-6",
      "home": "Bakau 2389",
      "written": "BAKAU 2389 · KANIFING",
      "lieu": "KMC-0001",
      "official_name": "Bakau",
      "number": "2389",
      "check": "6",
      "status": "provisional",
      "issued": "bulk",
      "issued_at": "2026-10-20T05:00:52Z",
      "entrance_lat": "13.4784100",
      "entrance_lng": "-16.6787355",
      "entrance_kind": "centre",
      "plus_code": "7C55F8HC+9G6",
      "class": "res.maison",
      "use": "residential",
      "kind": "un_batiment",
      "structures": "1",
      "floor_area_m2": "113.1",
      "postcode": "",
      "coverage": "",
      "official_address": "",
      "anchor_lat": "13.4784103",
      "anchor_lng": "-16.6787356",
      "rule": "single",
      "enclosed": "false"
    },
    "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
  },
  "zone": {
    "key": "KMC",
    "name": "Kanifing"
  }
}
```

Open ground:

```sh
curl 'http://localhost:8080/v1/at?lat=13.55&lng=-15.2'
```

`200 OK`

```json
{
  "status": "none",
  "zone": {
    "key": "LRR",
    "name": "Lower River"
  },
  "area": {
    "id": "LRR-0161",
    "zone": "LRR",
    "plateName": "Sukuta",
    "officialName": "Sukuta",
    "kind": "locality",
    "position": {
      "lat": 13.533332,
      "lng": -15.199999
    }
  },
  "spot": {
    "code": "7C56HR22+222",
    "short": "HR22+222",
    "withTown": "HR22+222 Sukuta",
    "zone": "LRR",
    "area": "LRR-0161",
    "cell": {
      "south": 13.55,
      "west": -15.2,
      "north": 13.550025,
      "east": -15.1999688
    }
  }
}
```

Outside The Gambia:

```sh
curl 'http://localhost:8080/v1/at?lat=14.2&lng=-16.0'
```

`200 OK`

```json
{
  "status": "outside",
  "point": {
    "lat": 14.2,
    "lng": -16.0
  },
  "message": "The point is outside The Gambia."
}
```

```sh
curl 'http://localhost:8080/v1/at?lat=13.47'
```

`400 Bad Request`

```json
{
  "error": {
    "code": "missing_lng",
    "message": "lng is required."
  }
}
```

## GET /v1/near?lat=&lng=&radius=&limit=

Codes whose entrance is within `radius` metres (default 100, at most 500), nearest first, at most `limit` (default and maximum 100).

```sh
curl 'http://localhost:8080/v1/near?lat=13.47841&lng=-16.67874&radius=25&limit=3'
```

`200 OK`

```json
{
  "point": {
    "lat": 13.47841,
    "lng": -16.67874
  },
  "radiusM": 25.0,
  "count": 2,
  "codes": [
    {
      "machine": "GM-KMC-0001-2389-6",
      "home": "Bakau 2389",
      "written": "BAKAU 2389 · KANIFING",
      "spoken": "Bakau, twenty-three, eighty-nine",
      "status": "provisional",
      "issued": "bulk",
      "issuedAt": "2026-10-20T05:00:52Z",
      "officialAddress": "F8HC+9G6 Bakau",
      "coverage": "official",
      "area": {
        "id": "KMC-0001",
        "plateName": "Bakau",
        "officialName": "Bakau",
        "nameProvisional": false,
        "nearTown": null
      },
      "zone": {
        "key": "KMC",
        "name": "Kanifing",
        "iso": null
      },
      "number": 2389,
      "check": 6,
      "entrance": {
        "lat": 13.47841,
        "lng": -16.6787355,
        "kind": "centre"
      },
      "plusCode": "7C55F8HC+9G6",
      "spot": {
        "code": "7C55F8HC+9G6",
        "short": "F8HC+9G6",
        "withTown": "F8HC+9G6 Bakau"
      },
      "centre": {
        "lat": 13.4784103,
        "lng": -16.6787356
      },
      "distanceM": 0.5
    },
    {
      "machine": "GM-KMC-0001-2392-2",
      "home": "Bakau 2392",
      "written": "BAKAU 2392 · KANIFING",
      "spoken": "Bakau, twenty-three, ninety-two",
      "status": "provisional",
      "issued": "bulk",
      "issuedAt": "2026-10-20T05:00:52Z",
      "officialAddress": "F8HC+CF9 Bakau",
      "coverage": "official",
      "area": {
        "id": "KMC-0001",
        "plateName": "Bakau",
        "officialName": "Bakau",
        "nameProvisional": false,
        "nearTown": null
      },
      "zone": {
        "key": "KMC",
        "name": "Kanifing",
        "iso": null
      },
      "number": 2392,
      "check": 2,
      "entrance": {
        "lat": 13.4785437,
        "lng": -16.6787632,
        "kind": "centre"
      },
      "plusCode": "7C55F8HC+CF9",
      "spot": {
        "code": "7C55F8HC+CF9",
        "short": "F8HC+CF9",
        "withTown": "F8HC+CF9 Bakau"
      },
      "centre": {
        "lat": 13.4785439,
        "lng": -16.6787633
      },
      "distanceM": 15.0
    }
  ]
}
```

```sh
curl 'http://localhost:8080/v1/near?lat=13.47841&lng=-16.67874&radius=800'
```

`400 Bad Request`

```json
{
  "error": {
    "code": "bad_radius",
    "message": "radius is in metres, more than 0 and at most 500."
  }
}
```

## GET /v1/verify?code=

Checks a machine code: its form, its check digit and whether it is issued. It always answers 200 when a code is given; `valid` and `reason` say what is wrong.

```sh
curl 'http://localhost:8080/v1/verify?code=GM-KMC-0001-2389-6'
```

`200 OK`

```json
{
  "code": "GM-KMC-0001-2389-6",
  "valid": true,
  "reason": null,
  "issued": true,
  "status": "provisional",
  "home": "Bakau 2389",
  "written": "BAKAU 2389 · KANIFING"
}
```

Two digits swapped (2389 typed as 2398):

```sh
curl 'http://localhost:8080/v1/verify?code=GM-KMC-0001-2398-6'
```

`200 OK`

```json
{
  "code": "GM-KMC-0001-2398-6",
  "valid": false,
  "reason": "check digit does not match: a digit is wrong or two are swapped",
  "issued": false,
  "status": null
}
```

```sh
curl 'http://localhost:8080/v1/verify'
```

`400 Bad Request`

```json
{
  "error": {
    "code": "missing_code",
    "message": "Give code: a machine code such as GM-KMC-0001-2389-6."
  }
}
```

## GET /v1/spot?lat=&lng=

The Plus Code of a point (the national digital address), its short form with the town of the area around it, and its cell.

```sh
curl 'http://localhost:8080/v1/spot?lat=13.4783&lng=-16.6787'
```

`200 OK`

```json
{
  "code": "7C55F8HC+8GF",
  "short": "F8HC+8GF",
  "withTown": "F8HC+8GF Bakau",
  "zone": "KMC",
  "area": "KMC-0001",
  "cell": {
    "south": 13.4783,
    "west": -16.6787188,
    "north": 13.478325,
    "east": -16.6786875
  }
}
```

## GET /v1/spot/decode?code=

Decodes a Plus Code, full or short with its town, to its cell, zone and area, and lists the codes whose entrance lies in the cell. A short code needs its town; when several places share the town's name, each gives a cell.

```sh
curl 'http://localhost:8080/v1/spot/decode?code=F8HC%2B9G6%20Bakau'
```

`200 OK`

```json
{
  "query": "F8HC+9G6 Bakau",
  "cells": [
    {
      "code": "7C55F8HC+9G6",
      "centre": {
        "lat": 13.4784125,
        "lng": -16.6787344
      },
      "cell": {
        "south": 13.4784,
        "west": -16.67875,
        "north": 13.478425,
        "east": -16.6787188
      },
      "zone": "KMC",
      "area": "KMC-0001",
      "codes": [
        {
          "machine": "GM-KMC-0001-2389-6",
          "home": "Bakau 2389",
          "written": "BAKAU 2389 · KANIFING",
          "spoken": "Bakau, twenty-three, eighty-nine",
          "status": "provisional",
          "issued": "bulk",
          "issuedAt": "2026-10-20T05:00:52Z",
          "officialAddress": "F8HC+9G6 Bakau",
          "coverage": "official",
          "area": {
            "id": "KMC-0001",
            "plateName": "Bakau",
            "officialName": "Bakau",
            "nameProvisional": false,
            "nearTown": null
          },
          "zone": {
            "key": "KMC",
            "name": "Kanifing",
            "iso": null
          },
          "number": 2389,
          "check": 6,
          "entrance": {
            "lat": 13.47841,
            "lng": -16.6787355,
            "kind": "centre"
          },
          "plusCode": "7C55F8HC+9G6",
          "spot": {
            "code": "7C55F8HC+9G6",
            "short": "F8HC+9G6",
            "withTown": "F8HC+9G6 Bakau"
          },
          "centre": {
            "lat": 13.4784103,
            "lng": -16.6787356
          }
        }
      ]
    }
  ]
}
```

```sh
curl 'http://localhost:8080/v1/spot/decode?code=7C55F8HC%2B8GF'
```

`200 OK`

```json
{
  "query": "7C55F8HC+8GF",
  "cells": [
    {
      "code": "7C55F8HC+8GF",
      "centre": {
        "lat": 13.4783125,
        "lng": -16.6787031
      },
      "cell": {
        "south": 13.4783,
        "west": -16.6787188,
        "north": 13.478325,
        "east": -16.6786875
      },
      "zone": "KMC",
      "area": "KMC-0001",
      "codes": []
    }
  ]
}
```

```sh
curl 'http://localhost:8080/v1/spot/decode?code=F8HC%2B9G6'
```

`400 Bad Request`

```json
{
  "error": {
    "code": "short_plus_code",
    "message": "F8HC+9G6 is a short Plus Code: give the town after it, as in \"F8HC+9G6 Bakau\"."
  }
}
```

## GET /v1/zones

The seven zones with their codes and areas.

```sh
curl 'http://localhost:8080/v1/zones'
```

`200 OK`

```json
{
  "zones": [
    {
      "key": "BJL",
      "index": 0,
      "name": "Banjul",
      "iso": "GM-B",
      "codes": 4320,
      "areas": 1
    },
    {
      "key": "CRR",
      "index": 1,
      "name": "Central River",
      "iso": "GM-M",
      "codes": 54222,
      "areas": 803
    },
    {
      "key": "KMC",
      "index": 2,
      "name": "Kanifing",
      "iso": null,
      "codes": 45338,
      "areas": 35
    },
    {
      "key": "LRR",
      "index": 3,
      "name": "Lower River",
      "iso": "GM-L",
      "codes": 19377,
      "areas": 181
    },
    {
      "key": "NBR",
      "index": 4,
      "name": "North Bank",
      "iso": "GM-N",
      "codes": 53630,
      "areas": 431
    },
    {
      "key": "URR",
      "index": 5,
      "name": "Upper River",
      "iso": "GM-U",
      "codes": 48103,
      "areas": 478
    },
    {
      "key": "WCR",
      "index": 6,
      "name": "West Coast",
      "iso": "GM-W",
      "codes": 246041,
      "areas": 418
    }
  ]
}
```

## GET /v1/zones/{key}

One zone with each of its areas.

```sh
curl 'http://localhost:8080/v1/zones/BJL'
```

`200 OK`

```json
{
  "key": "BJL",
  "index": 0,
  "name": "Banjul",
  "iso": "GM-B",
  "codes": 4320,
  "areas": [
    {
      "id": "BJL-0000",
      "zone": "BJL",
      "plateName": "Banjul",
      "officialName": "Banjul",
      "kind": "city",
      "position": {
        "lat": 13.455351,
        "lng": -16.575649
      },
      "codes": 4320
    }
  ]
}
```

```sh
curl 'http://localhost:8080/v1/zones/XYZ'
```

`404 Not Found`

```json
{
  "error": {
    "code": "unknown_zone",
    "message": "There is no zone XYZ. The zones are BJL, CRR, KMC, LRR, NBR, URR, WCR."
  }
}
```

## GET /v1/zones/{key}/codes?after=&limit=

Every code of a zone in machine-code order, a page at a time (`limit` up to 1,000, default 100). Pass the `next` of one page as `after` to get the following one; `next` is null on the last page.

```sh
curl 'http://localhost:8080/v1/zones/KMC/codes?limit=2'
```

`200 OK`

```json
{
  "zone": "KMC",
  "codes": [
    {
      "machine": "GM-KMC-0000-1001-5",
      "home": "Ampaya 1001",
      "written": "AMPAYA 1001 · KANIFING",
      "spoken": "Ampaya, ten, oh one",
      "status": "provisional",
      "issued": "bulk",
      "issuedAt": "2026-10-20T05:00:52Z",
      "officialAddress": "C8W5+GV4 Ampaya",
      "coverage": "official",
      "area": {
        "id": "KMC-0000",
        "plateName": "Ampaya",
        "officialName": "Ampaya",
        "nameProvisional": false,
        "nearTown": null
      },
      "zone": {
        "key": "KMC",
        "name": "Kanifing",
        "iso": null
      },
      "number": 1001,
      "check": 5,
      "entrance": {
        "lat": 13.4462745,
        "lng": -16.6902836,
        "kind": "centre"
      },
      "plusCode": "7C55C8W5+GV4",
      "spot": {
        "code": "7C55C8W5+GV4",
        "short": "C8W5+GV4",
        "withTown": "C8W5+GV4 Ampaya"
      },
      "centre": {
        "lat": 13.4462748,
        "lng": -16.6902841
      }
    },
    {
      "machine": "GM-KMC-0000-1004-4",
      "home": "Ampaya 1004",
      "written": "AMPAYA 1004 · KANIFING",
      "spoken": "Ampaya, ten, oh four",
      "status": "provisional",
      "issued": "bulk",
      "issuedAt": "2026-10-20T05:00:52Z",
      "officialAddress": "C8W5+FWG Ampaya",
      "coverage": "official",
      "area": {
        "id": "KMC-0000",
        "plateName": "Ampaya",
        "officialName": "Ampaya",
        "nameProvisional": false,
        "nearTown": null
      },
      "zone": {
        "key": "KMC",
        "name": "Kanifing",
        "iso": null
      },
      "number": 1004,
      "check": 4,
      "entrance": {
        "lat": 13.4461775,
        "lng": -16.6901867,
        "kind": "centre"
      },
      "plusCode": "7C55C8W5+FWG",
      "spot": {
        "code": "7C55C8W5+FWG",
        "short": "C8W5+FWG",
        "withTown": "C8W5+FWG Ampaya"
      },
      "centre": {
        "lat": 13.4461778,
        "lng": -16.6901864
      }
    }
  ],
  "next": "GM-KMC-0000-1004-4"
}
```

```sh
curl 'http://localhost:8080/v1/zones/KMC/codes?limit=2&after=GM-KMC-0000-1004-4'
```

`200 OK`

```json
{
  "zone": "KMC",
  "codes": [
    {
      "machine": "GM-KMC-0000-1007-7",
      "home": "Ampaya 1007",
      "written": "AMPAYA 1007 · KANIFING",
      "spoken": "Ampaya, ten, oh seven",
      "status": "provisional",
      "issued": "bulk",
      "issuedAt": "2026-10-20T05:00:52Z",
      "officialAddress": "C8W6+V3Q Ampaya",
      "coverage": "official",
      "area": {
        "id": "KMC-0000",
        "plateName": "Ampaya",
        "officialName": "Ampaya",
        "nameProvisional": false,
        "nearTown": null
      },
      "zone": {
        "key": "KMC",
        "name": "Kanifing",
        "iso": null
      },
      "number": 1007,
      "check": 7,
      "entrance": {
        "lat": 13.4472179,
        "lng": -16.6897688,
        "kind": "centre"
      },
      "plusCode": "7C55C8W6+V3Q",
      "spot": {
        "code": "7C55C8W6+V3Q",
        "short": "C8W6+V3Q",
        "withTown": "C8W6+V3Q Ampaya"
      },
      "centre": {
        "lat": 13.4472183,
        "lng": -16.6897689
      }
    },
    {
      "machine": "GM-KMC-0000-1010-6",
      "home": "Ampaya 1010",
      "written": "AMPAYA 1010 · KANIFING",
      "spoken": "Ampaya, ten, ten",
      "status": "provisional",
      "issued": "bulk",
      "issuedAt": "2026-10-20T05:00:52Z",
      "officialAddress": "C8W5+MXC Ampaya",
      "coverage": "official",
      "area": {
        "id": "KMC-0000",
        "plateName": "Ampaya",
        "officialName": "Ampaya",
        "nameProvisional": false,
        "nearTown": null
      },
      "zone": {
        "key": "KMC",
        "name": "Kanifing",
        "iso": null
      },
      "number": 1010,
      "check": 6,
      "entrance": {
        "lat": 13.4466801,
        "lng": -16.6901081,
        "kind": "centre"
      },
      "plusCode": "7C55C8W5+MXC",
      "spot": {
        "code": "7C55C8W5+MXC",
        "short": "C8W5+MXC",
        "withTown": "C8W5+MXC Ampaya"
      },
      "centre": {
        "lat": 13.44668,
        "lng": -16.6901078
      }
    }
  ],
  "next": "GM-KMC-0000-1010-6"
}
```

## GET /v1/areas?name=

The areas a name refers to: the plate name, the official name or an alias, matched by the national name key, so spellings that sound alike (Kerr and Keur, Serrekunda and Serre Kunda) find the same places.

```sh
curl 'http://localhost:8080/v1/areas?name=Brikama'
```

`200 OK`

```json
{
  "name": "Brikama",
  "areas": [
    {
      "id": "CRR-0071",
      "zone": "CRR",
      "plateName": "Brikama",
      "officialName": "Brikama",
      "kind": "locality",
      "position": {
        "lat": 13.566673,
        "lng": -15.333328
      },
      "codes": 32
    },
    {
      "id": "CRR-0073",
      "zone": "CRR",
      "plateName": "Brikama",
      "officialName": "Brikama Nding",
      "kind": "village",
      "position": {
        "lat": 13.540043,
        "lng": -14.943374
      },
      "codes": 168
    },
    {
      "id": "LRR-0017",
      "zone": "LRR",
      "plateName": "Brikama",
      "officialName": "Brikama",
      "kind": "locality",
      "position": {
        "lat": 13.316669,
        "lng": -15.933332
      },
      "codes": 14
    },
    {
      "id": "NBR-0054",
      "zone": "NBR",
      "plateName": "Brikama",
      "officialName": "Brikama",
      "kind": "village",
      "position": {
        "lat": 13.576893,
        "lng": -15.884496
      },
      "codes": 9
    },
    {
      "id": "WCR-0055",
      "zone": "WCR",
      "plateName": "Brikama",
      "officialName": "Brikama",
      "kind": "city",
      "position": {
        "lat": 13.274393,
        "lng": -16.645442
      },
      "codes": 2255
    }
  ]
}
```

```sh
curl 'http://localhost:8080/v1/areas'
```

`400 Bad Request`

```json
{
  "error": {
    "code": "missing_name",
    "message": "Give name: a place name as on the plate or its official name."
  }
}
```

## GET /v1/areas/{id}

One area: its names, kind and position, its name family and number blocks, how many codes it holds and how many numbers are still free, and the other areas with the same name.

```sh
curl 'http://localhost:8080/v1/areas/KMC-0001'
```

`200 OK`

```json
{
  "id": "KMC-0001",
  "zone": "KMC",
  "plateName": "Bakau",
  "officialName": "Bakau",
  "kind": "suburb",
  "position": {
    "lat": 13.47745,
    "lng": -16.67791
  },
  "zoneName": "Kanifing",
  "aliases": [],
  "nearTown": null,
  "nameProvisional": false,
  "coverage": "nways",
  "nameKey": "bakau",
  "family": 75,
  "digits": 4,
  "blocks": [
    [
      1000,
      5399
    ]
  ],
  "sameName": [],
  "codes": {
    "total": 1456,
    "provisional": 1456,
    "confirmed": 0,
    "retired": 0
  },
  "numbers": {
    "capacity": 4400,
    "used": 1456,
    "free": 2944
  }
}
```

```sh
curl 'http://localhost:8080/v1/areas/KMC-9999'
```

`404 Not Found`

```json
{
  "error": {
    "code": "unknown_area",
    "message": "There is no area KMC-9999. Area ids look like KMC-0001."
  }
}
```

## POST /v1/codes

Issues a code for a new compound, or for another door of a compound that has one (`of`), by the issuer's rules (server/README.md, "How a code is issued"). The body is `{"lat", "lng"}` with an optional `outline` (the building, as `[lng, lat]` pairs) or `of` (the machine code of the compound). The code is provisional. Only a deployment designated as the issuer may do this.

```sh
curl -X POST -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"lat": 13.3495584, "lng": -16.6246945}' 'http://localhost:8080/v1/codes'
```

`201 Created`

```json
{
  "machine": "GM-WCR-0243-11946-0",
  "home": "Karewan 11 946",
  "written": "KAREWAN 11 946 · WEST COAST",
  "spoken": "Karewan, eleven, nine hundred and forty-six",
  "status": "provisional",
  "issued": "on-demand",
  "issuedAt": "2026-10-21T13:53:22Z",
  "officialAddress": "89XG+R4F Karewan",
  "coverage": "official",
  "area": {
    "id": "WCR-0243",
    "plateName": "Karewan",
    "officialName": "Karewan",
    "nameProvisional": false,
    "nearTown": null
  },
  "zone": {
    "key": "WCR",
    "name": "West Coast",
    "iso": "GM-W"
  },
  "number": 11946,
  "check": 0,
  "entrance": {
    "lat": 13.3495584,
    "lng": -16.6246945,
    "kind": "centre"
  },
  "plusCode": "7C5589XG+R4F",
  "spot": {
    "code": "7C5589XG+R4F",
    "short": "89XG+R4F",
    "withTown": "89XG+R4F Karewan"
  },
  "centre": {
    "lat": 13.3495584,
    "lng": -16.6246945
  },
  "compound": {
    "class": null,
    "use": "unknown",
    "kind": "un_batiment",
    "structures": 0,
    "floorAreaM2": 0.0,
    "rule": null,
    "enclosed": false
  },
  "postcode": null,
  "structures": [],
  "registry": {
    "machine": "GM-WCR-0243-11946-0",
    "home": "Karewan 11 946",
    "written": "KAREWAN 11 946 · WEST COAST",
    "lieu": "WCR-0243",
    "official_name": "Karewan",
    "number": "11946",
    "check": "0",
    "status": "provisional",
    "issued": "on-demand",
    "issued_at": "2026-10-21T13:53:22Z",
    "entrance_lat": "13.3495584",
    "entrance_lng": "-16.6246945",
    "entrance_kind": "centre",
    "plus_code": "7C5589XG+R4F",
    "class": "",
    "use": "unknown",
    "kind": "un_batiment",
    "structures": "0",
    "floor_area_m2": "0.0",
    "postcode": "",
    "coverage": "",
    "official_address": "",
    "anchor_lat": "13.3495584",
    "anchor_lng": "-16.6246945",
    "rule": "",
    "enclosed": "false"
  },
  "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
}
```

Another door of Bakau 2389:

```sh
curl -X POST -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"lat": 13.47842, "lng": -16.67871, "of": "GM-KMC-0001-2389-6"}' 'http://localhost:8080/v1/codes'
```

`201 Created`

```json
{
  "machine": "GM-KMC-0001-2390-6",
  "home": "Bakau 2390",
  "written": "BAKAU 2390 · KANIFING",
  "spoken": "Bakau, twenty-three, ninety",
  "status": "provisional",
  "issued": "on-demand",
  "issuedAt": "2026-10-21T13:53:22Z",
  "officialAddress": "F8HC+9G7 Bakau",
  "coverage": "official",
  "area": {
    "id": "KMC-0001",
    "plateName": "Bakau",
    "officialName": "Bakau",
    "nameProvisional": false,
    "nearTown": null
  },
  "zone": {
    "key": "KMC",
    "name": "Kanifing",
    "iso": null
  },
  "number": 2390,
  "check": 6,
  "entrance": {
    "lat": 13.47842,
    "lng": -16.67871,
    "kind": "door"
  },
  "plusCode": "7C55F8HC+9G7",
  "spot": {
    "code": "7C55F8HC+9G7",
    "short": "F8HC+9G7",
    "withTown": "F8HC+9G7 Bakau"
  },
  "centre": {
    "lat": 13.47842,
    "lng": -16.67871
  },
  "compound": {
    "class": null,
    "use": "unknown",
    "kind": "door",
    "structures": 0,
    "floorAreaM2": 0.0,
    "rule": null,
    "enclosed": false
  },
  "postcode": null,
  "structures": [],
  "registry": {
    "machine": "GM-KMC-0001-2390-6",
    "home": "Bakau 2390",
    "written": "BAKAU 2390 · KANIFING",
    "lieu": "KMC-0001",
    "official_name": "Bakau",
    "number": "2390",
    "check": "6",
    "status": "provisional",
    "issued": "on-demand",
    "issued_at": "2026-10-21T13:53:22Z",
    "entrance_lat": "13.4784200",
    "entrance_lng": "-16.6787100",
    "entrance_kind": "door",
    "plus_code": "7C55F8HC+9G7",
    "class": "",
    "use": "unknown",
    "kind": "door",
    "structures": "0",
    "floor_area_m2": "0.0",
    "postcode": "",
    "coverage": "",
    "official_address": "",
    "anchor_lat": "13.4784200",
    "anchor_lng": "-16.6787100",
    "rule": "",
    "enclosed": "false"
  },
  "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
}
```

With the building's outline, which is kept as the compound's footprint:

```sh
curl -X POST -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"lat": 13.3247953, "lng": -16.5969105, "outline": [[-16.5969505, 13.3247553], [-16.5968705, 13.3247553], [-16.5968705, 13.3248353], [-16.5969505, 13.3248353]]}' 'http://localhost:8080/v1/codes'
```

`201 Created`

```json
{
  "machine": "GM-WCR-0266-2312-5",
  "home": "Kubuni 2312",
  "written": "KUBUNI 2312 · WEST COAST",
  "spoken": "Kubuni, twenty-three, twelve",
  "status": "provisional",
  "issued": "on-demand",
  "issuedAt": "2026-10-21T13:53:22Z",
  "officialAddress": "8CF3+W68 Kubuni",
  "coverage": "official",
  "area": {
    "id": "WCR-0266",
    "plateName": "Kubuni",
    "officialName": "Kubuni",
    "nameProvisional": false,
    "nearTown": null
  },
  "zone": {
    "key": "WCR",
    "name": "West Coast",
    "iso": "GM-W"
  },
  "number": 2312,
  "check": 5,
  "entrance": {
    "lat": 13.3247953,
    "lng": -16.5969105,
    "kind": "centre"
  },
  "plusCode": "7C558CF3+W68",
  "spot": {
    "code": "7C558CF3+W68",
    "short": "8CF3+W68",
    "withTown": "8CF3+W68 Kubuni"
  },
  "centre": {
    "lat": 13.3247953,
    "lng": -16.5969105
  },
  "compound": {
    "class": "res.maison",
    "use": "residential",
    "kind": "un_batiment",
    "structures": 1,
    "floorAreaM2": 76.7,
    "rule": null,
    "enclosed": false
  },
  "postcode": null,
  "structures": [
    {
      "index": 1,
      "id": "people:GM-WCR-0266-2312-5",
      "use": "res.maison",
      "confidence": 0.45,
      "source": "shape:house-size",
      "status": "existing",
      "footprintM2": 76.7,
      "perimeterM": 35.1,
      "floors": 1,
      "floorAreaM2": 76.7,
      "data": "people"
    }
  ],
  "registry": {
    "machine": "GM-WCR-0266-2312-5",
    "home": "Kubuni 2312",
    "written": "KUBUNI 2312 · WEST COAST",
    "lieu": "WCR-0266",
    "official_name": "Kubuni",
    "number": "2312",
    "check": "5",
    "status": "provisional",
    "issued": "on-demand",
    "issued_at": "2026-10-21T13:53:22Z",
    "entrance_lat": "13.3247953",
    "entrance_lng": "-16.5969105",
    "entrance_kind": "centre",
    "plus_code": "7C558CF3+W68",
    "class": "res.maison",
    "use": "residential",
    "kind": "un_batiment",
    "structures": "1",
    "floor_area_m2": "76.7",
    "postcode": "",
    "coverage": "",
    "official_address": "",
    "anchor_lat": "13.3247953",
    "anchor_lng": "-16.5969105",
    "rule": "",
    "enclosed": "false"
  },
  "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
}
```

A building that already has its code:

```sh
curl -X POST -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"lat": 13.47841, "lng": -16.67874}' 'http://localhost:8080/v1/codes'
```

`409 Conflict`

```json
{
  "error": {
    "code": "exists",
    "message": "This building already has its code: Bakau 2389.",
    "existing": {
      "machine": "GM-KMC-0001-2389-6",
      "home": "Bakau 2389",
      "written": "BAKAU 2389 · KANIFING",
      "spoken": "Bakau, twenty-three, eighty-nine",
      "status": "provisional",
      "issued": "bulk",
      "issuedAt": "2026-10-20T05:00:52Z",
      "officialAddress": "F8HC+9G6 Bakau",
      "coverage": "official",
      "area": {
        "id": "KMC-0001",
        "plateName": "Bakau",
        "officialName": "Bakau",
        "nameProvisional": false,
        "nearTown": null
      },
      "zone": {
        "key": "KMC",
        "name": "Kanifing",
        "iso": null
      },
      "number": 2389,
      "check": 6,
      "entrance": {
        "lat": 13.47841,
        "lng": -16.6787355,
        "kind": "centre"
      },
      "plusCode": "7C55F8HC+9G6",
      "spot": {
        "code": "7C55F8HC+9G6",
        "short": "F8HC+9G6",
        "withTown": "F8HC+9G6 Bakau"
      },
      "centre": {
        "lat": 13.4784103,
        "lng": -16.6787356
      },
      "compound": {
        "class": "res.maison",
        "use": "residential",
        "kind": "un_batiment",
        "structures": 1,
        "floorAreaM2": 113.1,
        "rule": "single",
        "enclosed": false
      },
      "postcode": null,
      "structures": [
        {
          "index": 1,
          "id": "osm:way/933561063",
          "use": "res.maison",
          "confidence": 0.85,
          "source": "osm:building=residential",
          "status": "existing",
          "footprintM2": 113.1,
          "perimeterM": 43,
          "floors": 1,
          "floorAreaM2": 113.1,
          "data": "osm"
        }
      ],
      "registry": {
        "machine": "GM-KMC-0001-2389-6",
        "home": "Bakau 2389",
        "written": "BAKAU 2389 · KANIFING",
        "lieu": "KMC-0001",
        "official_name": "Bakau",
        "number": "2389",
        "check": "6",
        "status": "provisional",
        "issued": "bulk",
        "issued_at": "2026-10-20T05:00:52Z",
        "entrance_lat": "13.4784100",
        "entrance_lng": "-16.6787355",
        "entrance_kind": "centre",
        "plus_code": "7C55F8HC+9G6",
        "class": "res.maison",
        "use": "residential",
        "kind": "un_batiment",
        "structures": "1",
        "floor_area_m2": "113.1",
        "postcode": "",
        "coverage": "",
        "official_address": "",
        "anchor_lat": "13.4784103",
        "anchor_lng": "-16.6787356",
        "rule": "single",
        "enclosed": "false"
      },
      "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
    }
  }
}
```

```sh
curl -X POST -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"lat": 14.2, "lng": -16.0}' 'http://localhost:8080/v1/codes'
```

`422 Unprocessable Entity`

```json
{
  "error": {
    "code": "outside",
    "message": "That point is outside The Gambia, so it cannot have a code."
  }
}
```

An outline too small to be a building:

```sh
curl -X POST -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"lat": 13.2721385, "lng": -16.6218754, "outline": [[-16.6218754, 13.2721385], [-16.62187, 13.2721385], [-16.62187, 13.27214]]}' 'http://localhost:8080/v1/codes'
```

`422 Unprocessable Entity`

```json
{
  "error": {
    "code": "bad_outline",
    "message": "That outline is 0 m², but a compound's building is between 12 m² and 2 ha."
  }
}
```

A door far from the compound's entrance:

```sh
curl -X POST -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"lat": 13.47, "lng": -16.67, "of": "GM-KMC-0001-2389-6"}' 'http://localhost:8080/v1/codes'
```

`422 Unprocessable Entity`

```json
{
  "error": {
    "code": "far",
    "message": "That door is more than 80 m from Bakau 2389's entrance."
  }
}
```

A door for a machine form with a wrong check digit:

```sh
curl -X POST -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"lat": 13.47842, "lng": -16.67871, "of": "GM-KMC-0001-2389-7"}' 'http://localhost:8080/v1/codes'
```

`422 Unprocessable Entity`

```json
{
  "error": {
    "code": "bad_check",
    "message": "GM-KMC-0001-2389-7: the check digit does not match. A digit is wrong or two are swapped; the code is refused rather than guessed."
  }
}
```

Without a key:

```sh
curl -X POST -H 'Content-Type: application/json' -d '{"lat": 13.3495584, "lng": -16.6246945}' 'http://localhost:8080/v1/codes'
```

`401 Unauthorized`

```json
{
  "error": {
    "code": "unauthorized",
    "message": "A valid bearer key is required (Authorization: Bearer <key>)."
  }
}
```

On a read-only deployment:

```sh
curl -X POST -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"lat": 13.3495584, "lng": -16.6246945}' 'http://localhost:8080/v1/codes'
```

`403 Forbidden`

```json
{
  "error": {
    "code": "read_only",
    "message": "This deployment is read-only: it serves the published registry and does not issue codes."
  }
}
```

## PATCH /v1/codes/{machine}

Changes a code's status or moves its entrance. A provisional code can be confirmed or retired; a confirmed one can go back to provisional or be retired. A retired code never returns and its number is never given again. The entrance moves at most 80 m and becomes a `gate`.

```sh
curl -X PATCH -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"status": "confirmed"}' 'http://localhost:8080/v1/codes/GM-WCR-0243-11946-0'
```

`200 OK`

```json
{
  "machine": "GM-WCR-0243-11946-0",
  "home": "Karewan 11 946",
  "written": "KAREWAN 11 946 · WEST COAST",
  "spoken": "Karewan, eleven, nine hundred and forty-six",
  "status": "confirmed",
  "issued": "on-demand",
  "issuedAt": "2026-10-21T13:53:22Z",
  "officialAddress": "89XG+R4F Karewan",
  "coverage": "official",
  "area": {
    "id": "WCR-0243",
    "plateName": "Karewan",
    "officialName": "Karewan",
    "nameProvisional": false,
    "nearTown": null
  },
  "zone": {
    "key": "WCR",
    "name": "West Coast",
    "iso": "GM-W"
  },
  "number": 11946,
  "check": 0,
  "entrance": {
    "lat": 13.3495584,
    "lng": -16.6246945,
    "kind": "centre"
  },
  "plusCode": "7C5589XG+R4F",
  "spot": {
    "code": "7C5589XG+R4F",
    "short": "89XG+R4F",
    "withTown": "89XG+R4F Karewan"
  },
  "centre": {
    "lat": 13.3495584,
    "lng": -16.6246945
  },
  "compound": {
    "class": null,
    "use": "unknown",
    "kind": "un_batiment",
    "structures": 0,
    "floorAreaM2": 0.0,
    "rule": null,
    "enclosed": false
  },
  "postcode": null,
  "structures": [],
  "registry": {
    "machine": "GM-WCR-0243-11946-0",
    "home": "Karewan 11 946",
    "written": "KAREWAN 11 946 · WEST COAST",
    "lieu": "WCR-0243",
    "official_name": "Karewan",
    "number": "11946",
    "check": "0",
    "status": "confirmed",
    "issued": "on-demand",
    "issued_at": "2026-10-21T13:53:22Z",
    "entrance_lat": "13.3495584",
    "entrance_lng": "-16.6246945",
    "entrance_kind": "centre",
    "plus_code": "7C5589XG+R4F",
    "class": "",
    "use": "unknown",
    "kind": "un_batiment",
    "structures": "0",
    "floor_area_m2": "0.0",
    "postcode": "",
    "coverage": "",
    "official_address": "",
    "anchor_lat": "13.3495584",
    "anchor_lng": "-16.6246945",
    "rule": "",
    "enclosed": "false"
  },
  "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
}
```

```sh
curl -X PATCH -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"entrance": {"lat": 13.3497, "lng": -16.6247}}' 'http://localhost:8080/v1/codes/GM-WCR-0243-11946-0'
```

`200 OK`

```json
{
  "machine": "GM-WCR-0243-11946-0",
  "home": "Karewan 11 946",
  "written": "KAREWAN 11 946 · WEST COAST",
  "spoken": "Karewan, eleven, nine hundred and forty-six",
  "status": "confirmed",
  "issued": "on-demand",
  "issuedAt": "2026-10-21T13:53:22Z",
  "officialAddress": "89XG+V4M Karewan",
  "coverage": "official",
  "area": {
    "id": "WCR-0243",
    "plateName": "Karewan",
    "officialName": "Karewan",
    "nameProvisional": false,
    "nearTown": null
  },
  "zone": {
    "key": "WCR",
    "name": "West Coast",
    "iso": "GM-W"
  },
  "number": 11946,
  "check": 0,
  "entrance": {
    "lat": 13.3497,
    "lng": -16.6247,
    "kind": "gate"
  },
  "plusCode": "7C5589XG+V4M",
  "spot": {
    "code": "7C5589XG+V4M",
    "short": "89XG+V4M",
    "withTown": "89XG+V4M Karewan"
  },
  "centre": {
    "lat": 13.3495584,
    "lng": -16.6246945
  },
  "compound": {
    "class": null,
    "use": "unknown",
    "kind": "un_batiment",
    "structures": 0,
    "floorAreaM2": 0.0,
    "rule": null,
    "enclosed": false
  },
  "postcode": null,
  "structures": [],
  "registry": {
    "machine": "GM-WCR-0243-11946-0",
    "home": "Karewan 11 946",
    "written": "KAREWAN 11 946 · WEST COAST",
    "lieu": "WCR-0243",
    "official_name": "Karewan",
    "number": "11946",
    "check": "0",
    "status": "confirmed",
    "issued": "on-demand",
    "issued_at": "2026-10-21T13:53:22Z",
    "entrance_lat": "13.3497000",
    "entrance_lng": "-16.6247000",
    "entrance_kind": "gate",
    "plus_code": "7C5589XG+V4M",
    "class": "",
    "use": "unknown",
    "kind": "un_batiment",
    "structures": "0",
    "floor_area_m2": "0.0",
    "postcode": "",
    "coverage": "",
    "official_address": "",
    "anchor_lat": "13.3495584",
    "anchor_lng": "-16.6246945",
    "rule": "",
    "enclosed": "false"
  },
  "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
}
```

```sh
curl -X PATCH -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"status": "retired"}' 'http://localhost:8080/v1/codes/GM-KMC-0001-2392-2'
```

`200 OK`

```json
{
  "machine": "GM-KMC-0001-2392-2",
  "home": "Bakau 2392",
  "written": "BAKAU 2392 · KANIFING",
  "spoken": "Bakau, twenty-three, ninety-two",
  "status": "retired",
  "issued": "bulk",
  "issuedAt": "2026-10-20T05:00:52Z",
  "officialAddress": "F8HC+CF9 Bakau",
  "coverage": "official",
  "area": {
    "id": "KMC-0001",
    "plateName": "Bakau",
    "officialName": "Bakau",
    "nameProvisional": false,
    "nearTown": null
  },
  "zone": {
    "key": "KMC",
    "name": "Kanifing",
    "iso": null
  },
  "number": 2392,
  "check": 2,
  "entrance": {
    "lat": 13.4785437,
    "lng": -16.6787632,
    "kind": "centre"
  },
  "plusCode": "7C55F8HC+CF9",
  "spot": {
    "code": "7C55F8HC+CF9",
    "short": "F8HC+CF9",
    "withTown": "F8HC+CF9 Bakau"
  },
  "centre": {
    "lat": 13.4785439,
    "lng": -16.6787633
  },
  "compound": {
    "class": "res.maison",
    "use": "residential",
    "kind": "un_batiment",
    "structures": 1,
    "floorAreaM2": 149.5,
    "rule": "single",
    "enclosed": false
  },
  "postcode": null,
  "structures": [
    {
      "index": 1,
      "id": "osm:way/933561062",
      "use": "res.maison",
      "confidence": 0.85,
      "source": "osm:building=residential",
      "status": "existing",
      "footprintM2": 149.5,
      "perimeterM": 50.2,
      "floors": 1,
      "floorAreaM2": 149.5,
      "data": "osm"
    }
  ],
  "registry": {
    "machine": "GM-KMC-0001-2392-2",
    "home": "Bakau 2392",
    "written": "BAKAU 2392 · KANIFING",
    "lieu": "KMC-0001",
    "official_name": "Bakau",
    "number": "2392",
    "check": "2",
    "status": "retired",
    "issued": "bulk",
    "issued_at": "2026-10-20T05:00:52Z",
    "entrance_lat": "13.4785437",
    "entrance_lng": "-16.6787632",
    "entrance_kind": "centre",
    "plus_code": "7C55F8HC+CF9",
    "class": "res.maison",
    "use": "residential",
    "kind": "un_batiment",
    "structures": "1",
    "floor_area_m2": "149.5",
    "postcode": "",
    "coverage": "",
    "official_address": "",
    "anchor_lat": "13.4785439",
    "anchor_lng": "-16.6787633",
    "rule": "single",
    "enclosed": "false"
  },
  "credit": "N-Ways Addressing for The Gambia, © N-WAYS LIMITED (nways.ng)"
}
```

```sh
curl -X PATCH -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"status": "confirmed"}' 'http://localhost:8080/v1/codes/GM-KMC-0001-2392-2'
```

`409 Conflict`

```json
{
  "error": {
    "code": "retired",
    "message": "Bakau 2392 is retired. A retired code never comes back and its number is never reused."
  }
}
```

```sh
curl -X PATCH -H "Authorization: Bearer $ISSUE_KEY" -H 'Content-Type: application/json' -d '{"status": "approved"}' 'http://localhost:8080/v1/codes/GM-KMC-0001-2389-6'
```

`422 Unprocessable Entity`

```json
{
  "error": {
    "code": "bad_status",
    "message": "A provisional code can become confirmed or retired, not 'approved'."
  }
}
```

## Unknown paths

Every path outside the list above:

```sh
curl 'http://localhost:8080/v1/addresses'
```

`404 Not Found`

```json
{
  "error": {
    "code": "not_found",
    "message": "There is no endpoint /v1/addresses. See /v1/info and server/openapi.yaml."
  }
}
```
