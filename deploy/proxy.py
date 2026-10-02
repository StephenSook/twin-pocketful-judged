"""Public front door for a live demo of the band's unmodified service.

Runs the band's own start command as a child process on an internal port and serves the public
port in front of it. It forwards every request unchanged except:
  - /_test/* (unauthenticated reset, export and import in the spec) answers 404, so nobody on the
    internet can wipe or read the whole store;
  - each client address is rate limited, and request bodies are capped;
  - every DEMO_RESET_SECONDS the proxy itself reseeds the service from seed.json through the
    service's own reset endpoint, so the demo accounts always work.
Standard library only. If the service exits, the proxy exits, so the host restarts both.
"""
import http.client
import http.server
import base64
import json
import os
import pathlib
import posixpath
import re
import subprocess
import sys
import threading
import time

PUBLIC_PORT = int(os.environ.get("PORT", "10000"))
UP_PORT = int(os.environ.get("DEMO_UPSTREAM_PORT", "8081"))
RESET_SECONDS = int(os.environ.get("DEMO_RESET_SECONDS", "3600"))
RATE = int(os.environ.get("DEMO_RATE_PER_10S", "120"))
MAX_BODY = int(os.environ.get("DEMO_MAX_BODY", str(1 << 20)))
SEED = pathlib.Path(__file__).with_name("seed.json").read_bytes()
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
       "trailer", "transfer-encoding", "upgrade", "host", "content-length"}
state = {"last_reset": None, "last_reset_status": None}
buckets, blk = {}, threading.Lock()


def decode_app_argv(encoded):
    """Decode the built image's exact entrypoint plus command without a shell round trip."""
    if not encoded:
        return ["python", "-m", "app.main"]
    try:
        raw = base64.b64decode(encoded, validate=True)
        argv = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("DEMO_APP_ARGV_B64 is not valid base64 JSON") from exc
    if not isinstance(argv, list) or not argv or not all(
        isinstance(value, str) and value and "\x00" not in value for value in argv
    ):
        raise ValueError("DEMO_APP_ARGV_B64 must encode a nonempty array of nonempty strings")
    return argv


APP_ARGV = decode_app_argv(os.environ.get("DEMO_APP_ARGV_B64"))


def canonical(raw):
    """Return (path, query) exactly as the service will route it, or None to refuse.

    The test endpoints must be blocked on the path the service sees, not on the raw request line:
    percent-encoding (/%5Ftest), repeated slashes (//_test) and dot segments (/x/../_test) all decode
    to the same route upstream. The proxy decodes and normalizes first, checks that, and forwards
    the normalized path so the check and the route can never disagree.
    """
    from urllib.parse import quote, unquote, urlsplit
    if raw.startswith("/"):
        # Never hand a path to urlsplit: it reads "//x/y" as host "x".
        path, _, query = raw.partition("?")
    else:
        parts = urlsplit(raw)  # absolute form, "http://host/path?query"
        path, query = parts.path or "/", parts.query
    if re.search(r"%(2f|5c)|\\", path, re.I):
        return None  # encoded slash or backslash: no legitimate route needs one
    for _ in range(3):  # undo nested encoding such as %255F
        decoded = unquote(path)
        if decoded == path:
            break
        path = decoded
    if "%" in path or any(ord(c) < 32 for c in path):
        return None
    trailing = path.endswith("/")
    # normpath keeps a leading "//" (POSIX allows it), so collapse slashes after normalizing too.
    path = re.sub(r"/+", "/", posixpath.normpath(re.sub(r"/+", "/", "/" + path)))
    if trailing and path != "/":
        path += "/"
    return quote(path, safe="/-._~!$&'()*+,;=:@"), query


def blocked(path):
    return path.lower().rstrip("/") == "/_test" or path.lower().startswith("/_test/")


def log(msg):
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} demo: {msg}", flush=True)


def upstream(method, path, body=b"", headers=None, timeout=15):
    c = http.client.HTTPConnection("127.0.0.1", UP_PORT, timeout=timeout)
    c.request(method, path, body=body, headers=headers or {})
    return c, c.getresponse()


def wait_healthy(deadline=90):
    t0 = time.time()
    while time.time() - t0 < deadline:
        try:
            c, r = upstream("GET", "/health", timeout=3)
            ok = r.status == 200
            c.close()
            if ok:
                return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def reseed():
    try:
        c, r = upstream("POST", "/_test/reset", SEED, {"Content-Type": "application/json"}, timeout=20)
        r.read()
        c.close()
        state.update(last_reset=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), last_reset_status=r.status)
        log(f"reseed -> {r.status}")
    except OSError as e:
        state.update(last_reset_status=f"error {e}")
        log(f"reseed failed: {e}")


def reseed_loop():
    while True:
        time.sleep(RESET_SECONDS)
        reseed()


def allowed(ip):
    now = time.time()
    with blk:
        start, n = buckets.get(ip, (now, 0))
        if now - start > 10:
            start, n = now, 0
        buckets[ip] = (start, n + 1)
        if len(buckets) > 10000:
            buckets.clear()
        return n + 1 <= RATE


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def reply(self, status, obj, extra=None):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def handle_any(self):
        # The request can forge forwarding headers. Rate-limit on the socket peer instead.
        ip = self.client_address[0]
        if not allowed(ip):
            return self.reply(429, {"error": "rate_limited"}, {"Retry-After": "10"})
        if self.path == "/__demo/status":
            return self.reply(200, {"reset_every_seconds": RESET_SECONDS, **state})
        canon = canonical(self.path)
        if canon is None:
            return self.reply(400, {"error": "bad_path"})
        path, query = canon
        if blocked(path):
            return self.reply(404, {"error": "not_found", "detail": "test endpoints are closed on the public demo"})
        target = path + ("?" + query if query else "")
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self.reply(413, {"error": "body_too_large"})
        body = self.rfile.read(length) if length else b""
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        try:
            c, r = upstream(self.command, target, body, headers)
        except OSError:
            return self.reply(502, {"error": "service_unavailable"})
        data = r.read()
        c.close()
        self.send_response(r.status, r.reason)  # adds the proxy's own Date and Server
        for k, v in r.getheaders():
            if k.lower() not in HOP and k.lower() not in ("date", "server"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = handle_any


def main():
    env = dict(os.environ, PORT=str(UP_PORT))
    app = subprocess.Popen(APP_ARGV, env=env)
    log(f"started service {json.dumps(APP_ARGV)} on 127.0.0.1:{UP_PORT} (pid {app.pid})")
    if not wait_healthy():
        log("service never became healthy")
        app.kill()
        sys.exit(1)
    reseed()
    threading.Thread(target=reseed_loop, daemon=True).start()
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PUBLIC_PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"public demo on 0.0.0.0:{PUBLIC_PORT}")
    code = app.wait()
    log(f"service exited with {code}; stopping")
    sys.exit(code or 1)


if __name__ == "__main__":
    main()
