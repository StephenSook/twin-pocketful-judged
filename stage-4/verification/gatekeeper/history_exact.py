#!/usr/bin/env python3
"""Temporal arithmetic must be independent of fixture array order at 2**53."""
import json
import probe as p

MAXIMUM = 2**53
fixture = {
    'currency': 'EUR', 'minor_units': 2,
    'users': [{'id': 'u_'+h, 'handle': h, 'email': h+'@example.test',
               'display_name': h, 'password': p.PASSWORD, 'balance': balance}
              for h, balance in [('a', MAXIMUM), ('b', 0)]],
    'payments': [
        {'id': 'p_in', 'from_user_id': 'u_b', 'to_user_id': 'u_a',
         'amount': 1, 'note': '', 'visibility': 'public', 'created_at': '2020-01-03T00:00:00+00:00'},
        {'id': 'p_out', 'from_user_id': 'u_a', 'to_user_id': 'u_b',
         'amount': 1, 'note': '', 'visibility': 'public', 'created_at': '2020-01-02T00:00:00+00:00'}],
    'requests': []}
p.check(p.call('POST', '/_test/reset', fixture)[0] == 204, 'valid exact boundary fixture')
token = p.call('POST', '/auth/login', {'email': 'a@example.test', 'password': p.PASSWORD})[1]['token']
status, body = p.call('GET', '/me?as_of=2020-01-04T00:00:00%2B00:00', token=token)
print(json.dumps({'status': status, 'expected': MAXIMUM, 'observed': body.get('balance')}))
p.check(status == 200 and body['balance'] == MAXIMUM, 'temporal sum exact despite fixture order')
print('PASS historical exact arithmetic')

# Creation order differs from corrected effective order, while every actual
# effective boundary remains in range.
fixture['users'][0]['balance'] = MAXIMUM - 1
fixture['users'][1]['balance'] = 2
fixture['payments'][0]['created_at'] = '2020-01-01T00:00:00+00:00'
p.check(p.call('POST', '/_test/reset', fixture)[0] == 204, 'correctable exact fixture')
tokens = {h: p.call('POST', '/auth/login', {'email': h+'@example.test', 'password': p.PASSWORD})[1]['token'] for h in ['a','b']}
status, _ = p.call('POST', '/payments/p_in/corrections', {
    'expected_revision': 1, 'amount': 2,
    'effective_at': '2020-01-03T00:00:00+00:00', 'reason': 'Moved effective date'}, tokens['b'], 'exact-correction')
p.check(status == 201, 'valid correction accepted')
status, body = p.call('GET', '/me?as_of=2020-01-04T00:00:00%2B00:00', token=tokens['a'])
print(json.dumps({'status': status, 'expected': MAXIMUM, 'observed': body.get('balance')}))
temporal_ok = status == 200 and body['balance'] == MAXIMUM

fixture['users'][0]['balance'] = 100
fixture['users'][1]['balance'] = MAXIMUM
fixture['payments'] = [{'id': 'p', 'from_user_id': 'u_a', 'to_user_id': 'u_b',
    'amount': 1, 'note': '', 'visibility': 'public', 'created_at': '2020-01-01T00:00:00+00:00'}]
p.check(p.call('POST', '/_test/reset', fixture)[0] == 204, 'overflow fixture')
tokens = {h: p.call('POST', '/auth/login', {'email': h+'@example.test', 'password': p.PASSWORD})[1]['token'] for h in ['a','b']}
status, _ = p.call('POST', '/payments/p/corrections', {
    'expected_revision': 1, 'amount': 2, 'effective_at': '2020-01-01T00:00:00+00:00',
    'reason': 'Increase'}, tokens['a'], 'overflow')
balances = [p.call('GET', '/me', token=tokens[h])[1]['balance'] for h in ['a','b']]
print(json.dumps({'overflow_expected_status': 422, 'observed_status': status,
    'expected_balances': [100, MAXIMUM], 'observed_balances': balances}))
p.check(temporal_ok, 'corrected temporal sum exact')
p.check(status == 422 and balances == [100, MAXIMUM], 'overflow rejected atomically')
print(json.dumps({'result':'PASS','assertions':p.COUNT,'cases':3}))
