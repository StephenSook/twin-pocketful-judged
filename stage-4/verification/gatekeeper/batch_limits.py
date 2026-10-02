#!/usr/bin/env python3
"""50 concurrent maximum-size batches against a 5000-payment ledger."""
import json,time
import probe as p
import refund_batches as r

fixture={'currency':'EUR','minor_units':2,'settlement_operator_ids':['u_c'],
 'users':[{'id':'u_'+h,'handle':h,'email':h+'@example.test','display_name':h,'password':p.PASSWORD,'balance':5000 if h!='c' else 0} for h in 'abc'],
 'payments':[{'id':'p_'+str(i).zfill(5),'from_user_id':'u_a','to_user_id':'u_b','amount':1,'note':'','visibility':'private','created_at':'2020-01-01T00:00:00+00:00'} for i in range(5000)]}
start=time.monotonic();r.expect(p.call('POST','/_test/reset',fixture),204);reset=time.monotonic()-start
t={h:r.expect(p.call('POST','/auth/login',{'email':h+'@example.test','password':p.PASSWORD}),200)['token'] for h in 'abc'}
def items(index):
 return [{'payment_id':'p_'+str(i).zfill(5),'expected_revision':1,'amount':2,'reason':'Maximum batch','effective_at':'2020-01-01T00:00:00+00:00'} for i in range(index*32,(index+1)*32)]
results=p.burst(lambda i:r.batch(t,items(i),key='max-'+str(i)))
for status,body in results:
 p.check(status==201 and len(body['revisions'])==32,'maximum-size batch succeeds within timeout')
 p.check(all(x['recorded_at']==body['recorded_at'] and x['correction_batch_id']==body['correction_batch_id'] for x in body['revisions']),'all32 revisions share recording and identity')
p.check([p.balance(t[x]) for x in 'abc']==[3400,6600,0],'1600 net increases exact')
results=p.burst(lambda i:r.refund(t,{'payment_id':'p_'+str(i).zfill(5)},1,key='refund-'+str(i)))
p.check(all(s==201 for s,_ in results),'50 corrected-payment refunds succeed')
p.check([p.balance(t[x]) for x in 'abc']==[3450,6550,0],'refunds conserve large ledger')
start=time.monotonic();snapshot=r.expect(p.call('GET','/_test/export'),200);export=time.monotonic()-start
start=time.monotonic();r.expect(p.call('POST','/_test/import',snapshot),204);imported=time.monotonic()-start
p.check([p.balance(t[x]) for x in 'abc']==[3450,6550,0],'large batch/refund state roundtrip')
print(json.dumps({'result':'PASS','assertions':p.COUNT,'payments':5050,'batch_size':32,'concurrency':50,
 'reset_seconds':round(reset,4),'export_seconds':round(export,4),'import_seconds':round(imported,4),'max_request_seconds':round(p.MAX_LATENCY,4)}))
