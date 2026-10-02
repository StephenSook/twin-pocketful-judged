#!/usr/bin/env python3
"""Malformed temporal export state cannot replace a valid destination."""
from copy import deepcopy
import json
import holds
import probe as p

users = holds.seed(100)
authorization = holds.hold(users,20)
status, payment = p.call('POST','/authorizations/'+authorization['authorization_id']+'/capture',
    {'amount':5,'final':False},users['b'],'partial')
p.check(status == 201,'import fixture partial capture')
_, snapshot = p.call('GET','/_test/export')
_, before = p.call('GET','/me',token=users['a'])
cases = []
bad = deepcopy(snapshot)
bad['state']['openings'][0]['opening'] = -1
cases.append(('negative opening',bad))
bad = deepcopy(snapshot)
bad['state']['openings'][0]['opening'] = 99
cases.append(('opening disagrees with current ledger',bad))
bad = deepcopy(snapshot)
bad['state']['auth_events'][0]['initialHold'] = -1
cases.append(('negative initial historical hold',bad))
bad = deepcopy(snapshot)
bad['state']['auth_events'][0]['captures'][0]['amount'] = -5
cases.append(('negative historical capture',bad))
bad = deepcopy(snapshot)
bad['state']['revisions'][0]['revisions'][0]['recorded_at'] = '2020-01-01T00:00:00+00:00'
cases.append(('original recorded time differs from created time',bad))
failures = []
for name,bad in cases:
    p.check(p.call('POST','/_test/import',snapshot)[0]==204,'valid export accepted')
    status,body = p.call('POST','/_test/import',bad)
    unchanged = p.call('GET','/me',token=users['a'])[1] == before
    ok = status == 422 and (body or {}).get('error',{}).get('code') == 'validation_failed' and unchanged
    print(json.dumps({'case':name,'expected_status':422,'observed_status':status,'unchanged_current_wallet':unchanged}))
    if not ok:failures.append(name)
p.check(not failures,'invalid temporal import rejected atomically: '+', '.join(failures))
print(json.dumps({'result':'PASS','assertions':p.COUNT}))
