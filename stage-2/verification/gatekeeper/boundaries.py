#!/usr/bin/env python3
"""Independent literal-boundary regressions. Usage: python3 boundaries.py URL"""
import json
import re
import secrets
import probe as p

fixture = {'currency': 'EUR', 'minor_units': 2, 'users': [
    {'id': 'edge', 'email': 'edge@example.test', 'password': secrets.token_urlsafe(20),
     'display_name': 'Edge', 'handle': 'edge', 'balance': 2 ** 53}],
    'payments': [], 'requests': []}
status, body = p.call('POST', '/_test/reset', fixture)
results = [{'case': 'inclusive 2^53 balance', 'expected_status': 204, 'observed_status': status,
            'passed': status == 204}]
# Isolate signup from previous destination state.
p.seed()
email = '\u0130@example.test'
status, signup = p.call('POST', '/auth/signup', {'email': email, 'password': secrets.token_urlsafe(20), 'display_name': 'Unicode'})
p.check(status == 201, 'Unicode local part signup')
status, me = p.call('GET', '/me', token=signup['token'])
expected = re.sub('[^a-z0-9_]', '_', email.split('@')[0].lower())[:20]
results.append({'case': 'lowercase then replace', 'expected_handle': expected,
                'observed_handle': me['handle'], 'passed': me['handle'] == expected})
print(json.dumps({'checks': results, 'passed': sum(r['passed'] for r in results), 'failed': sum(not r['passed'] for r in results)}))
raise SystemExit(0 if all(r['passed'] for r in results) else 1)
