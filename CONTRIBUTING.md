# Contributing

Thank you for helping. This repository holds The Gambia's N-Ways home codes, the engine that defines them, the server that serves them and the paper that explains them. Because the codes are addresses people already use, some things can change freely and some can never change.

## What you can propose

- **Corrections to the data that do not move a code**: a building's use class, a compound's entrance, a place's official name or an alias, a council street address. Open an issue with the code (machine form), what is wrong and your evidence (a photo, a council document, an OpenStreetMap edit).
- **Place names**: a council confirming one of the provisional short names, renaming a place (the old name stays as an alias) or adding a place. These come from the council concerned or with its agreement.
- **The server and the tools**: bug fixes, performance, deployment recipes, translations of the documentation. Open a pull request with a test.
- **The paper**: corrections of fact, better sources, clearer explanations. Cite your source.

## What cannot change

An issued code, its number and its place; the seven zones; the blocks of each name's range (they are only added to); the name key, the check digit and the numbering rules. These are frozen by engine/SPEC.md section 9, because changing any of them would change addresses people already use. A proposal that needs one of them changed is a new major version of the specification and does not apply to codes already issued.

## The issuer rule

New codes are issued only by The Gambia's designated issuer (GOVERNANCE.md). Pull requests never add codes to `registry/` by hand: the registry is replaced as a whole by the issuer's export, with its `MANIFEST.json`. If you run the server, run it read-only unless you are the designated issuer.

## How to send a change

1. Open an issue first for anything larger than a small fix, so the change can be discussed.
2. Keep the change focused, and keep comments and documentation in plain, factual English.
3. Run the checks before you open the pull request:

   ```sh
   (cd engine/reference && python3 gm_engine.py selftest && python3 -m unittest test_gm)
   python3 -m unittest server.tests.test_server
   ```

4. Do not commit databases, `.env` files, keys or build output (`.gitignore` covers them).

By contributing you agree that your contribution is licensed under the licence of the part you change (LICENSING.md): Apache 2.0 for code, ODbL 1.0 for data, CC BY 4.0 for documents.

Contact: hello@nways.ng.
