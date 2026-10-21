# The registry server of N-Ways Addressing for The Gambia.
#   docker compose up            build, import the bundled registry on first start, serve on :8080
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ADDRESSES_DB=/data/addresses.sqlite \
    REGISTRY_DIR=/app/registry \
    PORT=8080

RUN groupadd --system --gid 10001 addresses \
 && useradd --system --uid 10001 --gid addresses --home-dir /app --shell /usr/sbin/nologin addresses \
 && mkdir -p /data && chown addresses:addresses /data

WORKDIR /app
COPY --chown=addresses:addresses engine/reference/gm_engine.py engine/reference/gm_engine.py
COPY --chown=addresses:addresses engine/SPEC.md engine/SPEC.md
COPY --chown=addresses:addresses engine/data/border.geojson engine/data/border.geojson
COPY --chown=addresses:addresses model/zones.json model/zones.geojson model/
COPY --chown=addresses:addresses registry/ registry/
COPY --chown=addresses:addresses server/ server/
COPY --chown=addresses:addresses LICENSE LICENSE-DATA LICENSE-DOCS LICENSING.md NOTICE ./

USER addresses
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD python3 -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/v1/health' % os.environ.get('PORT', '8080'), timeout=4)"

CMD ["python3", "-m", "server", "run", "--quiet"]
