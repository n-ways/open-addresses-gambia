# Governance

**Issued on 20 October 2026; open (LICENSING.md).** These are N-Ways home codes. They are not The Gambia's official addresses: the official address is the government's Plus Code (National Digital Addressing Policy, 2023), and N-Ways always shows it first. Nobody may call a home code official unless a Gambian public authority adopts it.

## Who issues

The Gambia has one issuer at a time. Today it is N-WAYS LIMITED. The State may designate another body (for example GAMPOST or a ministry), and the role then passes whole: the outgoing issuer exports its registry, the new one imports it, and the outgoing one stops issuing.

Anyone may run the registry server in `server/` to serve the published codes. A deployment issues codes only if the State or N-WAYS LIMITED has designated it as the issuer; every other deployment runs read-only. Numbering is deterministic, so two issuers working from the same registry would give the same free number to two different compounds: one issuer is what keeps every code unique.

## What never changes

- the 7 zones and their keys;
- an issued home code, and its number (a retired number is never given again);
- the blocks of each name's national range (blocks are only ever added);
- the name key, the check digit and the numbering rules (SPEC.md section 9).

## What changes, and how

- **Building profiles** change with evidence, without changing any code.
- **Places.** A council can rename a place (the code keeps its number; the new name becomes an alias), confirm one of the 572 provisional short names, or add a place (it gets new blocks; no code moves).
- **Confirmation and corrections** come from residents in the N-Ways app, settled by automatic consensus: two phones agreeing, at least one at the gate. A designated issuer can also confirm, retire or move the entrance of a code through the API (`PATCH /v1/codes/{machine}`).
- **Official addresses.** If the government or a council publishes door numbers or a register, they are shown first, before the Plus Code.

## Hand-over

The repository, the registry and its rules are built to be handed over whole, without forking the engine, to the Ministry of Communications and Digital Economy, GAMPOST or a body they name, under the open licences in LICENSING.md.

## Privacy

Home codes describe places, never people. The registry records buildings, entrances and uses; it holds no names of residents, no occupant data and nothing about the people in a home, and homes are never named. Questions and corrections go to hello@nways.ng and are answered within 30 days.

## Publication

Every issued code is published in `registry/`, with its entrance, its centre, its compound profile, its official address and its building footprints, together with the frozen place table. Each new export replaces the files and their checksums in `MANIFEST.json`.
