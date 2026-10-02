#!/usr/bin/env python3
"""Stage4 authentication, idempotency, parsing, field precedence and privacy."""
import json
import probe as p
import refund_batches as r

t=p.seed(200);payment=r.pay(t)
refund_path='/payments/'+payment['payment_id']+'/refunds'
batch_body={'corrections':[r.item(payment,100)]}
for path,body,token in [(refund_path,{'amount':1},t['b']),('/correction-batches',batch_body,t['c'])]:
 r.expect(p.call('POST',path,body,key='no-token'),401,'unauthenticated')
 for key in [None,'']:r.expect(p.call('POST',path,body,token,key),400,'missing_idempotency_key')
 r.expect(p.call('POST',path,body,token,'x'*256),422,'validation_failed')
 r.expect(p.call('POST',path,body,token,'x'*255),201)
 r.expect(p.call('POST',path,body,token,'x'*255),200)
 r.expect(p.call('POST',path,{},token,'x'*255),409,'idempotency_key_reuse')
r.expect(p.call('POST','/payments/unknown/refunds',{'amount':1},t['b'],'unknown'),404,'not_found')
for body in [{},{'corrections':None},{'corrections':{}},{'corrections':'x'}]:
 r.expect(p.call('POST','/correction-batches',body,t['c'],'shape'),422,'validation_failed')
for field,values in [('amount',[None,True,'1',-1,1.1,1000000001]),('expected_revision',[0,None,True,'1',1.1]),('reason',['',None,True,'x'*201]),('effective_at',['2026-01-01','not-a-date',None])]:
 for value in values:
  entry=r.item(payment,100,2);entry[field]=value
  r.expect(r.batch(t,[entry],key='invalid'),422,'validation_failed')
# Unknown fields affect idempotency equality despite being ignored semantically.
body={'amount':1,'unknown':'first'}
receipt=r.expect(p.call('POST',refund_path,body,t['b'],'unknown-fields'),201)
r.expect(p.call('POST',refund_path,{'unknown':'second','amount':1},t['b'],'unknown-fields'),409,'idempotency_key_reuse')
p.check(r.expect(p.call('POST',refund_path,{'unknown':'first','amount':1},t['b'],'unknown-fields'),200)==receipt,'parsed JSON key order irrelevant')
feed=r.expect(p.call('GET','/activity',token=t['c']),200)['payments']
p.check(not feed,'operator cannot see private original or refund')
for who in ['a','b']:
 feed=r.expect(p.call('GET','/activity',token=t[who]),200)['payments']
 p.check(any(x['payment_id']==receipt['payment_id'] for x in feed),'both parties see private refund')
print(json.dumps({'result':'PASS','assertions':p.COUNT,'new_paths':2}))
