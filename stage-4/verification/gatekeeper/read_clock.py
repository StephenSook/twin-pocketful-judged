#!/usr/bin/env python3
"""Default read time must follow all previously committed logical events."""
import http.client
import json
from urllib.parse import urlsplit
import holds
import probe as p

tokens=holds.seed(100)
url=urlsplit(p.BASE)
connection=http.client.HTTPConnection(url.hostname,url.port,timeout=5)
headers={'Content-Type':'application/json','Authorization':'Bearer '+tokens['a']}
for i in range(50):
    connection.request('POST','/payments',json.dumps({'to_handle':'b','amount':1}),
        dict(headers,**{'Idempotency-Key':'clock-'+str(i)}))
    response=connection.getresponse();response.read()
    p.check(response.status==201,'rapid sequential payment')
connection.request('GET','/statement?limit=200',headers=headers)
response=connection.getresponse();statement=json.loads(response.read())
count=len(statement.get('entries',[]))
connection.close()
print(json.dumps({'expected_committed_entries':50,'observed_entries':count,
    'expected_closing_balance':50,'observed_closing_balance':statement.get('closing_balance')}))
p.check(response.status==200 and count==50 and statement['closing_balance']==50,
    'default statement read includes all completed writes')
print(json.dumps({'result':'PASS','assertions':p.COUNT}))
