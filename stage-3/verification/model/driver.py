#!/usr/bin/env python3
"""Run: python3 stage-2/verification/model/driver.py --base-url http://127.0.0.1:8080

Destructive: resets the target. Never run against valuable state. No dependencies.
Failure artifacts contain only synthetic operations, never exports or bearer tokens.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from model import initial, transition, expire, held


FIXTURE = {'currency': 'EUR', 'minor_units': 2, 'settlement_operator_ids': ['u_ada'],
    'users': [{'id': 'u_' + h, 'email': h + '@example.test', 'password': 'synthetic-password',
               'display_name': h.title(), 'handle': h, 'balance': b}
              for h, b in [('ada', 10000), ('bob', 2500), ('cy', 0), ('dee', 30)]],
    'payments': [{'id': 'p_seed', 'from_user_id': 'u_ada', 'to_user_id': 'u_bob',
                  'amount': 500, 'note': 'seed', 'visibility': 'private'}],
    'requests': [{'id': 'rq_seed', 'requester_id': 'u_bob', 'payer_id': 'u_cy',
                  'amount': 1200, 'note': 'seed request', 'status': 'pending'}]}


class Mismatch(AssertionError):
    def __init__(self, label, detail=''):
        self.label = label
        super().__init__(label + (': ' + detail if detail else ''))


def require(test, label, detail=''):
    if not test:
        raise Mismatch(label, detail)


def bind_path(path, bindings):
    # Bind complete URL segments: symbolic request:7 must not rewrite request:71.
    return '/'.join(urllib.parse.quote(bindings[part], safe='') if part in bindings else part
                    for part in path.split('/'))


def http(base, method, path, body=None, token=None, key=None, raw=None, auth=None):
    headers = {'Content-Type': 'application/json; charset=utf-8'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if auth is not None:
        headers['Authorization'] = auth
    if key is not None:
        headers['Idempotency-Key'] = key
    data = raw.encode() if raw is not None else json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(base.rstrip('/') + path, data=data, headers=headers, method=method)
    deadline = 10 if path.startswith('/_test/') else 5
    started = time.monotonic()
    try:
        response = urllib.request.urlopen(req, timeout=deadline)
    except urllib.error.HTTPError as e:
        response = e
    except (OSError, TimeoutError) as e:
        raise Mismatch('R1-012 transport', type(e).__name__) from None
    with response:
        status, raw_body, media = response.status, response.read(), response.headers.get('Content-Type', '')
    require(time.monotonic() - started <= deadline, 'R1-012 timeout')
    require(status < 500, 'R1-057 no-5xx', 'HTTP ' + str(status))
    if status == 204:
        require(not raw_body, 'R1-016 204 empty body')
        return status, None
    require('application/json' in media.lower() and 'charset=utf-8' in media.lower().replace(' ', ''), 'R1-018 JSON media type', media)
    try:
        parsed = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        raise Mismatch('R1-018 parseable response') from None
    if status >= 400:
        require(isinstance(parsed, dict) and isinstance(parsed.get('error'), dict), 'R1-046 error envelope')
        require(isinstance(parsed['error'].get('message'), str) and bool(parsed['error']['message']), 'R1-046 error message')
    return status, parsed


class Runner:
    def __init__(self, base, fixture=FIXTURE):
        self.base, self.fixture = base, deepcopy(fixture)
        self.state, self.bindings, self.tokens, self.replays = initial(fixture, time.time()), {}, {}, {}
        status, _ = http(base, 'POST', '/_test/reset', fixture)
        require(status == 204, 'R1-016 reset status', str(status))
        for u in fixture['users']:
            status, r = http(base, 'POST', '/auth/login', {'email': u['email'], 'password': u['password']})
            require(status == 200, 'R1-042 seeded login', str(status))
            require(r.get('user_id') == u['id'] and r.get('display_name') == u['display_name'], 'R1-059 login identity')
            require(isinstance(r.get('token'), str) and r['token'], 'R1-059 login token')
            self.tokens[u['handle']] = r['token']

    def match(self, expected, actual, label='response'):
        if isinstance(expected, dict):
            require(isinstance(actual, dict), label + ' object')
            for k, v in expected.items():
                require(k in actual, label + '.' + k + ' required')
                self.match(v, actual[k], label + '.' + k)
        elif isinstance(expected, list):
            require(isinstance(actual, list) and len(actual) == len(expected), label + ' count')
            for i, (e, a) in enumerate(zip(expected, actual)):
                self.match(e, a, label + '[' + str(i) + ']')
        elif isinstance(expected, str) and expected.startswith(('@id:', '@time:', '@expiry:')):
            require(isinstance(actual, str), label + ' symbolic string')
            if expected.startswith('@id:'):
                require(0 < len(actual) <= 64, 'R1-022 opaque ID length')
            else:
                require(bool(re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)', actual)), 'R1-019 timestamp format')
                try:
                    datetime.fromisoformat(actual.replace('Z', '+00:00'))
                except ValueError:
                    raise Mismatch('R1-019 timestamp validity') from None
            if expected in self.bindings:
                require(self.bindings[expected] == actual, label + ' stable symbolic value')
            else:
                if expected.startswith('@id:'):
                    require(actual not in [v for k, v in self.bindings.items() if k.startswith('@id:')], 'R1-022 distinct created IDs')
                self.bindings[expected] = actual
            if expected.startswith('@expiry:'):
                created = self.bindings['@time:' + expected.split(':')[1]]
                delta = datetime.fromisoformat(actual).timestamp() - datetime.fromisoformat(created).timestamp()
                require(delta == self.state['ttl'], 'R2-099 exact authorization TTL')
        else:
            require(type(expected) == type(actual) or type(expected) in (int, float) and type(actual) in (int, float), label + ' JSON type')
            require(expected == actual, label + ' value', 'expected ' + repr(expected) + ', observed ' + repr(actual))

    def run(self, op, observe=True):
        state, expected = transition(self.state, dict(op, now=time.time()))
        path = bind_path(op['path'], self.bindings)
        if op.get('query'):
            path += '?' + urllib.parse.urlencode(op['query'])
        status, actual = http(self.base, op.get('method', 'POST'), path,
                             op.get('body', {}) if op.get('method', 'POST') != 'GET' else None,
                             self.tokens.get(op.get('user')), op.get('key'),
                             raw='{' if op.get('malformed') else op.get('raw'))
        require(status == expected['status'], 'operation status ' + op['path'],
                'expected ' + str(expected['status']) + ', observed ' + str(status) +
                (' ' + str(actual.get('error', {}).get('code')) if isinstance(actual, dict) else ''))
        if op.get('method') == 'GET' and status == 200 and op['path'] in ('/activity', '/requests', '/authorizations'):
            field = 'payments' if op['path'] == '/activity' else op['path'][1:]
            # Full collections are compared below; list boundary tests avoid unspecified tie order.
            require(len(actual[field]) == len(expected['body'][field]), 'R1-056 page length')
            require(actual['has_more'] == expected['body']['has_more'], 'R1-101 has_more')
        else:
            self.match(expected['body'], actual)
        if status in (200, 201) and 'key' in op:
            ck = (op.get('user'), op.get('method', 'POST'), op['path'], op['key'])
            if status == 201:
                self.replays[ck] = deepcopy(actual)
            else:
                require(self.replays[ck] == actual, 'R1-071 exact replay JSON')
        self.state = state
        for a in state['authorizations']:
            stamp = self.bindings.get(a['expires_at'], a['expires_at'])
            if not stamp.startswith('@'):
                state['deadlines'][a['authorization_id']] = datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()
        if observe:
            self.observe()
        return actual

    def collection(self, user, path):
        field = 'payments' if path == '/activity' else path[1:]
        items = []
        for offset in range(0, 10000, 200):
            status, page = http(self.base, 'GET', path + '?limit=200&offset=' + str(offset), token=self.tokens[user])
            require(status == 200, 'observable list status')
            require(isinstance(page.get(field), list) and type(page.get('has_more')) is bool, 'list envelope')
            require(len(page[field]) <= 200, 'R1-056 maximum page size')
            items += page[field]
            if not page['has_more']:
                break
            require(len(page[field]) == 200, 'R1-101 full page before more')
        else:
            raise Mismatch('R1-101 pagination terminates')
        times = [datetime.fromisoformat(p['created_at'].replace('Z', '+00:00')).timestamp() for p in items]
        # Activity allows all ties within a second. Request tie policy unspecified; weaker same-second check is conservative.
        require([math.floor(t) for t in times] == sorted([math.floor(t) for t in times], reverse=True), 'R1-097/110 newest first')
        return items

    def observe(self):
        expire(self.state, time.time())
        total = 0
        for user in self.state['users']:
            _, expected = transition(self.state, {'method': 'GET', 'path': '/me', 'user': user})
            status, actual = http(self.base, 'GET', '/me', token=self.tokens[user])
            require(status == 200, 'R1-078 me status')
            self.match(expected['body'], actual, 'R1-078 /me')
            total += actual['balance']
            require(actual['balance'] >= 0, 'R1-002 nonnegative')
            for path, field, id_field in [('/activity', 'payments', 'payment_id'), ('/requests', 'requests', 'request_id'), ('/authorizations', 'authorizations', 'authorization_id')]:
                _, response = transition(self.state, {'method': 'GET', 'path': path, 'user': user, 'query': {'limit': '200'}})
                # Bypass model pagination for collections >200.
                if field == 'payments':
                    rows = [p for p in self.state[field] if p['visibility'] == 'public' or user in (p['from_handle'], p['to_handle'])]
                elif field == 'authorizations':
                    rows = [a for a in self.state[field] if user in (a['from_handle'], a['to_handle'])]
                else:
                    rows = [r for r in self.state[field] if user in (r['requester_handle'], r['payer_handle'])]
                actual_rows = self.collection(user, path)
                indexed = {r[id_field]: r for r in actual_rows}
                require(len(indexed) == len(actual_rows) == len(rows), 'R1-037/038 visible collection count')
                for row in rows:
                    rid = self.bindings.get(row[id_field], row[id_field])
                    require(rid in indexed, 'R1-037/038 visible collection membership')
                    expected_row = row
                    if field == 'authorizations':
                        seed = next((a for a in self.fixture.get('authorizations', []) if a['id'] == rid), None)
                        if seed and seed['status'] != 'open' and 'captured_amount' not in seed:
                            # Closed seeded history is unspecified when omitted. Do not invent it.
                            expected_row = {k:v for k,v in row.items() if k not in ('captured_amount','payment_id','payment_ids')}
                    self.match(expected_row, indexed[rid], field + ' record')
        require(total == self.state['total'], 'R1-001 conservation')


def op(user, path, body=None, key=None, **extras):
    result = {'user': user, 'path': path, 'body': body or {}}
    if key is not None:
        result['key'] = key
    return dict(result, **extras)


def deterministic():
    xs = [op('ada', '/payments', {'to_handle': 'bob', 'amount': 10, 'note': '  café ☕ 😀 <>&\n', 'extra': 9}, 'p'),
          op('ada', '/payments', {'extra': 9, 'note': '  café ☕ 😀 <>&\n', 'amount': 10.0, 'to_handle': 'bob'}, 'p'),
          op('ada', '/payments', {'to_handle': 'bob', 'amount': None}, 'p'),
          op('ada', '/payments', {'to_handle': 'bob', 'amount': 10, 'visibility': 'private'}, 'private'),
          op('cy', '/requests/rq_seed/pay', {}, 'short'),
          op('ada', '/payments', {'to_handle': 'cy', 'amount': 1300}, 'fund'),
          op('cy', '/requests/rq_seed/pay', {'visibility': 'private'}, 'short'),
          op('cy', '/requests/rq_seed/pay', {'visibility': 'private'}, 'short'),
          op('cy', '/requests/rq_seed/pay', {}, 'short'),
          op('cy', '/requests/rq_seed/pay', {}, 'new'),
          op('ada', '/requests/rq_seed/decline'), op('bob', '/requests/rq_seed/cancel'),
          op('ada', '/splits', {'amount': 1, 'participant_handles': ['ada', 'bob', 'cy']}, 'zero'),
          op('ada', '/splits', {'amount': 10, 'participant_handles': ['bob', 'cy', 'dee']}, 'omitted'),
          op('cy', '/splits', {'amount': 1000000000, 'participant_handles': ['cy']}, 'solo'),
          op('ada', '/settlements', {'transfers': [
              {'from_handle': 'cy', 'to_handle': 'bob', 'amount': 1000, 'visibility': 'private'},
              {'from_handle': 'bob', 'to_handle': 'cy', 'amount': 1000}]}, 'net'),
          op('ada', '/settlements', {'transfers': [
              {'from_handle': 'cy', 'to_handle': 'bob', 'amount': 1000000},
              {'from_handle': 'bob', 'to_handle': 'missing', 'amount': 1}]}, 'failed-batch'),
          op('ada', '/settlements', {'transfers': [
              {'from_handle': 'ada', 'to_handle': 'dee', 'amount': 1}]}, 'failed-batch')]
    for endpoint, body in [('/payments', {'to_handle': 'bob', 'amount': 1}),
                           ('/requests', {'payer_handle': 'bob', 'amount': 1}),
                           ('/splits', {'participant_handles': ['bob'], 'amount': 1}),
                           ('/settlements', {'transfers': [{'from_handle': 'ada', 'to_handle': 'bob', 'amount': 1}]}),
                           ('/requests/rq_seed/pay', {})]:
        xs += [op('ada', endpoint, body), op('ada', endpoint, body, ''), op('ada', endpoint, body, 'x' * 256)]
    for endpoint, body in [('/payments', {'to_handle': 'bob', 'amount': 1}),
                           ('/requests', {'payer_handle': 'bob', 'amount': 1}),
                           ('/splits', {'participant_handles': ['bob'], 'amount': 1})]:
        for field, bads in [('amount', [0, -1, 1000000001, 1.5, '1', True, None]),
                            ('note', [None, False, 1, 'a' * 201]),
                            ('visibility', [None, True, 'hidden']) if endpoint == '/payments' else ('note', [[]])]:
            for bad in bads:
                xs.append(op('ada', endpoint, dict(body, **{field: bad}), 'invalid-' + str(len(xs))))
    xs += [op('ada', '/payments', {'to_handle': 'bob', 'amount': 1, 'note': '😀' * 200}, 'unicode'),
           op('ada', '/payments', {'to_handle': 'ada', 'amount': 1}, 'self'),
           op('ada', '/requests', {'payer_handle': 'ada', 'amount': 1}, 'self'),
           op('ada', '/splits', {'participant_handles': ['bob', 'bob'], 'amount': 1}, 'dup'),
           op('ada', '/splits', {'participant_handles': [], 'amount': 1}, 'empty'),
           op('ada', '/splits', {'participant_handles': ['bob', 'missing'], 'amount': 1}, 'unknown'),
           op('ada', '/requests', {'payer_handle': 'cy', 'amount': 1000000000}, 'huge'),
           op('bob', '/settlements', {'transfers': [{'from_handle': 'ada', 'to_handle': 'bob', 'amount': 1}]}, 'forbidden')]
    for bad in [None, [], {}, [None], [], [{'from_handle': 'ada', 'to_handle': 'bob', 'amount': 1}] * 33]:
        xs.append(op('ada', '/settlements', {'transfers': bad}, 'shape-' + str(len(xs))))
    for endpoint in ['/requests', '/activity']:
        for name, vals in [('limit', ['0', '201', '4.0', '1e2', '+4', '-1', '']), ('offset', ['-1', '4.0', '+4', '1e2'])]:
            for v in vals:
                xs.append(op('ada', endpoint, method='GET', query={name: v}))
        for query in [{'limit': '1'}, {'limit': '200', 'offset': '999'}, {'extra': 'ignored'}, {'limit': '50', 'offset': '0'}]:
            xs.append(op('ada', endpoint, method='GET', query=query))
    for q in [{'status': 'bad'}, {'direction': 'bad'}, {'status': 'paid'}, {'direction': 'incoming'}, {'direction': 'outgoing'}]:
        xs.append(op('ada', '/requests', method='GET', query=q))
    return xs


def random_ops(state, seed, count):
    rng, xs, s = random.Random(seed), [], deepcopy(state)
    handles = list(s['users'])
    for i in range(count):
        user = rng.choice(handles)
        kind = rng.randrange(6)
        if kind == 0:
            candidate = op(user, '/payments', {'to_handle': rng.choice(handles + ['missing']),
                'amount': rng.choice([0, 1, 2, 30, 100, 1000000000, 1000000001, True, '1']),
                'visibility': rng.choice(['public', 'private'])}, 'fuzz-' + str(i))
        elif kind == 1:
            candidate = op(user, '/requests', {'payer_handle': rng.choice(handles),
                'amount': rng.choice([1, 2, 999, 1000000000])}, 'fuzz-' + str(i))
        elif kind == 2 and s['requests']:
            req = rng.choice(s['requests'])
            verb = rng.choice(['pay', 'decline', 'cancel'])
            user = rng.choice([req['payer_handle'], req['requester_handle'], user])
            candidate = op(user, '/requests/' + req['request_id'] + '/' + verb,
                {'visibility': rng.choice(['public', 'private'])} if verb == 'pay' else {},
                'fuzz-' + str(i) if verb == 'pay' else None)
        elif kind == 3:
            candidate = op(user, '/splits', {'amount': rng.choice([1, 2, 5, 10, 999, 1000]),
                'participant_handles': rng.sample(handles, rng.randint(1, 4))}, 'fuzz-' + str(i))
        elif kind == 4:
            entries = []
            for _ in range(rng.randint(1, 4)):
                a, b = rng.sample(handles, 2)
                entries.append({'from_handle': a, 'to_handle': b, 'amount': rng.choice([1, 30, 1000]), 'visibility': rng.choice(['public', 'private'])})
            candidate = op('ada', '/settlements', {'transfers': entries}, 'fuzz-' + str(i))
        elif xs:
            candidate = deepcopy(rng.choice(xs))
            if rng.random() < .5:
                candidate['body']['unknown_retry_field'] = i
        else:
            candidate = op('ada', '/payments', {'to_handle': 'bob', 'amount': 1}, 'fuzz-' + str(i))
        s, _ = transition(s, candidate)
        xs.append(candidate)
    return xs


def lifecycle_ops(state):
    # Resolve model-generated IDs by state, without assuming their allocation sequence.
    xs = []
    for req in state['requests']:
        if req['status'] == 'pending' and req['amount'] == 0:
            xs.append(op(req['payer_handle'], '/requests/' + req['request_id'] + '/pay', {}, 'zero-pay'))
    for action, field in [('decline', 'payer_handle'), ('cancel', 'requester_handle')]:
        req = next((r for r in reversed(state['requests']) if r['status'] == 'pending' and r['amount'] > 0), None)
        if req:
            xs += [op(req[field], '/requests/' + req['request_id'] + '/' + action)] * 2
            state, _ = transition(state, xs[-1])
    return xs


def edge_ops(state):
    """Build dependent scenarios against the pure state, then execute them live unchanged."""
    xs, s = [], deepcopy(state)
    def add(operation):
        nonlocal s
        xs.append(operation)
        s, response = transition(s, operation)
        return response
    # Every successful write path is replayed, including originals whose resources changed.
    for (user, method, path, key), (body, _) in list(s['keys'].items()):
        add(op(user, path, json.loads(body), key, method=method))
    for payer in ['bob', 'dee']:
        response = add(op('ada', '/requests', {'payer_handle': payer, 'amount': 1}, 'path-' + payer))
        rid = response['body']['request_id']
        add(op(payer, '/requests/' + rid + '/pay', {}, 'shared-pay-path'))
    # Two same-payer requests exercise identical user+key+body across different concrete paths.
    for i in range(2):
        response = add(op('ada', '/requests', {'payer_handle': 'bob', 'amount': 1}, 'cross-path-' + str(i)))
        add(op('bob', '/requests/' + response['body']['request_id'] + '/pay', {}, 'same-path-key'))
    response = add(op('ada', '/requests', {'payer_handle': 'bob', 'amount': 1}, 'cancel-replay'))
    rid = response['body']['request_id']
    add(op('ada', '/requests/' + rid + '/cancel'))
    add(op('ada', '/requests', {'payer_handle': 'bob', 'amount': 1}, 'cancel-replay'))
    for user, target in [('ada', 'bob'), ('bob', 'ada')]:
        add(op(user, '/payments', {'to_handle': target, 'amount': 1}, 'same-user-key'))
    add(op('ada', '/payments', {'to_handle': 'bob', 'amount': 1}, 'x' * 255))
    for raw in ['{"to_handle":"bob","amount":1000.0}', '{ "amount": 1e3, "to_handle": "bob" }']:
        add(op('ada', '/payments', {'to_handle': 'bob', 'amount': 1000}, 'numeric-json', raw=raw))
    for body in [{'to_handle': 1, 'amount': 1}, {'to_handle': 'bob'}, {'amount': 1}]:
        add(op('ada', '/payments', body, 'missing-type-' + str(len(xs))))
    add(op('ada', '/payments', {'to_handle': 'bob', 'amount': 1, 'note': 'a' * 200}, 'note-200'))
    add(op('ada', '/payments', {'to_handle': 'bob', 'amount': 1, 'note': 'a' * 200, 'new_unknown': 1}, 'note-200'))
    add(op('ada', '/settlements', {'transfers': [{'from_handle': 'ada', 'to_handle': 'bob', 'amount': 1}] * 32}, 'batch32'))
    add(op('ada', '/settlements', {'transfers': [{'from_handle': 'missing', 'to_handle': 'bob', 'amount': 1},
            {'from_handle': 'ada', 'to_handle': 'ada', 'amount': 1}]}, 'entry-order'))
    add(op('ada', '/settlements', {'transfers': [{'from_handle': 'ada', 'to_handle': 'ada', 'amount': 1},
            {'from_handle': 'missing', 'to_handle': 'bob', 'amount': 1}]}, 'entry-order'))
    return xs


def run_sequence(base, operations):
    runner = Runner(base)
    runner.observe()
    for operation in operations:
        runner.run(operation)
    return runner


def authorization_ops(state):
    """Deterministic witnesses with symbolic IDs obtained only from the pure model."""
    state, xs = deepcopy(state), []
    def add(operation):
        nonlocal state
        xs.append(operation)
        state, response = transition(state, operation)
        return response['body']
    body = {'to_handle': 'bob', 'amount': 2000, 'note': '  held ☕ ', 'visibility': 'private'}
    a = add(op('ada', '/authorizations', body, 'hold'))
    aid = a['authorization_id']
    capture, void = '/authorizations/' + aid + '/capture', '/authorizations/' + aid + '/void'
    for key in [None, '', 'x'*256]:
        add(op('bob', capture, {}, key))
    add(op('ada', '/authorizations', body, 'hold'))
    add(op('ada', '/authorizations', {'amount': None}, 'hold'))
    for user in ['ada', 'cy']:
        add(op(user, capture, {}, 'forbidden'))
    for user in ['bob', 'cy']:
        add(op(user, void))
    for n in [0, -1, 0.5, None, True, '100', 2001]:
        add(op('bob', capture, {'amount': n}, 'invalid'))
    add(op('bob', capture, {'amount': 1, 'final': 'false'}, 'invalid'))
    add(op('ada', '/payments', {'to_handle': 'cy', 'amount': 8001}, 'available'))
    add(op('ada', '/authorizations', {'to_handle': 'cy', 'amount': 8001}, 'available'))
    req = add(op('cy', '/requests', {'payer_handle': 'ada', 'amount': 8001}, 'held-request'))
    add(op('ada', '/requests/' + req['request_id'] + '/pay', {}, 'available'))
    add(op('ada', '/settlements', {'transfers': [{'from_handle': 'ada', 'to_handle': 'cy', 'amount': 8001}]}, 'available'))
    partial_body = {'amount': 700, 'final': False, 'note': 'ignored', 'visibility': 'public'}
    add(op('bob', capture, partial_body, 'partial'))
    add(op('bob', capture, partial_body, 'partial'))
    add(op('bob', capture, {'amount': 1301}, 'invalid'))
    add(op('bob', capture, {'amount': 300}, 'final'))
    add(op('bob', capture, {}, 'closed'))
    add(op('bob', capture, {'amount': 300}, 'final'))
    add(op('bob', capture, {}, 'final'))
    add(op('ada', void))
    for ending in ['full', 'void', 'open']:
        a = add(op('ada', '/authorizations', {'to_handle': 'bob', 'amount': 1000}, ending))
        capture = '/authorizations/' + a['authorization_id'] + '/capture'
        void = '/authorizations/' + a['authorization_id'] + '/void'
        add(op('bob', capture, {'amount': 200, 'final': False}, 'partial'))
        if ending == 'full':
            add(op('bob', capture, {'final': False}, 'rest'))
            add(op('bob', capture, {}, 'closed'))
        elif ending == 'void':
            add(op('ada', void))
            add(op('ada', void))
            add(op('bob', capture, {}, 'closed'))
            add(op('bob', capture, {'amount': 200, 'final': False}, 'partial'))
    for user in ['ada', 'bob', 'cy']:
        for direction in [None, 'incoming', 'outgoing', 'bad']:
            for status in [None, 'open', 'captured', 'voided', 'expired', 'bad']:
                q = {k: v for k, v in [('direction', direction), ('status', status)] if v is not None}
                add(op(user, '/authorizations', method='GET', query=q))
    for q in [{'limit':'0'}, {'limit':'201'}, {'limit':'1e2'}, {'offset':'-1'}, {'offset':'4.0'}, {'limit':'1', 'offset':'1'}]:
        add(op('ada', '/authorizations', method='GET', query=q))
    for key in [None, '', 'x'*256]:
        add(op('ada', '/authorizations', body, key))
    for body in [{'to_handle':'ada','amount':1}, {'to_handle':'missing','amount':1},
                 {'to_handle':'bob','amount':None}, {'to_handle':'bob','amount':1000000001},
                 {'to_handle':'bob','amount':1,'note':None}, {'to_handle':'bob','amount':1,'note':'😀'*201},
                 {'to_handle':'bob','amount':1,'visibility':None}]:
        add(op('ada', '/authorizations', body, 'invalid-create'))
    add(op('bob', '/authorizations/missing/capture', {}, 'missing'))
    add(op('ada', '/authorizations/missing/void'))
    available = state['users']['ada']['balance'] - held(state, 'ada')
    a = add(op('ada', '/authorizations', {'to_handle':'bob','amount':available}, 'all-available'))
    path = '/authorizations/' + a['authorization_id']
    add(op('bob', path + '/capture', {'amount':1,'final':False}, 'reserved'))
    add(op('ada', path + '/void'))
    return xs


def authorization_random(state, seed, steps):
    state, xs, rng = deepcopy(state), [], random.Random(seed)
    for i in range(steps):
        user = rng.choice(list(state['users']))
        choice = rng.randrange(5)
        if choice == 0 or not state['authorizations']:
            target = rng.choice(list(state['users']))
            operation = op(user, '/authorizations', {'to_handle': target, 'amount': rng.choice([1, 30, 100, 1000, 1000000000]),
                                                    'visibility': rng.choice(['public', 'private'])}, 'random-hold-' + str(i))
        elif choice in (1,2):
            a = rng.choice(state['authorizations'])
            user = a['to_handle'] if rng.randrange(4) else user
            body = {} if rng.randrange(4) == 0 else {'amount': rng.choice([1, a['remaining_amount'], a['remaining_amount']+1]), 'final': bool(rng.randrange(2))}
            if a['status'] != 'open' or user != a['to_handle']:
                # Avoid asserting unspecified precedence between invalid input and role/status.
                body = {}
            operation = op(user, '/authorizations/' + a['authorization_id'] + '/capture', body, 'random-capture-' + str(i))
        elif choice == 3:
            a = rng.choice(state['authorizations'])
            operation = op(a['from_handle'] if rng.randrange(4) else user, '/authorizations/' + a['authorization_id'] + '/void')
        else:
            operation = op(user, '/payments', {'to_handle': rng.choice(list(state['users'])), 'amount': rng.choice([1, 100, 9000])}, 'random-spend-' + str(i))
        xs.append(operation)
        state, response = transition(state, operation)
        if 'key' in operation and response['status'] == 201:
            xs.append(deepcopy(operation))
            state, _ = transition(state, operation)
    return xs


def shrink(base, sequence, label):
    # Classic deletion delta debugging; preserve failure kind, not just any assertion.
    result, granularity = list(sequence), 2
    attempts = 0
    while len(result) >= 2 and attempts < 80:
        size = math.ceil(len(result) / granularity)
        reduced = False
        for start in range(0, len(result), size):
            candidate = result[:start] + result[start + size:]
            attempts += 1
            try:
                run_sequence(base, candidate)
            except Mismatch as e:
                if e.label == label:
                    result, reduced = candidate, True
                    granularity = max(2, granularity - 1)
                    break
            if attempts >= 80:
                break
        if not reduced:
            if granularity >= len(result):
                break
            granularity = min(len(result), granularity * 2)
    return result, attempts


def persistence(runner, second_url=None):
    runner.run(op('ada', '/payments', {'to_handle': 'missing', 'amount': 1}, 'failed-persist'))
    status, snapshot = http(runner.base, 'GET', '/_test/export')
    require(status == 200 and snapshot.get('track') == 'pocketful' and snapshot.get('format_version') == 1 and isinstance(snapshot.get('state'), dict), 'R1-117 export envelope')
    # Never write/print this opaque value: it may contain credentials and tokens.
    target = second_url or runner.base
    destination = Runner(target, dict(FIXTURE, currency='JPY', minor_units=0))
    old_token = destination.tokens['ada']
    destination_account = {'email': 'destination_only@example.test', 'password': 'synthetic-password', 'display_name': 'Temporary'}
    require(http(target, 'POST', '/auth/signup', destination_account)[0] == 201, 'R1-128 destination setup')
    for _ in range(2):
        status, _ = http(target, 'POST', '/_test/import', snapshot)
        require(status == 204, 'R1-118 import status')
    runner.base = target
    runner.observe()
    status, _ = http(target, 'GET', '/me', token=old_token)
    require(status == 401, 'R1-128 removed destination token')
    require(http(target, 'POST', '/auth/login', destination_account)[0] == 401, 'R1-128 removed destination credentials')
    for u in runner.fixture['users']:
        status, body = http(target, 'POST', '/auth/login', {'email': u['email'], 'password': u['password']})
        require(status == 200 and body['user_id'] == u['id'], 'R1-124 imported password login')
    for (user, method, path, key), response in list(runner.replays.items()):
        parsed, _ = runner.state['keys'][(user, method, path, key)]
        runner.run(op(user, path, json.loads(parsed), key, method=method), observe=False)
    runner.observe()
    runner.run(op('ada', '/payments', {'to_handle': 'bob', 'amount': 1}, 'failed-persist'))
    for bad in [{}, dict(snapshot, track='wrong'), dict(snapshot, format_version=2), dict(snapshot, state=None)]:
        status, body = http(target, 'POST', '/_test/import', bad)
        require(status == 422 and body['error']['code'] == 'validation_failed', 'R1-121 invalid import')
        runner.observe()
    status, body = http(target, 'POST', '/_test/import', raw='{')
    require(status == 400 and body['error']['code'] == 'malformed_request', 'R1-121 malformed import')
    runner.observe()


def concurrency(base):
    runner = Runner(base)
    body = {'to_handle': 'bob', 'amount': 100, 'visibility': 'private'}
    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(lambda _: http(base, 'POST', '/payments', body, runner.tokens['ada'], 'race'), range(50)))
    require(sorted(status for status, _ in results) == [200] * 49 + [201], 'R1-075 exactly one creation')
    require(all(body == results[0][1] for _, body in results), 'R1-075 identical concurrent responses')
    runner.state, expected = transition(runner.state, op('ada', '/payments', body, 'race'))
    runner.match(expected['body'], results[0][1])
    runner.observe()


def auth_and_controls(base):
    runner = Runner(base)
    require(http(base, 'GET', '/health') == (200, {'status': 'ok'}), 'R1-015 health')
    for path in ['/me', '/requests', '/activity']:
        for auth in [None, 'garbage', 'Bearer unknown']:
            status, body = http(base, 'GET', path, auth=auth)
            require(status == 401 and body['error']['code'] == 'unauthenticated', 'R1-048 auth')
    status, body = http(base, 'POST', '/payments', raw='{', token=runner.tokens['ada'], key='malformed')
    require(status == 400 and body['error']['code'] == 'malformed_request', 'R1-047 malformed JSON')
    for raw in ['[]', 'null']:
        status, body = http(base, 'POST', '/payments', raw=raw, token=runner.tokens['ada'], key='malformed')
        require(status == 400 and body['error']['code'] == 'malformed_request', 'R1-047 object body')
    negative = deepcopy(FIXTURE)
    negative['users'][0]['balance'] = -1
    status, body = http(base, 'POST', '/_test/reset', negative)
    require(status == 422 and body['error']['code'] == 'validation_failed', 'R1-044 negative reset')
    runner.observe()
    for email, password in [('none@example.test', 'synthetic-password'), ('ada@example.test', 'wrong-password')]:
        status, body = http(base, 'POST', '/auth/login', {'email': email, 'password': password})
        require(status == 401 and body['error']['code'] == 'unauthenticated', 'R1-063 login error')
    for body, status_expected, code in [
        ({'email': 'x@example.test', 'password': 'short', 'display_name': 'X'}, 422, 'validation_failed'),
        ({'email': 'invalid', 'password': 'synthetic-password', 'display_name': 'X'}, 422, 'validation_failed'),
        ({'email': 'ada@example.test', 'password': 'synthetic-password', 'display_name': 'X'}, 409, 'email_taken'),
        ({'email': 'ada@other.test', 'password': 'synthetic-password', 'display_name': 'X'}, 409, 'handle_taken')]:
        status, actual = http(base, 'POST', '/auth/signup', body)
        require(status == status_expected and actual['error']['code'] == code, 'R1-060/064 signup validation')
    body = {'email': 'MiX.ed+LongLocalPartMoreThan20@example.test', 'password': 'synthetic-password', 'display_name': 'New'}
    status, signup = http(base, 'POST', '/auth/signup', body)
    require(status == 201 and signup.get('display_name') == 'New' and isinstance(signup.get('token'), str), 'R1-058 signup')
    status, me = http(base, 'GET', '/me', token=signup['token'])
    require(status == 200 and me['balance'] == 0 and me['handle'] == 'mix_ed_longlocalpart' and me['user_id'] == signup['user_id'], 'R1-027/029 derived handle and zero balance')
    status, logged = http(base, 'POST', '/auth/login', {'email': body['email'], 'password': body['password']})
    require(status == 200, 'R1-066 second session')
    require(http(base, 'GET', '/me', token=signup['token'])[0] == 200 and http(base, 'GET', '/me', token=logged['token'])[0] == 200, 'R1-066 both sessions valid')
    for currency, units in [('JPY', 0), ('BHD', 3)]:
        r = Runner(base, dict(FIXTURE, currency=currency, minor_units=units))
        r.run(op('ada', '/payments', {'to_handle': 'bob', 'amount': 1000}, 'currency'))
    require(http(base, 'GET', '/me', token=signup['token'])[0] == 401, 'R1-129 reset clears old tokens')
    no_operator = Runner(base, {k: v for k, v in FIXTURE.items() if k != 'settlement_operator_ids'})
    no_operator.run(op('ada', '/settlements', {'transfers': [{'from_handle': 'ada', 'to_handle': 'bob', 'amount': 1}]}, 'no-operator'))
    # Check exact high balance arithmetic close to the representable limit.
    high = deepcopy(FIXTURE)
    high['users'][0]['balance'] = 2 ** 53 - 10000
    r = Runner(base, high)
    r.run(op('ada', '/payments', {'to_handle': 'bob', 'amount': 999999999}, 'large'))


def boundary_case():
    fixture = deepcopy(FIXTURE)
    fixture['users'][0]['balance'] = 2 ** 53
    # Stage3 reconstructs opening balances; do not invent an opening above2^53
    # by combining this maximum ending balance with a seeded outgoing payment.
    fixture['payments'] = []
    operations = [
        op('ada', '/payments', {'to_handle': 'bob', 'amount': 1}, 'boundary-out'),
        op('bob', '/payments', {'to_handle': 'ada', 'amount': 1}, 'boundary-back'),
        op('ada', '/settlements', {'transfers': [
            {'from_handle': 'ada', 'to_handle': 'bob', 'amount': 1},
            {'from_handle': 'bob', 'to_handle': 'ada', 'amount': 1}
        ]}, 'boundary-net')]
    return fixture, operations


def balance_boundary(base, second_url=None):
    fixture, operations = boundary_case()
    runner = Runner(base, fixture)
    for operation in operations:
        runner.run(operation)
    persistence(runner, second_url)


def seeded_and_expiry(base):
    now = int(time.time())
    future = datetime.fromtimestamp(now + 7200, timezone.utc).isoformat()
    past = datetime.fromtimestamp(now - 7200, timezone.utc).isoformat()
    fixture = deepcopy(FIXTURE)
    fixture['authorizations'] = [
        {'id': 'a_seed_' + status, 'from_user_id': 'u_ada', 'to_user_id': 'u_bob',
         'amount': 2000, 'status': status, 'expires_at': past if status == 'expired' else future}
        for status in ['open', 'captured', 'voided', 'expired']]
    fixture['authorizations'].append({'id':'a_past_open','from_user_id':'u_ada','to_user_id':'u_bob',
        'amount':100000,'status':'open','expires_at':past})
    fixture['users'][0]['available'] = 999999
    r = Runner(base, fixture)
    r.observe()
    r.run(op('bob', '/authorizations/a_past_open/capture', {}, 'expired'))
    r.run(op('ada', '/authorizations/a_past_open/void'))
    bad = deepcopy(fixture)
    bad['authorizations'][0]['amount'] = 10001
    for invalid in [bad] + [dict(fixture, authorization_ttl_seconds=n) for n in [0, -1, 0.5, True, None, '600']]:
        status, body = http(base, 'POST', '/_test/reset', invalid)
        require(status == 422 and body['error']['code'] == 'validation_failed', 'R2 reset hold/TTL validation')
        r.observe()
    short = dict(FIXTURE, authorization_ttl_seconds=3)
    r = Runner(base, short)
    created = r.run(op('ada', '/authorizations', {'to_handle':'bob','amount':2000}, 'short'))
    a = r.state['authorizations'][-1]
    path = '/authorizations/' + a['authorization_id'] + '/capture'
    r.run(op('bob', path, {'amount':700,'final':False}, 'partial'))
    deadline = datetime.fromisoformat(created['expires_at']).timestamp()
    time.sleep(max(0, deadline - time.time() + 0.15))
    r.observe()
    for user in ['ada', 'bob', 'cy']:
        r.run(op(user, '/authorizations', method='GET', query={'status':'expired'}))
    r.run(op('bob', path, {}, 'expired'))
    r.run(op('ada', '/authorizations/' + a['authorization_id'] + '/void'))
    r.run(op('bob', path, {'amount':700,'final':False}, 'partial'))
    r.run(op('ada', '/authorizations', {'to_handle':'bob','amount':2000}, 'short'))
    r.run(op('ada', '/payments', {'to_handle':'cy','amount':9300}, 'released'))


def migration(stage1_url, stage2_url):
    """No source imports: use stage1 HTTP only and keep opaque credentials in memory."""
    status, _ = http(stage1_url, 'POST', '/_test/reset', FIXTURE)
    require(status == 204, 'R2 migration source reset')
    tokens = {}
    for u in FIXTURE['users']:
        status, response = http(stage1_url, 'POST', '/auth/login', {'email':u['email'],'password':u['password']})
        require(status == 200, 'R2 migration source login')
        tokens[u['handle']] = response['token']
    request_body = {'payer_handle':'ada','amount':100,'note':'migration pending'}
    status, request = http(stage1_url, 'POST', '/requests', request_body, token=tokens['bob'], key='migration-request')
    require(status == 201, 'R2 migration source pending request')
    body = {'to_handle':'bob','amount':123,'note':'lost receipt','visibility':'private'}
    status, receipt = http(stage1_url, 'POST', '/payments', body, token=tokens['ada'], key='migration-lost')
    require(status == 201, 'R2 migration source payment')
    status, snapshot = http(stage1_url, 'GET', '/_test/export')
    require(status == 200, 'R2 migration export')
    destination = Runner(stage2_url)
    for _ in range(2):
        require(http(stage2_url, 'POST', '/_test/import', snapshot)[0] == 204, 'R2 stage1 import')
    require(http(stage2_url, 'GET', '/me', token=destination.tokens['ada'])[0] == 401, 'R2 migration replacement')
    for user, token in tokens.items():
        status, me = http(stage2_url, 'GET', '/me', token=token)
        expected = next(u['balance'] for u in FIXTURE['users'] if u['handle']==user)
        expected += -123 if user=='ada' else 123 if user=='bob' else 0
        require(status == 200 and me['balance'] == me['total'] == me['available'] == expected and me['held'] == 0,
                'R2 migration session and totals')
    status, replay = http(stage2_url, 'POST', '/payments', body, token=tokens['ada'], key='migration-lost')
    require(status == 200 and replay == receipt, 'R2 migration exact historical receipt')
    status, replay_request = http(stage2_url, 'POST', '/requests', request_body, token=tokens['bob'], key='migration-request')
    require(status == 200 and replay_request == request, 'R2 migration request replay')
    status, paid = http(stage2_url, 'POST', '/requests/' + request['request_id'] + '/pay', {}, token=tokens['ada'], key='migration-pay')
    require(status == 201 and paid['amount'] == 100 and paid['authorization_id'] is None, 'R2 migration request payable')
    status, me = http(stage2_url, 'GET', '/me', token=tokens['ada'])
    require(status == 200 and me['total'] == 9777, 'R2 migration no duplicate movement')


def self_test():
    require(bind_path('/requests/@id:request:71/pay', {'@id:request:7': 'wrong', '@id:request:71': 'correct'})
            == '/requests/correct/pay', 'adapter exact segment binding')
    state = initial(FIXTURE)
    count = 0
    for operation in deterministic():
        before = deepcopy(state)
        state, response = transition(state, operation)
        require(before is not state, 'pure state copy')
        if response['status'] >= 400:
            require(state == before, 'failed operation pure no-op')
        count += 1
    more = lifecycle_ops(deepcopy(state))
    for operation in more:
        state, response = transition(state, operation)
        count += 1
    for operation in edge_ops(state):
        state, response = transition(state, operation)
        count += 1
    for operation in random_ops(state, 20261001, 500):
        state, response = transition(state, operation)
        count += 1
    zero = initial(FIXTURE)
    zero, response = transition(zero, op('ada', '/splits', {'amount': 1, 'participant_handles': ['ada', 'bob', 'cy']}, 'zero'))
    require([x['amount'] for x in response['body']['shares']] == [1, 0, 0], 'R1-112/114 split example')
    for request in response['body']['requests']:
        zero, paid = transition(zero, op(request['payer_handle'], '/requests/' + request['request_id'] + '/pay', {}, 'z'))
        require(paid['status'] == 201 and paid['body']['amount'] == 0, 'R1-114 payable zero')
    fixture, operations = boundary_case()
    boundary = initial(fixture)
    for operation in operations:
        boundary, response = transition(boundary, operation)
        require(response['status'] == 201, 'R1-041 boundary operation')
    require(boundary['users']['ada']['balance'] == 2 ** 53 and
            boundary['total'] == sum(u['balance'] for u in fixture['users']),
            'R1-041 inclusive boundary and exact aggregate')
    auth_state = initial(FIXTURE)
    auth_count = 0
    for operation in authorization_ops(auth_state):
        auth_state, response = transition(auth_state, operation)
        auth_count += 1
    for operation in authorization_random(auth_state, 42, 500):
        auth_state, response = transition(auth_state, operation)
        auth_count += 1
    timed = initial(dict(FIXTURE, authorization_ttl_seconds=3), now=100)
    timed, response = transition(timed, op('ada','/authorizations',{'to_handle':'bob','amount':2000},'ttl'))
    aid = response['body']['authorization_id']
    timed, _ = transition(timed, op('bob','/authorizations/'+aid+'/capture',{'amount':700,'final':False},'partial',now=102))
    timed, expired = transition(timed, op('bob','/authorizations/'+aid+'/capture',{},'expired',now=103))
    require(expired['body']['error']['code']=='authorization_expired' and timed['authorizations'][0]['remaining_amount']==0,
            'R2 exact expiry boundary')
    require(timed['authorizations'][0]['captured_amount']==700, 'R2 expiry preserves partial capture')
    print('MODEL SELF-TEST PASS operations=' + str(count) + ' boundary=pass authorization_operations=' + str(auth_count) + ' expiry=pass')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url')
    parser.add_argument('--second-url', help='optional fresh second process for portable import check')
    parser.add_argument('--stage1-url', help='isolated frozen stage1 service for upgrade import; destructive reset')
    parser.add_argument('--seed', type=int, default=20261001)
    parser.add_argument('--steps', type=int, default=100)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--replay', type=Path)
    parser.add_argument('--no-shrink', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    parser.error('--base-url is required') if not args.base_url else None
    operations = json.loads(args.replay.read_text()) if args.replay else authorization_ops(initial(FIXTURE)) + deterministic()
    if not args.replay:
        simulated = initial(FIXTURE)
        for operation in operations:
            simulated, _ = transition(simulated, operation)
        more = lifecycle_ops(deepcopy(simulated))
        for operation in more:
            simulated, _ = transition(simulated, operation)
        edges = edge_ops(simulated)
        for operation in edges:
            simulated, _ = transition(simulated, operation)
        randoms = random_ops(simulated, args.seed, args.steps)
        for operation in randoms:
            simulated, _ = transition(simulated, operation)
        operations += more + edges + randoms + authorization_random(simulated, args.seed, args.steps)
    try:
        runner = run_sequence(args.base_url, operations)
    except Mismatch as error:
        print('DIFFERENTIAL FAIL ' + str(error))
        minimal, attempts = (operations, 0) if args.no_shrink else shrink(args.base_url, operations, error.label)
        directory = Path(tempfile.mkdtemp(prefix='pocketful-model-'))
        path = directory / 'reproduction.json'
        path.write_text(json.dumps(minimal, indent=2, ensure_ascii=False) + '\n')
        print('REPRO operations=' + str(len(minimal)) + ' shrink_attempts=' + str(attempts) + ' file=' + str(path))
        raise SystemExit(1)
    if not args.replay:
        try:
            persistence(runner, args.second_url)
            concurrency(args.base_url)
            auth_and_controls(args.base_url)
            balance_boundary(args.base_url, args.second_url)
            seeded_and_expiry(args.base_url)
            if args.stage1_url:
                migration(args.stage1_url, args.base_url)
        except Mismatch as error:
            print('CONTRACT FAIL ' + str(error))
            raise SystemExit(1)
    print('DIFFERENTIAL PASS operations=' + str(len(operations)) + ' seed=' + str(args.seed) +
          (' replay-only' if args.replay else ' persistence=pass concurrency=50 auth-controls=pass boundary=pass holds-expiry=pass migration=' + ('pass' if args.stage1_url else 'NOT_RUN')))


if __name__ == '__main__':
    main()
