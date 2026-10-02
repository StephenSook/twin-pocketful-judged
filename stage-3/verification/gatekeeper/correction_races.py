#!/usr/bin/env python3
"""50-flight mixed histories and atomic export invariants; synthetic state only."""
import concurrent.futures
import json
import threading
from urllib.parse import urlencode
import holds
import probe as p

tokens = holds.seed(1000)
_, payment = p.call('POST','/payments',{'to_handle':'b','amount':100},tokens['a'],'initial')
_, authorization = p.call('POST','/authorizations',{'to_handle':'c','amount':200},tokens['a'],'initial-hold')
_, frozen = p.call('GET','/statement',token=tokens['a'])
snapshot_path = '/statement?'+urlencode({'snapshot':frozen['snapshot']})
gate = threading.Barrier(50)

def inspect(state):
    balances = {u['id']:u['balance'] for u in state['users']}
    expected = {u['user_id']:u['opening'] for u in state['openings']}
    revisions = {r['payment_id']:r['revisions'][-1] for r in state['revisions']}
    payments = {x['payment']['payment_id']:x['payment'] for x in state['payments']}
    for pid, payment in payments.items():
        amount = revisions[pid]['amount']
        expected[payment['from_user_id']] -= amount
        expected[payment['to_user_id']] += amount
    p.check(expected == balances, 'atomic export wallets agree with latest revisions')
    p.check(sum(balances.values()) == 1000, 'atomic export total conserved')
    held = dict.fromkeys(balances,0)
    for row in state['authorizations']:
        a = row['authorization']
        captures = [payments[x] for x in a['payment_ids']]
        p.check(sum(x['amount'] for x in captures) == a['captured_amount'], 'atomic capture history sum')
        p.check(all(x['authorization_id'] == a['authorization_id'] for x in captures), 'capture links consistent')
        p.check(a['captured_amount'] <= a['amount'], 'cumulative capture limit')
        if a['status'] == 'open': held[a['from_user_id']] += a['remaining_amount']
    p.check(all(balances[u] >= held[u] >= 0 for u in balances), 'every atomic snapshot total and available nonnegative')

def operation(i):
    gate.wait()
    if i < 10:
        body={'expected_revision':1,'amount':100+i,'reason':'Concurrent correction','effective_at':payment['created_at']}
        return 'correction',p.call('POST','/payments/'+payment['payment_id']+'/corrections',body,tokens['a'],'corr-'+str(i))
    if i < 20:
        return 'payment',p.call('POST','/payments',{'to_handle':'b','amount':1},tokens['a'],'pay-'+str(i))
    if i < 30:
        return 'hold',p.call('POST','/authorizations',{'to_handle':'c','amount':1},tokens['a'],'hold-'+str(i))
    if i < 40:
        return 'capture',p.call('POST','/authorizations/'+authorization['authorization_id']+'/capture',{'amount':1,'final':False},tokens['c'],'capture-'+str(i))
    if i < 45:
        return 'export',p.call('GET','/_test/export')
    return 'snapshot',p.call('GET',snapshot_path,token=tokens['a'])

with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
    results = list(pool.map(operation,range(50)))
winners = []
for kind,(status,body) in results:
    if kind == 'correction':
        if status == 201:winners.append(body)
        else:p.check(status == 409 and body['error']['code']=='stale_revision','losing correction stale')
    elif kind == 'export':
        p.check(status == 200,'atomic export read succeeds')
        inspect(body['state'])
    elif kind == 'snapshot':
        p.check(status == 200 and body == frozen,'concurrent statement pages frozen')
    else:p.check(status == 201,'mixed write commits')
p.check(len(winners)==1,'one expected-revision winner')
winner = winners[0]['amount']
for h,total,held in [('a',1000-winner-20,200),('b',winner+10,0),('c',10,0)]:
    holds.wallet(tokens[h],total,held)
inspect(p.call('GET','/_test/export')[1]['state'])
p.check(p.call('GET',snapshot_path,token=tokens['a'])[1] == frozen,'snapshot remains frozen after all writes')
print(json.dumps({'result':'PASS','in_flight':50,'assertions':p.COUNT,'atomic_snapshots':6,
    'linearization':'one winning correction plus commuting affordable payments, holds and captures; nine stale corrections after winner'}))
