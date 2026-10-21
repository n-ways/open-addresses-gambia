"""python3 -m server import | serve | export | run

  import  --registry registry --db data/addresses.sqlite [--replace]
          load and verify the published registry (SHA-256 and counts against MANIFEST.json)
  serve   --db data/addresses.sqlite --port 8080
          the JSON API under /v1
  export  --db data/addresses.sqlite --out DIR
          write the registry back in the published format
  run     import the bundled registry if the database does not exist yet, then serve
          (the container's entry point)

Environment: ADDRESSES_DB, REGISTRY_DIR, HOST, PORT, ISSUE_KEYS (comma-separated
bearer keys; none means read-only), ISSUE_PER_DAY (codes per key per 24 hours,
default 500), CORS_ORIGINS (comma-separated origins, or *).
"""
import argparse
import os
import signal
import sys

from . import store as S
from .api import Config, make_server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def env_list(name):
    return [x.strip() for x in os.environ.get(name, '').split(',') if x.strip()]


def config(args):
    return Config(db=args.db, port=int(args.port), host=args.host, issue_keys=env_list('ISSUE_KEYS'),
                  issue_per_day=int(os.environ.get('ISSUE_PER_DAY', '500')), cors=env_list('CORS_ORIGINS'),
                  quiet=getattr(args, 'quiet', False))


def serve(args):
    cfg = config(args)
    httpd = make_server(cfg, S.Store(cfg.db))
    mode = f'issuing with {len(cfg.issue_keys)} key(s)' if cfg.issue_keys else 'read-only'
    sys.stderr.write(f'serving {cfg.db} on http://{cfg.host}:{cfg.port}/v1 ({mode})\n')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main(argv=None):
    db_default = os.environ.get('ADDRESSES_DB', os.path.join('data', 'addresses.sqlite'))
    reg_default = os.environ.get('REGISTRY_DIR', os.path.join(ROOT, 'registry'))
    ap = argparse.ArgumentParser(prog='python3 -m server', description='N-Ways Addressing for The Gambia: registry server')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('import', help='load the published registry into SQLite')
    p.add_argument('--registry', default=reg_default)
    p.add_argument('--db', default=db_default)
    p.add_argument('--replace', action='store_true', help='replace a database that holds codes issued by this deployment')
    for name in ('serve', 'run'):
        p = sub.add_parser(name, help='serve the API' if name == 'serve' else 'import if needed, then serve')
        p.add_argument('--db', default=db_default)
        p.add_argument('--registry', default=reg_default)
        p.add_argument('--host', default=os.environ.get('HOST', '0.0.0.0'))
        p.add_argument('--port', default=os.environ.get('PORT', '8080'))
        p.add_argument('--quiet', action='store_true', help='no access log')
    p = sub.add_parser('export', help='write the registry back in the published format')
    p.add_argument('--db', default=db_default)
    p.add_argument('--out', required=True)
    args = ap.parse_args(argv)
    try:
        if args.cmd == 'import':
            S.import_registry(args.registry, args.db, replace=args.replace)
        elif args.cmd == 'export':
            S.export_registry(args.db, args.out)
        elif args.cmd == 'serve':
            serve(args)
        elif args.cmd == 'run':
            if not os.path.exists(args.db):
                S.import_registry(args.registry, args.db)
            serve(args)
    except (S.ImportError_, FileNotFoundError) as e:
        sys.exit(f'error: {e}')


if __name__ == '__main__':
    main()
