# Live demo image: the band's stage image, built unchanged from its own Dockerfile, plus the
# demo front door (proxy.py) that closes the test endpoints and reseeds the demo accounts.
#   docker build -t app stage-4
#   docker build -t demo --build-arg APP_IMAGE=app --build-arg APP_ARGV_B64=<base64-json-array> factory/deploy
#
# The front door brings its own Python, so the band may build in any language: a pinned, self-contained
# python-build-standalone runtime (release 20260924, CPython 3.12.14, x86_64 glibc), refused unless its
# SHA-256 matches the value published in that release's SHA256SUMS.
ARG APP_IMAGE

FROM python:3.12-slim AS front-door-runtime
ARG PBS_URL=https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz
ARG PBS_SHA256=269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41
RUN python3 - "$PBS_URL" "$PBS_SHA256" <<'PY'
import hashlib, sys, tarfile, urllib.request
url, expected = sys.argv[1], sys.argv[2]
data = urllib.request.urlopen(url, timeout=120).read()
actual = hashlib.sha256(data).hexdigest()
if actual != expected:
    raise SystemExit(f"front-door runtime checksum mismatch: {actual}")
open("/tmp/python.tar.gz", "wb").write(data)
with tarfile.open("/tmp/python.tar.gz") as archive:
    archive.extractall("/opt", filter="data")
PY
RUN /opt/python/bin/python3 -c "import http.server, json, subprocess, urllib.request"

FROM ${APP_IMAGE}
ARG APP_ARGV_B64
ENV DEMO_APP_ARGV_B64=${APP_ARGV_B64} DEMO_UPSTREAM_PORT=8081 DEMO_RESET_SECONDS=3600 PORT=10000
COPY --from=front-door-runtime /opt/python /opt/demo-python
COPY proxy.py seed.json /demo/
EXPOSE 10000
ENTRYPOINT ["/opt/demo-python/bin/python3", "/demo/proxy.py"]
CMD []
