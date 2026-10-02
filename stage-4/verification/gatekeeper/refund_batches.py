#!/usr/bin/env python3
"""Independent stage-4 semantics, precedence and 50-flight histories.
Usage: python3 refund_batches.py URL. Never logs credentials or snapshots.
"""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import probe as p
import history

def expect(result,status,code=None):
    s,b=result
    p.check(s==status and (code is None or b.get('error',{}).get('code')==code),
            'expected '+str(status)+' '+str(code)+' observed '+str(s)+' '+str(b.get('error',{}).get('code') if isinstance(b,dict) else None))
    return b

def pay(t,amount=100):
    return expect(p.call('POST','/payments',{'to_handle':'b','amount':amount,'note':' original 🪙 ','visibility':'private'},t['a'],'pay'),201)

def refund(t,payment,amount,key='refund',actor='b'):
    return p.call('POST','/payments/'+payment['payment_id']+'/refunds',{'amount':amount},t[actor],key)

def item(payment,amount,revision=1):
    return {'payment_id':payment['payment_id'],'expected_revision':revision,'amount':amount,
            'effective_at':payment['created_at'],'reason':'Adjusted history'}

def single(t,payment,amount,revision=1,key='single'):
    body=item(payment,amount,revision);body.pop('payment_id')
    return p.call('POST','/payments/'+payment['payment_id']+'/corrections',body,t['a'],key)

def batch(t,items,key='batch',actor='c'):
    return p.call('POST','/correction-batches',{'corrections':items},t[actor],key)

def frozen(t):
    return expect(p.call('GET','/statement',token=t['a']),200)

def refund_semantics():
    t=p.seed(200);payment=pay(t)
    p.check(payment.get('refund_of','missing') is None,'ordinary payment refund_of null')
    before=frozen(t)
    expect(refund(t,payment,1,actor='a'),403,'forbidden')
    expect(refund(t,payment,1,actor='c'),403,'forbidden')
    for amount in [0,-1,True,None,'2',1.5,1000000001]:
        expect(refund(t,payment,amount),422,'validation_failed')
    expect(refund(t,payment,101),422,'refund_exceeds_payment')
    receipt=expect(refund(t,payment,30),201)
    p.check(receipt['refund_of']==payment['payment_id'] and receipt['from_user_id']=='u_b' and receipt['to_user_id']=='u_a','refund direction and link')
    p.check(receipt['note']==payment['note'] and receipt['visibility']==payment['visibility'] and receipt['request_id'] is None and receipt['authorization_id'] is None,'refund receipt inherited fields')
    p.check([p.balance(t[x]) for x in 'abc']==[130,70,0],'refund moves only amount')
    expect(refund(t,payment,71,key='cap'),422,'refund_exceeds_payment')
    expect(refund(t,receipt,1,actor='a',key='nested'),422,'invalid_refund_target')
    body=item(receipt,0);body.pop('payment_id')
    expect(p.call('POST','/payments/'+receipt['payment_id']+'/corrections',body,t['b'],'immutable'),422,'linked_payment_immutable')
    expect(batch(t,[item(receipt,0)],key='immutable-batch'),422,'linked_payment_immutable')
    expect(single(t,payment,29),422,'refund_exceeds_payment')
    revision=expect(single(t,payment,60),201)
    p.check(revision.get('correction_batch_id','missing') is None,'single correction batch id null')
    expect(refund(t,payment,31,key='corrected-cap'),422,'refund_exceeds_payment')
    expect(refund(t,payment,30,key='corrected-cap'),201)
    p.check([p.balance(t[x]) for x in 'abc']==[200,0,0],'refund cap uses corrected amount')
    p.check(expect(refund(t,payment,30),200)==receipt,'original refund retry unchanged after correction')
    expect(refund(t,payment,None),409,'idempotency_key_reuse')
    p.check(expect(p.call('POST','/payments',{'to_handle':'b','amount':100,'note':' original 🪙 ','visibility':'private'},t['a'],'pay'),200)==payment,'original payment replay unchanged')
    p.check(expect(p.call('GET','/statement?'+urlencode({'snapshot':before['snapshot']}),token=t['a']),200)==before,'snapshot unchanged by refunds/correction')
    revs=expect(p.call('GET','/payments/'+payment['payment_id']+'/revisions',token=t['a']),200)['revisions']
    p.check(all(r.get('correction_batch_id','missing') is None for r in revs),'all unbatched revisions include null')
    t=p.seed(100);payment=pay(t)
    expect(p.call('POST','/authorizations',{'to_handle':'c','amount':90},t['b'],'held'),201)
    expect(refund(t,payment,11),409,'insufficient_funds')
    expect(refund(t,payment,10),201)

def settlement(t):
    return expect(p.call('POST','/settlements',{'transfers':[{'from_handle':'a','to_handle':'b','amount':100},
         {'from_handle':'b','to_handle':'a','amount':100}]},t['c'],'settle'),201)

def batch_semantics():
    t=p.seed(100);s=settlement(t);a,b=s['payments'];before=frozen(t)
    expect(single(t,a,0),422,'linked_payment_immutable')
    expect(batch(t,[item(a,0)],actor='a'),403,'forbidden')
    expect(batch(t,[item(a,0)]),422,'incomplete_settlement')
    mismatch=item(b,0);mismatch['effective_at']=(datetime.fromisoformat(b['created_at'])-timedelta(seconds=1)).isoformat()
    expect(batch(t,[item(a,0),mismatch]),422,'validation_failed')
    equivalent=item(b,0);equivalent['effective_at']=datetime.fromisoformat(b['created_at']).astimezone(timezone(timedelta(hours=2))).isoformat()
    request=[item(a,0),equivalent]
    result=expect(batch(t,request),201)
    p.check([r['payment_id'] for r in result['revisions']]==[a['payment_id'],b['payment_id']],'batch preserves input order')
    p.check(all(r['recorded_at']==result['recorded_at'] and r['correction_batch_id']==result['correction_batch_id'] for r in result['revisions']),'shared recording and batch identity')
    p.check(all(datetime.fromisoformat(result['recorded_at'])>datetime.fromisoformat(x['created_at']) for x in (a,b)),'recording strictly after every member')
    p.check([p.balance(t[x]) for x in 'abc']==[100,0,0],'combined affordability allows net zero reversal')
    p.check(expect(batch(t,request),200)==result,'batch exact replay')
    expect(batch(t,[]),409,'idempotency_key_reuse')
    p.check(expect(p.call('GET','/statement?'+urlencode({'snapshot':before['snapshot']}),token=t['a']),200)==before,'settlement snapshot frozen')
    expect(batch(t,request,key='stale'),409,'stale_revision')
    saved=expect(p.call('GET','/_test/export'),200)
    p.seed(3);expect(p.call('POST','/_test/import',saved),204)
    p.check(expect(batch(t,request),200)==result,'batch replay preserved by import')
    p.check(expect(p.call('GET','/statement?'+urlencode({'snapshot':before['snapshot']}),token=t['a']),200)==before,'snapshot preserved by import')
    # Input-order errors must win before completeness, current funds, or history.
    t=history.seed()
    first={'payment_id':'p_one','expected_revision':2,'amount':30,'effective_at':history.T1,'reason':'stale'}
    missing={**first,'payment_id':'missing','expected_revision':1}
    expect(batch(t,[first,missing]),409,'stale_revision')
    expect(batch(t,[missing,first]),404,'not_found')
    for values in [[],[first]*2,[missing]*33,[None]]:
        expect(batch(t,values),422,'validation_failed')
    # b has only 20 now, but receives 20 while returning 40 in the same batch.
    two={'payment_id':'p_two','expected_revision':1,'amount':0,'effective_at':history.T2,'reason':'reverse'}
    one={**first,'expected_revision':1,'amount':0}
    result=expect(batch(t,[one,two]),201)
    p.check([p.balance(t[x]) for x in 'abc']==[100,0,0],'ordinary batch combined funds')

def races():
    t=p.seed(100);payment=pay(t)
    results=p.burst(lambda i:refund(t,payment,3,key='cap-'+str(i)))
    p.check(sum(s==201 for s,_ in results)==33,'50 refunds admit exactly floor(cap/amount)')
    p.check(all(s==201 or (s==422 and b['error']['code']=='refund_exceeds_payment') for s,b in results),'cap losers deterministic')
    p.check([p.balance(t[x]) for x in 'abc']==[99,1,0],'concurrent refund conservation')
    t=p.seed(100);payment=pay(t)
    results=p.burst(lambda i:refund(t,payment,25,key='identical'))
    p.check(sum(s==201 for s,_ in results)==1 and sum(s==200 for s,_ in results)==49,'refund identical key one commit')
    p.check(all(b==results[0][1] for _,b in results),'refund replay bodies equal')
    t=p.seed(100);payment=pay(t,50)
    results=p.burst(lambda i:single(t,payment,40,key='single-'+str(i)) if i%2 else batch(t,[item(payment,30)],key='batch-'+str(i)))
    p.check(sum(s==201 for s,_ in results)==1,'single versus batch one shared revision winner')
    p.check(all(s==201 or (s==409 and b['error']['code']=='stale_revision') for s,b in results),'all shared-revision losers stale')
    winner=[b for s,b in results if s==201][0];amount=winner['revisions'][0]['amount'] if 'revisions' in winner else winner['amount']
    p.check([p.balance(t[x]) for x in 'abc']==[100-amount,amount,0],'winning revision explains wallets')
    t=p.seed(100);s=settlement(t);request=[item(x,0) for x in s['payments']]
    results=p.burst(lambda i:batch(t,request,key='identical'))
    p.check(sum(s==201 for s,_ in results)==1 and sum(s==200 for s,_ in results)==49,'batch identical key one commit')
    p.check(all(b==results[0][1] for _,b in results),'batch replay bodies equal')

if __name__=='__main__':
    try:
        refund_semantics();batch_semantics();races()
        print(json.dumps({'result':'PASS','assertions':p.COUNT,'concurrency':50,'max_request_seconds':round(p.MAX_LATENCY,4)}))
    except Exception as exc:
        print(json.dumps({'result':'FAIL','assertions':p.COUNT,'check':str(exc) if isinstance(exc,AssertionError) else type(exc).__name__}));raise SystemExit(1)
