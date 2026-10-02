#!/usr/bin/env python3
"""Independent Stage 1 checks. Usage: python3 probe.py http://service:8080

Never prints request credentials, response tokens, or opaque exports.
Uses only Python's standard library. Each failure prints a named assertion.
"""
import concurrent.futures as cf
import json
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip('/')
COUNT = 0
MAX_LATENCY = 0
PASSWORD = secrets.token_urlsafe(20)


def check(ok, name):
    global COUNT
    COUNT += 1
    if not ok:
        raise AssertionError(name)


def call(method, path, body=None, token=None, key=None):
    global MAX_LATENCY
    headers = {'Content-Type': 'application/json; charset=utf-8'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if key is not None:
        headers['Idempotency-Key'] = key
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    start = time.monotonic()
    try:
        response = urllib.request.urlopen(req, timeout=10 if path.startswith('/_test/') else 5)
    except urllib.error.HTTPError as exc:
        response = exc
    raw = response.read()
    elapsed = time.monotonic() - start
    MAX_LATENCY = max(MAX_LATENCY, elapsed)
    check(elapsed < (10 if path.startswith('/_test/') else 5), 'request timeout ' + path)
    check(response.status < 500, 'no 5xx ' + path)
    value = json.loads(raw) if raw else None
    if response.status >= 400:
        check(isinstance(value.get('error', {}).get('message'), str), 'error envelope')
    return response.status, value


def seed(balance=20):
    fixture = {'currency': 'EUR', 'minor_units': 2, 'users': [
        {'id': 'u_' + h, 'email': h + '@example.test', 'password': PASSWORD,
         'display_name': h, 'handle': h, 'balance': balance if h == 'a' else 0}
        for h in ['a', 'b', 'c']], 'settlement_operator_ids': ['u_c'],
        'payments': [], 'requests': []}
    check(call('POST', '/_test/reset', fixture)[0] == 204, 'reset')
    tokens = {}
    for h in ['a', 'b', 'c']:
        status, value = call('POST', '/auth/login', {'email': h + '@example.test', 'password': PASSWORD})
        check(status == 200, 'login')
        tokens[h] = value['token']
    return tokens


def balance(token):
    status, value = call('GET', '/me', token=token)
    check(status == 200, 'read wallet')
    check(value['balance'] >= 0, 'nonnegative wallet')
    return value['balance']


def burst(function, n=50):
    barrier = threading.Barrier(n)
    def run(i):
        barrier.wait()
        return function(i)
    with cf.ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(run, range(n)))


def serial_history(events, initial):
    """Find a serial witness for unit debits and wallet reads via count intervals.

    Successful unit debits induce ranks 1..N. Each read fixes its rank. Real-time
    precedence and read-rank precedence form a DAG; an acyclic graph gives a
    concrete one-at-a-time order. Failed overdrafts require the exhausted rank.
    """
    edges = [set() for _ in events]
    for i, a in enumerate(events):
        for j, b in enumerate(events):
            if i != j and a['end'] <= b['start']:
                edges[i].add(j)
            if i != j and a['kind'] == b['kind'] == 'read' and a['rank'] < b['rank']:
                edges[i].add(j)
    # Bounded DFS preserves all real-time edges and validates every read.
    predecessors = [0] * len(events)
    for i, outgoing in enumerate(edges):
        for j in outgoing:
            predecessors[j] |= 1 << i
    full = (1 << len(events)) - 1
    failed = set()
    # Reads at the current rank must precede the next debit. Ordering enabled
    # commutative debits by earliest response prevents factorial exploration.
    order = sorted(range(len(events)), key=lambda i: (events[i]['kind'] == 'write', events[i]['end']))
    def visit(mask, used):
        if mask == full:
            return True
        if mask in failed:
            return False
        check(len(failed) < 100000, 'history search budget (inconclusive if exhausted)')
        for i in order:
            event = events[i]
            bit = 1 << i
            if mask & bit or predecessors[i] & ~mask:
                continue
            kind = event['kind']
            if kind == 'read' and event['rank'] != used:
                continue
            if kind == 'fail' and used != initial:
                continue
            if kind == 'write' and used >= initial:
                continue
            if visit(mask | bit, used + (kind == 'write')):
                return True
        failed.add(mask)
        return False
    check(visit(0, 0), 'history has a one-at-a-time witness')


def concurrency():
    tokens = seed()
    events = []
    lock = threading.Lock()
    def operation(i):
        if i == 49:
            for n in range(25):
                start = time.monotonic()
                status, snapshot = call('GET', '/_test/export')
                check(status == 200, 'concurrent atomic snapshot')
                state = snapshot['state']
                balances = {u['handle']: u['balance'] for u in state['users']}
                check(sum(balances.values()) == 20, 'every snapshot conserves total')
                check(all(v >= 0 for v in balances.values()), 'every snapshot nonnegative')
                payments = [p['payment'] for p in state['payments']]
                request_ids = [p['request_id'] for p in payments if p['request_id'] is not None]
                check(len(request_ids) == len(set(request_ids)), 'every snapshot requests move once')
                check(balances['b'] == len(payments) == 20 - balances['a'], 'every snapshot movements match receipts')
                event = {'kind': 'read', 'rank': balances['b'],
                         'start': start, 'end': time.monotonic()}
                with lock:
                    events.append(event)
            return
        start = time.monotonic()
        status, value = call('POST', '/payments', {'to_handle': 'b', 'amount': 1}, tokens['a'], 'race-' + str(i))
        check(status in [201, 409], 'overdraft race status')
        if status == 409:
            check(value['error']['code'] == 'insufficient_funds', 'overdraft race code')
        with lock:
            events.append({'kind': 'write' if status == 201 else 'fail', 'start': start, 'end': time.monotonic()})
    burst(operation)
    check(sum(e['kind'] == 'write' for e in events) == 20, 'exactly affordable debits commit')
    check([balance(tokens[h]) for h in ['a', 'b', 'c']] == [0, 20, 0], 'conserved final total')
    serial_history(events, 20)
    tokens = seed(100)
    results = burst(lambda i: call('POST', '/payments', {'to_handle': 'b', 'amount': 3}, tokens['a'], 'identical'))
    check(sum(s == 201 for s, _ in results) == 1, 'one original among 50 identical writes')
    check(sum(s == 200 for s, _ in results) == 49, '49 replay responses')
    check(all(v == results[0][1] for _, v in results), 'replay responses identical')
    status, request = call('POST', '/requests', {'payer_handle': 'a', 'amount': 7}, tokens['b'], 'rq')
    check(status == 201, 'create request for race')
    path = '/requests/' + request['request_id'] + '/pay'
    results = burst(lambda i: call('POST', path, {}, tokens['a'], 'pay-' + str(i)))
    check(sum(s == 201 for s, _ in results) == 1, 'request paid once among 50 distinct keys')
    check(sum(s == 409 and v['error']['code'] == 'request_not_pending' for s, v in results) == 49, 'losers observe terminal request')
    check([balance(tokens[h]) for h in ['a', 'b', 'c']] == [90, 10, 0], 'request conservation')


def semantics():
    tokens = seed(10)
    status, receipt = call('POST', '/settlements', {'transfers': [
        {'from_handle': 'b', 'to_handle': 'a', 'amount': 10, 'visibility': 'private'},
        {'from_handle': 'a', 'to_handle': 'b', 'amount': 10}]}, tokens['c'], 'net')
    check(status == 201, 'net settlement affordable despite unfunded first leg')
    check([balance(tokens[h]) for h in ['a', 'b', 'c']] == [10, 0, 0], 'net settlement balances')
    check(all(p['created_at'] == receipt['committed_at'] and p['settlement_id'] == receipt['settlement_id'] for p in receipt['payments']), 'settlement receipt linkage')
    status, split = call('POST', '/splits', {'amount': 1, 'participant_handles': ['a', 'b', 'c']}, tokens['a'], 'split')
    check(status == 201 and [s['amount'] for s in split['shares']] == [1, 0, 0], 'zero shares preserve exact rounding')
    for h, req in zip(['b', 'c'], split['requests']):
        check(call('POST', '/requests/' + req['request_id'] + '/pay', {}, tokens[h], 'zero')[0] == 201, 'zero share payable')
    status, private = call('POST', '/payments', {'to_handle': 'b', 'amount': 1, 'visibility': 'private'}, tokens['a'], 'private')
    check(status == 201, 'private transfer')
    for h in ['a', 'b', 'c']:
        status, feed = call('GET', '/activity', token=tokens[h])
        check(status == 200, 'activity')
        check((private['payment_id'] in [p['payment_id'] for p in feed['payments']]) == (h != 'c'), 'private visibility including operator')
    _, req = call('POST', '/requests', {'payer_handle': 'a', 'amount': 1}, tokens['b'], 'auth-rq')
    for action in ['pay', 'decline', 'cancel']:
        status, error = call('POST', '/requests/' + req['request_id'] + '/' + action, {}, tokens['c'], 'foreign')
        check(status == 403 and error['error']['code'] == 'forbidden', 'foreign request ' + action)
        wrong_party = 'a' if action == 'cancel' else 'b'
        status, error = call('POST', '/requests/' + req['request_id'] + '/' + action, {}, tokens[wrong_party], 'wrong-role')
        check(status == 403 and error['error']['code'] == 'forbidden', 'visible wrong-role request ' + action)
    status, error = call('POST', '/payments', {'amount': False}, tokens['a'], 'private')
    check(status == 409 and error['error']['code'] == 'idempotency_key_reuse', 'replay precedence over invalid fields')
    status, exported = call('GET', '/_test/export')
    check(status == 200 and exported['track'] == 'pocketful' and exported['format_version'] == 1, 'export envelope')
    before = [balance(tokens[h]) for h in ['a', 'b', 'c']]
    seed(999)
    for _ in range(2):
        check(call('POST', '/_test/import', exported)[0] == 204, 'repeat replacement import')
        check([balance(tokens[h]) for h in ['a', 'b', 'c']] == before, 'import preserves balances and old tokens')
        status, replay = call('POST', '/payments', {'to_handle': 'b', 'amount': 1, 'visibility': 'private'}, tokens['a'], 'private')
        check(status == 200 and replay == private, 'import preserves original idempotent receipt')
        check(call('POST', '/auth/login', {'email': 'a@example.test', 'password': PASSWORD})[0] == 200, 'import preserves password login')


if __name__ == '__main__':
    try:
        concurrency()
        semantics()
        print(json.dumps({'result': 'PASS', 'assertions': COUNT, 'max_request_seconds': round(MAX_LATENCY, 4)}))
    except Exception as exc:
        # No exception representation: transport errors may include private input.
        print(json.dumps({'result': 'FAIL', 'assertions': COUNT, 'check': str(exc) if isinstance(exc, AssertionError) else type(exc).__name__}))
        sys.exit(1)
