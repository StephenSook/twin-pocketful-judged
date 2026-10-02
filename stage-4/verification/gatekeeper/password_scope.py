#!/usr/bin/env python3
"""Observe seed and signup costs plus post-login upgrade, without logging hashes.

Usage: python3 password_scope.py URL
Reports whether the original minimum covers the initial seeded hash separately.
"""
import json
import sys
import time
import probe as p

fixture = {'currency': 'EUR', 'minor_units': 2, 'users': [
    {'id': 'seed', 'email': 'seed@example.test', 'password': p.PASSWORD,
     'display_name': 'Seed', 'handle': 'seed', 'balance': 1},
    {'id': 'seed2', 'email': 'seed2@example.test', 'password': p.PASSWORD,
     'display_name': 'Seed2', 'handle': 'seed2', 'balance': 1}], 'payments': [], 'requests': []}
p.check(p.call('POST', '/_test/reset', fixture)[0] == 204, 'reset password scope')
_, exported = p.call('GET', '/_test/export')
original = exported['state']['users'][0]['password_hash']
initial_hashes = [u['password_hash'] for u in exported['state']['users']]
p.check(len({h.split('$')[4] for h in initial_hashes}) == len(initial_hashes), 'same seeded password has distinct per-user salts before login')
p.check(p.PASSWORD not in json.dumps(exported), 'initial seeded export contains no plaintext password')
initial = original.split('$')[3]
_, signup = p.call('POST', '/auth/signup', {'email': 'signup@example.test', 'password': p.PASSWORD, 'display_name': 'Signup'})
_, exported = p.call('GET', '/_test/export')
signup_hash = next(u['password_hash'] for u in exported['state']['users'] if u['id'] == signup['user_id'])
signup_params = dict(x.split('=') for x in signup_hash.split('$')[3].split(','))
p.check(int(signup_params['m']) >= 19456 and int(signup_params['t']) >= 2, 'signup retains full cost')
p.check(p.call('POST', '/auth/login', {'email': 'seed@example.test', 'password': 'wrong-value'})[0] == 401, 'wrong password rejected')
_, exported = p.call('GET', '/_test/export')
p.check(next(u['password_hash'] for u in exported['state']['users'] if u['id'] == 'seed') == original, 'wrong password never upgrades hash')
p.check(p.call('POST', '/auth/login', {'email': 'seed@example.test', 'password': p.PASSWORD})[0] == 200, 'correct seeded login')
deadline = time.monotonic() + 5
while True:
    _, exported = p.call('GET', '/_test/export')
    upgraded = next(u['password_hash'] for u in exported['state']['users'] if u['id'] == 'seed')
    if upgraded.split('$')[3] == signup_hash.split('$')[3]:
        break
    p.check(time.monotonic() < deadline, 'seed hash eventually reaches signup cost')
    time.sleep(.05)
p.check(original != upgraded, 'upgraded hash changes')
params = dict(x.split('=') for x in initial.split(','))
minimum = int(params['m']) >= 19456 and int(params['t']) >= 2
fixture_exemption = '--fixture-exemption' in sys.argv[2:]
p.check(int(params['m']) >= 1024 and int(params['t']) >= 1, 'seed retains declared reduced Argon2id cost')
print(json.dumps({'initial_seed_parameters': initial, 'signup_parameters': signup_hash.split('$')[3],
                  'after_login_parameters': upgraded.split('$')[3], 'initial_seed_meets_original_minimum': minimum,
                  'fixture_exemption': fixture_exemption, 'unique_seed_salts_before_login': True,
                  'behavior_checks': 'PASS', 'assertions': p.COUNT}))
raise SystemExit(0 if minimum or fixture_exemption else 1)
