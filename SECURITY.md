# Security

## Reporting a problem

Write to **hello@nways.ng** with "Security" in the subject. Please include what you found, how to reproduce it and what it affects (the engine, the server, a deployment, the data). Do not open a public issue for a vulnerability, and do not test against deployments you do not run.

We acknowledge a report within three working days, keep you informed while we fix it, and credit you when the fix is published unless you prefer otherwise.

Please also write to us, in the same way, if the data exposes something it should not: the registry is meant to describe places only, never people.

## Running the server safely

- Run a deployment read-only (no `ISSUE_KEYS`) unless it is The Gambia's designated issuer.
- Keep issuing keys out of the repository and out of `docker-compose.yml`: use the environment or an `.env` file, generate them with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`, and give each client its own key so one can be withdrawn without the others.
- Serve the API through a reverse proxy with TLS (server/README.md) and keep the server's own port closed to the outside.
- Back up an issuing deployment and export its registry regularly.
