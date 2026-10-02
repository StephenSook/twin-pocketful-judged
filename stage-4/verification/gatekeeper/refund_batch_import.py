#!/usr/bin/env python3
"""Stage4 invalid export edits must be refused atomically, without logging state."""
from copy import deepcopy
from datetime import datetime,timedelta
import json
import probe as p
import refund_batches as r

t=p.seed(200)
settlement=r.settlement(t)
batch=r.expect(r.batch(t,[r.item(x,50) for x in settlement['payments']]),201)
payment=r.pay(t,50)
refund=r.expect(r.refund(t,payment,10),201)
snapshot=r.expect(p.call('GET','/_test/export'),200)
before=r.expect(p.call('GET','/me',token=t['a']),200)
cases=[]

def edit(name,fn):
    state=deepcopy(snapshot);fn(state['state']);cases.append((name,state))

def refund_record(s):
    return next(x['payment'] for x in s['payments'] if x['payment']['payment_id']==refund['payment_id'])

def revision(s):
    return next(x['revisions'][-1] for x in s['revisions'] if x['payment_id']==settlement['payments'][0]['payment_id'])

edit('refund must copy original note',lambda s:refund_record(s).__setitem__('note','altered'))
edit('refund must copy original visibility',lambda s:refund_record(s).__setitem__('visibility','public'))
edit('refund target cannot be itself',lambda s:refund_record(s).__setitem__('refund_of',refund['payment_id']))
edit('batch recording time must be shared',lambda s:revision(s).__setitem__('recorded_at',(datetime.fromisoformat(revision(s)['recorded_at'])+timedelta(milliseconds=1)).isoformat()))
edit('settlement batch effective instant must be shared',lambda s:revision(s).__setitem__('effective_at',(datetime.fromisoformat(revision(s)['effective_at'])-timedelta(milliseconds=1)).isoformat()))
edit('settlement correction cannot lose batch membership',lambda s:revision(s).__setitem__('correction_batch_id',None))
failures=[]
for name,bad in cases:
    r.expect(p.call('POST','/_test/import',snapshot),204)
    status,body=p.call('POST','/_test/import',bad)
    unchanged=p.call('GET','/me',token=t['a'])[1]==before
    ok=status==422 and body.get('error',{}).get('code')=='validation_failed' and unchanged
    print(json.dumps({'case':name,'expected_status':422,'observed_status':status,'unchanged_wallet':unchanged}))
    if not ok:failures.append(name)
r.expect(p.call('POST','/_test/import',snapshot),204)
print(json.dumps({'result':'FAIL' if failures else 'PASS','assertions':p.COUNT,'failed_cases':failures}))
raise SystemExit(bool(failures))
