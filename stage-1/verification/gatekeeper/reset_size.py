#!/usr/bin/env python3
"""Test reset timeout without logging credentials. Usage: python3 reset_size.py URL [USERS]"""
import json
import sys
import time
import probe as p

count = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
fixture = {'currency': 'EUR', 'minor_units': 2, 'users': [
    {'id': 'u' + str(i), 'email': 'user' + str(i) + '@example.test', 'password': p.PASSWORD,
     'display_name': 'User', 'handle': 'user' + str(i), 'balance': 1} for i in range(count)],
    'payments': [], 'requests': []}
start = time.monotonic()
try:
    status, _ = p.call('POST', '/_test/reset', fixture)
    outcome = str(status)
except Exception as exc:
    outcome = type(exc).__name__
elapsed = time.monotonic() - start
print(json.dumps({'users': count, 'body_bytes': len(json.dumps(fixture).encode()), 'outcome': outcome,
                  'seconds': round(elapsed, 4)}))
raise SystemExit(0 if outcome == '204' and elapsed < 10 else 1)
