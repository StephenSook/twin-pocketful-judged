#!/usr/bin/env python3
"""API-only security checks. Usage: python3 security.py URL; never logs secrets."""
import json
import secrets
import probe as p

tokens = p.seed(20)
_, request = p.call('POST', '/requests', {'payer_handle': 'a', 'amount': 2, 'note': 'private request'}, tokens['b'], 'request')
request_id = request['request_id']
routes = [('GET', '/me', None), ('GET', '/activity', None), ('GET', '/requests', None),
          ('POST', '/payments', {'to_handle': 'b', 'amount': 1}),
          ('POST', '/requests', {'payer_handle': 'b', 'amount': 1}),
          ('POST', '/splits', {'amount': 1, 'participant_handles': ['a', 'b']}),
          ('POST', '/settlements', {'transfers': [{'from_handle': 'a', 'to_handle': 'b', 'amount': 1}]})]
routes += [('POST', '/requests/' + request_id + '/' + action, {}) for action in ['pay', 'decline', 'cancel']]
for method, path, body in routes:
    for token in [None, secrets.token_urlsafe(32)]:
        status, error = p.call(method, path, body, token, 'unauthenticated')
        p.check(status == 401 and error['error']['code'] == 'unauthenticated', 'protected path requires valid bearer ' + path)
for action in ['pay', 'decline', 'cancel']:
    status, error = p.call('POST', '/requests/' + request_id + '/' + action, {}, tokens['c'], 'foreign-request')
    p.check(status == 403 and error['error']['code'] == 'forbidden', 'unrelated operator cannot use request ID')
    p.check(request_id not in json.dumps(error) and request['note'] not in json.dumps(error), 'refusal omits object details')
    status, error = p.call('POST', '/requests/unknown-object/' + action, {}, tokens['c'], 'unknown-request')
    p.check(status == 404 and error['error']['code'] == 'not_found', 'unknown request ID')
for path in ['/requests', '/requests?direction=incoming', '/requests?direction=outgoing']:
    status, result = p.call('GET', path, token=tokens['c'])
    p.check(status == 200 and result['requests'] == [], 'operator sees no unrelated request listing')
status, error = p.call('POST', '/settlements', {'transfers': [{'from_handle': 'a', 'to_handle': 'b', 'amount': 1}]}, tokens['a'], 'operator-only')
p.check(status == 403 and error['error']['code'] == 'forbidden', 'nonoperator cannot supply foreign transfer handles')
status, receipt = p.call('POST', '/payments', {'to_handle': 'b', 'amount': 1, 'visibility': 'private'}, tokens['a'], 'key-scope')
p.check(status == 201, 'private payment')
status, receipt2 = p.call('POST', '/payments', {'to_handle': 'a', 'amount': 1, 'visibility': 'private'}, tokens['b'], 'key-scope')
p.check(status == 201 and receipt2['payment_id'] != receipt['payment_id'], 'other user key does not recover foreign response')
_, feed = p.call('GET', '/activity', token=tokens['c'])
p.check(feed['payments'] == [], 'operator sees no private payments')
_, exported = p.call('GET', '/_test/export')
serialized = json.dumps(exported)
p.check(p.PASSWORD not in serialized, 'no plaintext password in stored export')
p.check(all(t not in serialized for t in tokens.values()), 'raw bearer tokens not stored')
hashes = [u['password_hash'] for u in exported['state']['users']]
p.check(all(h.startswith('$argon2id$v=19$') for h in hashes), 'Argon2id password storage')
p.check(len(set(hashes)) == len(hashes), 'distinct salts for identical passwords')
for h in hashes:
    params = dict(field.split('=') for field in h.split('$')[3].split(','))
    p.check(int(params['m']) >= 19456 and int(params['t']) >= 2, 'slow password hash parameters')
print(json.dumps({'result': 'PASS', 'assertions': p.COUNT, 'identifier_kinds': ['bearer token', 'request ID', 'recipient/payer handle', 'settlement handles', 'idempotency key'], 'authorization_ruling': 'known request wrong role 403; unknown request 404', 'pages': 'not applicable; API-only'}))
