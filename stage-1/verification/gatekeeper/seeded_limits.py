#!/usr/bin/env python3
"""Large distinct-password fixtures and immediate controls. Usage: python3 seeded_limits.py URL"""
import json
import secrets
import time
import probe as p

results = []
for count in [1000, 5000]:
    passwords = [secrets.token_urlsafe(20) for _ in range(count)]
    fixture = {'currency': 'EUR', 'minor_units': 2, 'users': [
        {'id': 'u' + str(i), 'email': 'user' + str(i) + '@example.test', 'password': passwords[i],
         'display_name': 'User', 'handle': 'user' + str(i), 'balance': 1} for i in range(count)],
        'payments': [], 'requests': []}
    started = time.monotonic()
    status, _ = p.call('POST', '/_test/reset', fixture)
    reset_seconds = time.monotonic() - started
    p.check(status == 204, 'large distinct reset')
    started = time.monotonic()
    status, exported = p.call('GET', '/_test/export')
    export_seconds = time.monotonic() - started
    p.check(status == 200, 'immediate distinct export')
    p.check(len(exported['state']['users']) == count, 'all users exported')
    p.check(sum(u['balance'] for u in exported['state']['users']) == count, 'export balance conservation')
    hashes = [u['password_hash'] for u in exported['state']['users']]
    p.check(all(isinstance(h, str) and h.startswith('$argon2id$') for h in hashes), 'every user hashed before export')
    p.check(len(set(hashes)) == count, 'distinct passwords have distinct hashes')
    params = sorted({h.split('$')[3] for h in hashes})
    timings = []
    def login(i):
        started = time.monotonic()
        status, body = p.call('POST', '/auth/login', {'email': 'user' + str(i) + '@example.test',
            'password': passwords[i] if i != 49 else secrets.token_urlsafe(20)})
        timings.append(time.monotonic() - started)
        p.check(status == (200 if i != 49 else 401), 'immediate large-fixture login')
        return status, body
    logins = p.burst(login)
    signup_results = p.burst(lambda i: p.call('POST', '/auth/signup', {'email': 'signup' + str(i) + '@example.test', 'password': p.PASSWORD, 'display_name': 'New'}))
    p.check(all(s == 201 for s, _ in signup_results), 'signups during seeded rehash')
    started = time.monotonic()
    p.check(p.call('POST', '/_test/import', exported)[0] == 204, 'immediate exported state imports')
    import_seconds = time.monotonic() - started
    p.check(p.call('GET', '/me', token=logins[0][1]['token'])[0] == 401, 'snapshot replacement removes later sessions')
    p.check(p.call('POST', '/auth/login', {'email': 'user0@example.test', 'password': passwords[0]})[0] == 200, 'import preserves seeded login')
    results.append({'users': count, 'reset_seconds': round(reset_seconds, 4), 'immediate_export_seconds': round(export_seconds, 4),
                    'login_200': 49, 'wrong_password_401': 1, 'max_login_seconds': round(max(timings), 4),
                    'signup_201': 50, 'import_seconds': round(import_seconds, 4), 'seed_hash_parameters': params})
    print(json.dumps(results[-1]), flush=True)
print(json.dumps({'result': 'PASS', 'assertions': p.COUNT, 'cases': len(results)}))
