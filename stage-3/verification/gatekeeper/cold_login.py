#!/usr/bin/env python3
"""Reproduce cold unknown-account burst. Usage: python3 cold_login.py IMAGE NETWORK"""
import concurrent.futures as cf
import json
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

image, network = sys.argv[1:3]
name = 'gatekeeper-cold-login'
barrier = threading.Barrier(50)
password = secrets.token_urlsafe(20)


def run(i):
    request = urllib.request.Request(url + '/auth/login', method='POST', headers={'Content-Type': 'application/json'},
        data=json.dumps({'email': 'unknown@example.test', 'password': password}).encode())
    barrier.wait()
    start = time.monotonic()
    try:
        response = urllib.request.urlopen(request, timeout=5)
        response.read()
        status = response.status
    except urllib.error.HTTPError as exc:
        exc.read()
        status = exc.code
    except Exception as exc:
        status = type(exc).__name__
    return {'status': status, 'seconds': round(time.monotonic() - start, 4)}


try:
    subprocess.run(['docker', 'run', '-d', '--name', name, '--network', network, '--cpus', '2', '--memory', '2g', image], check=True, stdout=subprocess.DEVNULL)
    ip = subprocess.check_output(['docker', 'inspect', '--format', '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', name], text=True).strip()
    url = 'http://' + ip + ':8080'
    for _ in range(200):
        try:
            urllib.request.urlopen(url + '/health', timeout=1).close()
            break
        except Exception:
            time.sleep(.05)
    with cf.ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(run, range(50)))
    statuses = {}
    for result in results:
        key = str(result['status'])
        statuses[key] = statuses.get(key, 0) + 1
    passed = all(r['status'] == 401 and r['seconds'] < 5 for r in results)
    print(json.dumps({'result': 'PASS' if passed else 'FAIL', 'requests': 50, 'statuses': statuses,
                      'max_seconds': max(r['seconds'] for r in results)}))
    raise SystemExit(0 if passed else 1)
finally:
    subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
