#!/usr/bin/env python3
"""Reset distinct passwords then immediately export. Usage: python3 pending_export.py URL [USERS]"""
import json
import secrets
import sys
import time
import probe as p

count = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
fixture = {'currency': 'EUR', 'minor_units': 2, 'users': [
    {'id': 'u' + str(i), 'email': 'user' + str(i) + '@example.test', 'password': secrets.token_urlsafe(20),
     'display_name': 'User', 'handle': 'user' + str(i), 'balance': 1} for i in range(count)],
    'payments': [], 'requests': []}
results = []
for method, path, body in [('POST', '/_test/reset', fixture), ('GET', '/_test/export', None)]:
    start = time.monotonic()
    try:
        status, _ = p.call(method, path, body)
        outcome = str(status)
    except Exception as exc:
        outcome = type(exc).__name__
    results.append({'path': path, 'outcome': outcome, 'seconds': round(time.monotonic() - start, 4)})
print(json.dumps({'distinct_users': count, 'results': results}))
passed = results[0]['outcome'] == '204' and results[1]['outcome'] == '200' and all(r['seconds'] < 10 for r in results)
raise SystemExit(0 if passed else 1)
