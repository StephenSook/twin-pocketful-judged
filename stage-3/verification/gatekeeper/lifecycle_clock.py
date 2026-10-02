#!/usr/bin/env python3
"""Money/hold creation after void must not be backdated ahead of release."""
import json
import time
from datetime import datetime
from urllib.parse import urlencode
import holds
import probe as p

failures=[]
for kind in ['payment','authorization']:
    tokens=holds.seed(100)
    # Keep the complete short sequence within a wall-clock second on the
    # defective implementation; no product behavior depends on this timing.
    while time.time()%1>.7:time.sleep(.01)
    authorization=holds.hold(tokens,100)
    status,void=p.call('POST','/authorizations/'+authorization['authorization_id']+'/void',{},tokens['a'])
    p.check(status==200,'void releases funds')
    path='/payments' if kind=='payment' else '/authorizations'
    status,created=p.call('POST',path,{'to_handle':'b','amount':100},tokens['a'],'after-void')
    p.check(status==201,'released funds reusable immediately')
    causal=datetime.fromisoformat(created['created_at'])>=datetime.fromisoformat(void['closed_at'])
    status,wallet=p.call('GET','/me?'+urlencode({'as_of':created['created_at']}),token=tokens['a'])
    nonnegative=status==200 and wallet['available']>=0 and wallet['total']>=wallet['held']>=0
    export=p.call('GET','/_test/export')[1]
    import_status,_=p.call('POST','/_test/import',export)
    print(json.dumps({'case':kind+' after void','causal_timestamps':causal,
      'historical_total':wallet['total'],'historical_held':wallet['held'],
      'historical_available':wallet['available'],'own_export_import_status':import_status}))
    if not (causal and nonnegative and import_status==204):failures.append(kind)
p.check(not failures,'lifecycle chronology and portable self-export: '+', '.join(failures))
print(json.dumps({'result':'PASS','assertions':p.COUNT}))
