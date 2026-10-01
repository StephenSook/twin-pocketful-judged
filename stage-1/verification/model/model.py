"""Independent, pure Pocketful stage-1 transition function. Standard library only.

Identifiers and clocks are symbolic. The live driver binds them to opaque service values.
No product imports, storage, network, threads, or mutation of the input state.
"""
from copy import deepcopy
import json
import re


class Fault(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


def fail(status, code):
    raise Fault(status, code)


def value(body, key, kind):
    if key not in body:
        fail(422, 'validation_failed')
    if not isinstance(body[key], kind) or isinstance(body[key], bool):
        fail(400, 'malformed_request')
    return body[key]


def amount(body):
    n = body.get('amount')
    if type(n) not in (int, float) or not 1 <= n <= 1000000000 or int(n) != n:
        fail(422, 'validation_failed')
    return int(n)


def note(body):
    n = body.get('note', '')
    if not isinstance(n, str) or len(n) > 200:
        fail(422, 'validation_failed')
    return n


def visibility(body):
    v = body.get('visibility', 'public')
    if v not in ('public', 'private'):
        fail(422, 'validation_failed')
    return v


def canonical(body):
    # JSON number spelling is not part of JSON-value identity. Booleans remain distinct.
    if type(body) is float and body.is_integer():
        return int(body)
    if isinstance(body, list):
        return [canonical(v) for v in body]
    if isinstance(body, dict):
        return {k: canonical(v) for k, v in body.items()}
    return body


def initial(fixture):
    s = {'users': {u['handle']: deepcopy(u) for u in fixture['users']},
         'currency': fixture['currency'], 'minor_units': fixture['minor_units'],
         'operators': fixture.get('settlement_operator_ids', []),
         'payments': [], 'requests': [], 'keys': {}, 'serial': 0}
    by_id = {u['id']: h for h, u in s['users'].items()}
    for p in fixture.get('payments', []):
        a, b = by_id[p['from_user_id']], by_id[p['to_user_id']]
        s['payments'].append({'payment_id': p['id'], 'from_user_id': p['from_user_id'],
            'to_user_id': p['to_user_id'], 'from_handle': a, 'to_handle': b,
            'amount': p['amount'], 'note': p.get('note', ''),
            'visibility': p.get('visibility', 'public'), 'currency': s['currency'],
            'request_id': p.get('request_id'), 'settlement_id': p.get('settlement_id'),
            'created_at': p.get('created_at', '@time:seed:' + p['id'])})
    for r in fixture.get('requests', []):
        a, b = by_id[r['requester_id']], by_id[r['payer_id']]
        s['requests'].append({'request_id': r['id'], 'requester_id': r['requester_id'],
            'payer_id': r['payer_id'], 'requester_handle': a, 'payer_handle': b,
            'amount': r['amount'], 'note': r.get('note', ''), 'status': r['status'],
            'currency': s['currency'], 'payment_id': r.get('payment_id'),
            'created_at': r.get('created_at', '@time:seed:' + r['id'])})
    s['total'] = sum(u['balance'] for u in s['users'].values())
    return s


def identity(s, kind):
    s['serial'] += 1
    return '@id:' + kind + ':' + str(s['serial'])


def existing(s, handle):
    if handle not in s['users']:
        fail(404, 'not_found')
    return handle


def make_payment(s, sender, recipient, n, memo, vis, request=None, settlement=None, when=None):
    p = {'payment_id': identity(s, 'payment'), 'from_user_id': s['users'][sender]['id'],
         'to_user_id': s['users'][recipient]['id'], 'from_handle': sender,
         'to_handle': recipient, 'amount': n, 'currency': s['currency'], 'note': memo,
         'visibility': vis, 'request_id': request, 'settlement_id': settlement,
         'created_at': when or '@time:' + str(s['serial'])}
    s['payments'].append(p)
    return p


def make_request(s, requester, payer, n, memo):
    r = {'request_id': identity(s, 'request'), 'requester_id': s['users'][requester]['id'],
         'payer_id': s['users'][payer]['id'], 'requester_handle': requester,
         'payer_handle': payer, 'amount': n, 'currency': s['currency'], 'note': memo,
         'status': 'pending', 'payment_id': None, 'created_at': '@time:' + str(s['serial'])}
    s['requests'].append(r)
    return r


def transfer(s, sender, recipient, n):
    if s['users'][sender]['balance'] < n:
        fail(409, 'insufficient_funds')
    s['users'][sender]['balance'] -= n
    s['users'][recipient]['balance'] += n


def transition(state, op):
    """Return (new_state, {status, body}) from a state and abstract HTTP operation.

    op: method, path, user (fixture handle or None), body, optional key/query.
    Caller auth token parsing belongs to the HTTP adapter, represented by user=None.
    Every failure returns an unmodified copy of the original state.
    """
    s = deepcopy(state)
    try:
        status, body = execute(s, op)
        assert all(u['balance'] >= 0 for u in s['users'].values())
        assert sum(u['balance'] for u in s['users'].values()) == s['total']
        return s, {'status': status, 'body': deepcopy(body)}
    except Fault as e:
        return deepcopy(state), {'status': e.status, 'body': {'error': {'code': e.code}}}


def execute(s, op):
    method, path, user = op.get('method', 'POST'), op['path'], op.get('user')
    if path == '/health' and method == 'GET':
        return 200, {'status': 'ok'}
    if user not in s['users']:
        fail(401, 'unauthenticated')
    body = op.get('body', {})
    if method == 'POST' and (op.get('malformed') or not isinstance(body, dict)):
        fail(400, 'malformed_request')
    if method == 'GET':
        if path == '/me':
            u = s['users'][user]
            return 200, {'user_id': u['id'], 'display_name': u['display_name'],
                'handle': user, 'balance': u['balance'], 'currency': s['currency'],
                'minor_units': s['minor_units']}
        if path in ('/activity', '/requests'):
            q = op.get('query', {})
            integers = {}
            for k, default, lower, upper in [('limit', '50', 1, 200), ('offset', '0', 0, None)]:
                raw = q.get(k, default)
                if not re.fullmatch('[0-9]+', raw):
                    fail(422, 'validation_failed')
                n = int(raw)
                if n < lower or upper is not None and n > upper:
                    fail(422, 'validation_failed')
                integers[k] = n
            if path == '/requests':
                direction, status = q.get('direction'), q.get('status')
                if direction not in (None, 'incoming', 'outgoing') or status not in (None, 'pending', 'paid', 'declined', 'cancelled'):
                    fail(422, 'validation_failed')
                rows = [r for r in s['requests'] if user in (r['requester_handle'], r['payer_handle'])]
                if direction:
                    field = 'payer_handle' if direction == 'incoming' else 'requester_handle'
                    rows = [r for r in rows if r[field] == user]
                if status:
                    rows = [r for r in rows if r['status'] == status]
                field = 'requests'
            else:
                rows = [p for p in s['payments'] if p['visibility'] == 'public' or user in (p['from_handle'], p['to_handle'])]
                field = 'payments'
            rows = list(reversed(rows))
            offset, limit = integers['offset'], integers['limit']
            return 200, {field: rows[offset:offset + limit], 'has_more': offset + limit < len(rows)}
        fail(404, 'not_found')
    is_pay = re.fullmatch(r'/requests/([^/]+)/pay', path)
    idempotent = path in ('/payments', '/requests', '/splits', '/settlements') or is_pay
    cache_key = None
    if idempotent:
        key = op.get('key')
        if key is None or key == '':
            fail(400, 'missing_idempotency_key')
        if len(key) > 255:
            fail(422, 'validation_failed')
        cache_key = (user, method, path, key)
        parsed = json.dumps(canonical(body), sort_keys=True, ensure_ascii=False)
        if cache_key in s['keys']:
            old_body, old_response = s['keys'][cache_key]
            if parsed != old_body:
                fail(409, 'idempotency_key_reuse')
            return 200, deepcopy(old_response)
    if path == '/payments':
        target = value(body, 'to_handle', str)
        n, memo, vis = amount(body), note(body), visibility(body)
        existing(s, target)
        if target == user:
            fail(422, 'self_payment')
        transfer(s, user, target, n)
        result = make_payment(s, user, target, n, memo, vis)
    elif path == '/requests':
        target = value(body, 'payer_handle', str)
        n, memo = amount(body), note(body)
        existing(s, target)
        if target == user:
            fail(422, 'self_request')
        result = make_request(s, user, target, n, memo)
    elif path == '/splits':
        n, memo = amount(body), note(body)
        participants = value(body, 'participant_handles', list)
        if any(not isinstance(h, str) for h in participants):
            fail(400, 'malformed_request')
        if not participants or len(set(participants)) != len(participants):
            fail(422, 'validation_failed')
        for h in participants:
            existing(s, h)
        split_id = identity(s, 'split')
        when = '@time:' + str(s['serial'])
        shares = [{'handle': h, 'amount': n // len(participants) + (i < n % len(participants))}
                  for i, h in enumerate(participants)]
        requests = [make_request(s, user, share['handle'], share['amount'], memo)
                    for share in shares if share['handle'] != user]
        result = {'split_id': split_id, 'amount': n, 'currency': s['currency'],
                  'note': memo, 'shares': shares, 'requests': requests, 'created_at': when}
    elif path == '/settlements':
        if s['users'][user]['id'] not in s['operators']:
            fail(403, 'forbidden')
        entries = body.get('transfers')
        if not isinstance(entries, list) or not 1 <= len(entries) <= 32:
            fail(422, 'validation_failed')
        validated = []
        for entry in entries:
            if not isinstance(entry, dict):
                fail(422, 'validation_failed')
            sender, recipient = value(entry, 'from_handle', str), value(entry, 'to_handle', str)
            n, memo, vis = amount(entry), note(entry), visibility(entry)
            existing(s, sender)
            existing(s, recipient)
            if sender == recipient:
                fail(422, 'self_payment')
            validated.append((sender, recipient, n, memo, vis))
        balances = {h: u['balance'] for h, u in s['users'].items()}
        for sender, recipient, n, _, _ in validated:
            balances[sender] -= n
            balances[recipient] += n
        if any(n < 0 for n in balances.values()):
            fail(409, 'insufficient_funds')
        for h, n in balances.items():
            s['users'][h]['balance'] = n
        sid = identity(s, 'settlement')
        when = '@time:' + str(s['serial'])
        payments = [make_payment(s, a, b, n, memo, vis, settlement=sid, when=when)
                    for a, b, n, memo, vis in validated]
        result = {'settlement_id': sid, 'committed_at': when, 'payments': payments}
    else:
        action = re.fullmatch(r'/requests/([^/]+)/(pay|decline|cancel)', path)
        if not action:
            fail(404, 'not_found')
        rid, verb = action.groups()
        if verb == 'pay':
            vis = visibility(body)
        r = next((r for r in s['requests'] if r['request_id'] == rid), None)
        if r is None:
            fail(404, 'not_found')
        party = 'requester_handle' if verb == 'cancel' else 'payer_handle'
        if r[party] != user:
            fail(403, 'forbidden')
        if verb == 'pay':
            if r['status'] != 'pending':
                fail(409, 'request_not_pending')
            transfer(s, r['payer_handle'], r['requester_handle'], r['amount'])
            result = make_payment(s, r['payer_handle'], r['requester_handle'], r['amount'], r['note'], vis, request=rid)
            r['status'], r['payment_id'] = 'paid', result['payment_id']
        else:
            target = 'cancelled' if verb == 'cancel' else 'declined'
            if r['status'] not in ('pending', target):
                fail(409, 'request_not_pending')
            r['status'] = target
            return 200, r
    if cache_key is not None:
        s['keys'][cache_key] = (parsed, deepcopy(result))
    return 201, result
