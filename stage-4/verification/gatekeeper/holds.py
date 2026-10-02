#!/usr/bin/env python3
"""Independent hold/capture semantics and 50-flight linearizability.

Usage: python3 holds.py URL. Credentials and opaque exports never printed.
"""
import json
import threading
import time
from datetime import datetime, timedelta, timezone
import probe as p


def seed(balance=100, ttl=600, authorizations=None):
    fixture = {'currency': 'EUR', 'minor_units': 2, 'authorization_ttl_seconds': ttl,
        'users': [{'id': 'u_' + h, 'email': h + '@example.test', 'password': p.PASSWORD,
                   'display_name': h, 'handle': h, 'balance': balance if h == 'a' else 0} for h in ['a', 'b', 'c']],
        'payments': [], 'requests': [], 'authorizations': authorizations or [], 'settlement_operator_ids': ['u_c']}
    p.check(p.call('POST', '/_test/reset', fixture)[0] == 204, 'stage2 reset')
    tokens = {}
    for h in ['a', 'b', 'c']:
        status, user = p.call('POST', '/auth/login', {'email': h + '@example.test', 'password': p.PASSWORD})
        p.check(status == 200, 'stage2 seed login')
        tokens[h] = user['token']
    return tokens


def wallet(token, total, held):
    status, me = p.call('GET', '/me', token=token)
    p.check(status == 200, 'wallet status')
    p.check((me['balance'], me['total'], me['held'], me['available']) == (total, total, held, total - held), 'wallet total/held/available exact')


def hold(tokens, amount, key='hold'):
    status, auth = p.call('POST', '/authorizations', {'to_handle': 'b', 'amount': amount, 'note': 'held money', 'visibility': 'private'}, tokens['a'], key)
    p.check(status == 201, 'authorize succeeds')
    p.check(auth['remaining_amount'] == amount and auth['payment_ids'] == [], 'new hold remainder and history')
    return auth


def error(method, path, body, token, key, expected_status, code):
    status, value = p.call(method, path, body, token, key)
    p.check(status == expected_status and value['error']['code'] == code, 'error ' + path + ' ' + code)


def semantics():
    tokens = seed()
    auth = hold(tokens, 60)
    aid = auth['authorization_id']
    capture = '/authorizations/' + aid + '/capture'
    wallet(tokens['a'], 100, 60)
    p.check(p.call('GET', '/activity', token=tokens['a'])[1]['payments'] == [], 'hold never enters feed')
    error('POST', '/payments', {'to_handle': 'b', 'amount': 41}, tokens['a'], 'held-payment', 409, 'insufficient_funds')
    _, req = p.call('POST', '/requests', {'payer_handle': 'a', 'amount': 41}, tokens['b'], 'held-request')
    error('POST', '/requests/' + req['request_id'] + '/pay', {}, tokens['a'], 'held-pay', 409, 'insufficient_funds')
    error('POST', '/settlements', {'transfers': [{'from_handle': 'a', 'to_handle': 'b', 'amount': 41}]}, tokens['c'], 'held-settlement', 409, 'insufficient_funds')
    for who in ['a', 'c']:
        error('POST', capture, {}, tokens[who], 'forbidden-' + who, 403, 'forbidden')
    error('POST', '/authorizations/' + aid + '/void', {}, tokens['b'], None, 403, 'forbidden')
    p.check(p.call('GET', '/authorizations', token=tokens['c'])[1]['authorizations'] == [], 'operator has no unrelated authorizations')
    partial_body = {'amount': 20, 'final': False}
    status, partial = p.call('POST', capture, partial_body, tokens['b'], 'partial')
    p.check(status == 201 and partial['authorization_id'] == aid and partial['request_id'] is None and partial['visibility'] == 'private', 'partial capture receipt')
    wallet(tokens['a'], 80, 40)
    wallet(tokens['b'], 20, 0)
    error('POST', capture, {'amount': 41}, tokens['b'], 'too-much', 422, 'capture_exceeds_authorization')
    error('POST', capture, {'amount': 1, 'final': 'false'}, tokens['b'], 'wrong-type', 400, 'malformed_request')
    status, final = p.call('POST', capture, {'amount': 10}, tokens['b'], 'final')
    p.check(status == 201, 'partial amount final capture')
    wallet(tokens['a'], 70, 0)
    auth_after = p.call('GET', '/authorizations', token=tokens['a'])[1]['authorizations'][0]
    p.check(auth_after['status'] == 'captured' and auth_after['remaining_amount'] == 0 and auth_after['captured_amount'] == 30, 'final releases remainder')
    p.check(auth_after['payment_ids'] == [partial['payment_id'], final['payment_id']] and auth_after['payment_id'] == final['payment_id'], 'ordered capture history')
    p.check(p.call('POST', capture, partial_body, tokens['b'], 'partial') == (200, partial), 'replay original partial after closure')
    error('POST', capture, {}, tokens['b'], 'after-close', 409, 'authorization_not_open')
    p.check(p.call('GET', '/activity', token=tokens['c'])[1]['payments'] == [], 'private captures hidden from operator')
    auth2 = hold(tokens, 20, 'hold2')
    path = '/authorizations/' + auth2['authorization_id']
    p.check(p.call('POST', path + '/capture', {'amount': 5, 'final': False}, tokens['b'], 'partial2')[0] == 201, 'second partial')
    status, voided = p.call('POST', path + '/void', {}, tokens['a'])
    p.check(status == 200 and voided['captured_amount'] == 5 and voided['remaining_amount'] == 0 and len(voided['payment_ids']) == 1, 'void preserves captures/releases only remainder')
    p.check(p.call('POST', path + '/void', {}, tokens['a']) == (200, voided), 'void replay stable')
    wallet(tokens['a'], 65, 0)


def expiry():
    tokens = seed(ttl=1)
    auth = hold(tokens, 20)
    created = datetime.fromisoformat(auth['created_at'])
    expires = datetime.fromisoformat(auth['expires_at'])
    p.check((expires - created).total_seconds() == 1, 'expiry is created plus TTL')
    time.sleep(max(0, expires.timestamp() - time.time()) + .08)
    path = '/authorizations/' + auth['authorization_id']
    error('POST', path + '/capture', {}, tokens['b'], 'expired', 409, 'authorization_expired')
    wallet(tokens['a'], 100, 0)
    result = p.call('GET', '/authorizations?status=expired', token=tokens['a'])[1]['authorizations']
    p.check(len(result) == 1 and result[0]['status'] == 'expired' and result[0]['remaining_amount'] == 0, 'expiry reflected on read')
    error('POST', path + '/capture', {}, tokens['b'], 'expired-read', 409, 'authorization_expired')
    error('POST', path + '/void', {}, tokens['a'], None, 409, 'authorization_not_open')
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    for state, code in [('expired', 'authorization_expired'), ('captured', 'authorization_not_open'), ('voided', 'authorization_not_open')]:
        tokens = seed(authorizations=[{'id': 'old', 'from_user_id': 'u_a', 'to_user_id': 'u_b', 'amount': 5, 'status': state, 'expires_at': past, 'note': '', 'visibility': 'public'}])
        error('POST', '/authorizations/old/capture', {}, tokens['b'], 'old', 409, code)


def authorization_record(record):
    # Adapter for the implementation-defined export. Fail closed on a new shape.
    for candidate in [record, record.get('authorization'), record.get('a')]:
        if isinstance(candidate, dict) and 'from_user_id' in candidate and 'captured_amount' in candidate:
            return candidate
    raise AssertionError('authorization export adapter requires review')


def concurrent_available():
    tokens = seed()
    events = []
    lock = threading.Lock()
    def run(i):
        if i == 49:
            for _ in range(25):
                started = time.monotonic()
                status, snapshot = p.call('GET', '/_test/export')
                p.check(status == 200, 'atomic stage2 snapshot')
                state = snapshot['state']
                users = {u['id']: u for u in state['users']}
                auths = [authorization_record(a) for a in state.get('authorizations', [])]
                held = {uid: sum(a['amount'] - a['captured_amount'] for a in auths if a['from_user_id'] == uid and a['status'] == 'open') for uid in users}
                p.check(sum(u['balance'] for u in users.values()) == 100, 'every snapshot conserves total')
                p.check(all(u['balance'] >= held[uid] >= 0 for uid, u in users.items()), 'every snapshot available and held nonnegative')
                p.check(all(0 <= a['captured_amount'] <= a['amount'] for a in auths), 'every snapshot captures within authorization')
                available = users['u_a']['balance'] - held['u_a']
                p.check((100 - available) % 3 == 0, 'available follows whole committed operations')
                with lock:
                    events.append({'kind': 'read', 'rank': (100 - available) // 3, 'start': started, 'end': time.monotonic()})
            return
        started = time.monotonic()
        path = '/authorizations' if i % 2 else '/payments'
        status, value = p.call('POST', path, {'to_handle': 'b', 'amount': 3}, tokens['a'], 'available-' + str(i))
        p.check(status in [201, 409], 'competing hold/payment status')
        if status == 409:
            p.check(value['error']['code'] == 'insufficient_funds', 'competing failure uses available')
        with lock:
            events.append({'kind': 'write' if status == 201 else 'fail', 'start': started, 'end': time.monotonic()})
    p.burst(run)
    p.check(sum(e['kind'] == 'write' for e in events) == 33, 'exactly33 affordable operations')
    p.serial_history(events, 33)
    _, me = p.call('GET', '/me', token=tokens['a'])
    p.check(me['available'] == 1 and me['balance'] == me['total'] and me['total'] - me['held'] == 1, 'final available matches serial history')


def replay_races():
    tokens = seed()
    body = {'to_handle': 'b', 'amount': 50}
    results = p.burst(lambda i: p.call('POST', '/authorizations', body, tokens['a'], 'same-hold'))
    p.check(sum(s == 201 for s, _ in results) == 1 and sum(s == 200 for s, _ in results) == 49, '50 hold replays have one original')
    original = results[0][1]
    p.check(all(value == original for _, value in results), 'hold replay bodies identical')
    wallet(tokens['a'], 100, 50)
    path = '/authorizations/' + original['authorization_id'] + '/capture'
    results = p.burst(lambda i: p.call('POST', path, {'amount': 20, 'final': False}, tokens['b'], 'same-capture'))
    p.check(sum(s == 201 for s, _ in results) == 1 and sum(s == 200 for s, _ in results) == 49, '50 capture replays have one original')
    p.check(all(value == results[0][1] for _, value in results), 'capture replay bodies identical')
    wallet(tokens['a'], 80, 30)
    wallet(tokens['b'], 20, 0)


def capture_races():
    tokens = seed()
    auth = hold(tokens, 50)
    path = '/authorizations/' + auth['authorization_id'] + '/capture'
    results = p.burst(lambda i: p.call('POST', path, {'amount': 1, 'final': False}, tokens['b'], 'capture-' + str(i)))
    p.check(all(s == 201 for s, _ in results), '50 distinct partial captures exactly exhaust hold')
    wallet(tokens['a'], 50, 0)
    result = p.call('GET', '/authorizations', token=tokens['a'])[1]['authorizations'][0]
    p.check(result['status'] == 'captured' and result['captured_amount'] == 50 and result['remaining_amount'] == 0 and len(set(result['payment_ids'])) == 50, 'capture invariant after burst')
    tokens = seed()
    auth = hold(tokens, 50)
    path = '/authorizations/' + auth['authorization_id']
    results = p.burst(lambda i: p.call('POST', path + ('/capture' if i % 2 else '/void'), {}, tokens['b'] if i % 2 else tokens['a'], 'race-' + str(i) if i % 2 else None))
    p.check(all(s in [200, 201, 409] for s, _ in results), 'capture/void race has no invalid outcome')
    captured = sum(s == 201 for s, _ in results)
    p.check(captured <= 1, 'final capture wins at most once against void')
    wallet(tokens['a'], 50 if captured else 100, 0)
    wallet(tokens['b'], 50 if captured else 0, 0)


if __name__ == '__main__':
    try:
        semantics()
        expiry()
        concurrent_available()
        capture_races()
        replay_races()
        print(json.dumps({'result': 'PASS', 'assertions': p.COUNT, 'max_request_seconds': round(p.MAX_LATENCY, 4)}))
    except Exception as exc:
        print(json.dumps({'result': 'FAIL', 'assertions': p.COUNT, 'check': str(exc) if isinstance(exc, AssertionError) else type(exc).__name__}))
        raise SystemExit(1)
