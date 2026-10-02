#!/usr/bin/env python3
"""5000-payment temporal workload within per-request budgets."""
from datetime import datetime,timedelta,timezone
import json
import time
import probe as p

start = datetime.now(timezone.utc)-timedelta(days=2)
fx={'currency':'EUR','minor_units':2,'users':[
    {'id':h,'handle':h,'email':h+'@x','display_name':h,'password':p.PASSWORD,'balance':5000} for h in ['a','b']],
    'payments':[{'id':'p_'+str(i).zfill(5),'from_user_id':'a' if i%2==0 else 'b',
      'to_user_id':'b' if i%2==0 else 'a','amount':1,'note':'ledger','visibility':'private',
      'created_at':(start+timedelta(seconds=i)).isoformat()} for i in range(5000)]}
t=time.monotonic();p.check(p.call('POST','/_test/reset',fx)[0]==204,'large ledger reset');reset=time.monotonic()-t
token=p.call('POST','/auth/login',{'email':'a@x','password':p.PASSWORD})[1]['token']
def page(_):
    status,body=p.call('GET','/statement?limit=200',token=token)
    p.check(status==200 and len(body['entries'])==200 and body['has_more'],'large statement page')
    p.check(body['opening_balance']==5000 and body['closing_balance']==5000,'large statement window balances')
    return body['snapshot']
snapshots=[]
for _ in range(4):snapshots.extend(p.burst(page))
def correct(i):
    status,body=p.call('POST','/payments/p_'+str(i*2).zfill(5)+'/corrections',{
      'expected_revision':1,'amount':2,'reason':'Scale test','effective_at':fx['payments'][i*2]['created_at']},token,'corr-'+str(i))
    p.check(status==201,'large ledger correction')
p.burst(correct)
p.check(p.call('GET','/me',token=token)[1]['total']==4950,'large corrected current balance')
for snapshot in snapshots[::20]:
    body=p.call('GET','/statement?snapshot='+snapshot+'&limit=200',token=token)[1]
    p.check(body['closing_balance']==5000 and body['entries'][0]['delta']==-1,'large snapshot frozen')
t=time.monotonic();status,export=p.call('GET','/_test/export');export_seconds=time.monotonic()-t
p.check(status==200,'large export')
t=time.monotonic();p.check(p.call('POST','/_test/import',export)[0]==204,'large temporal import');import_seconds=time.monotonic()-t
p.check(p.call('GET','/me',token=token)[1]['total']==4950,'large imported balance')
print(json.dumps({'result':'PASS','payments':5000,'statement_snapshots':200,'corrections':50,'assertions':p.COUNT,
 'reset_seconds':round(reset,4),'export_seconds':round(export_seconds,4),'import_seconds':round(import_seconds,4),'max_request_seconds':round(p.MAX_LATENCY,4)}))
