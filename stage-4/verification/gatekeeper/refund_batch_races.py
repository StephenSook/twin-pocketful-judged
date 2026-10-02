#!/usr/bin/env python3
"""Mixed 50-flight refunds, shared-revision corrections, snapshots and atomic reads."""
import json
from urllib.parse import urlencode
import probe as p
import refund_batches as r

t=p.seed(200);payment=r.pay(t);frozen=r.frozen(t)
snapshot_path='/statement?'+urlencode({'snapshot':frozen['snapshot']})

def inspect(state):
    wallets={u['id']:u['balance'] for u in state['users']}
    expected={u['user_id']:u['opening'] for u in state['openings']}
    latest={x['payment_id']:x['revisions'][-1] for x in state['revisions']}
    refunded={}
    for row in state['payments']:
        pay=row['payment'];amount=latest[pay['payment_id']]['amount']
        expected[pay['from_user_id']]-=amount;expected[pay['to_user_id']]+=amount
        if pay['refund_of']:
            refunded[pay['refund_of']]=refunded.get(pay['refund_of'],0)+pay['amount']
    p.check(expected==wallets and sum(wallets.values())==200,'atomic wallets equal revision sum and conserve money')
    p.check(all(v>=0 for v in wallets.values()),'atomic wallets nonnegative')
    p.check(all(v<=latest[k]['amount'] for k,v in refunded.items()),'atomic cumulative refund cap')
    for row in state['authorizations']:
        a=row['authorization']
        if a['status']=='open':wallets[a['from_user_id']]-=a['remaining_amount']
    p.check(all(v>=0 for v in wallets.values()),'atomic available nonnegative')

def operation(i):
    if i<15:return 'refund',r.refund(t,payment,2,key='r-'+str(i))
    if i<30:return 'single',r.single(t,payment,90,key='s-'+str(i))
    if i<40:return 'batch',r.batch(t,[r.item(payment,90)],key='b-'+str(i))
    if i<45:return 'export',p.call('GET','/_test/export')
    return 'snapshot',p.call('GET',snapshot_path,token=t['a'])

results=p.burst(operation)
winners=0
for kind,(status,body) in results:
    if kind in ('single','batch'):
        if status==201:winners+=1
        else:p.check(status==409 and body['error']['code']=='stale_revision','overlapping revision loser stale')
    elif kind=='refund':p.check(status==201,'commuting affordable refund commits')
    elif kind=='export':
        p.check(status==200,'atomic snapshot read succeeds');inspect(body['state'])
    else:p.check(status==200 and body==frozen,'saved statement immutable during writes')
p.check(winners==1,'one single/batch correction winner')
p.check([p.balance(t[x]) for x in 'abc']==[140,60,0],'serial witness one decrease10 and fifteen refunds2')
inspect(r.expect(p.call('GET','/_test/export'),200)['state'])
print(json.dumps({'result':'PASS','assertions':p.COUNT,'concurrency':50,'atomic_snapshots':6,
 'linearization':'one correction, 24 stale conflicts, fifteen commuting refunds; atomic reads satisfy revision/cap/available invariants'}))
