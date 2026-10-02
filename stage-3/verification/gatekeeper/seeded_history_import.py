#!/usr/bin/env python3
"""Every valid seeded terminal/past-expiry hold survives unchanged export."""
import json
import subprocess
import sys
import time
import holds
import probe as p

failures=[]
for status in ['open','expired','voided','captured']:
    authorization={'id':'a_past','from_user_id':'u_a','to_user_id':'u_b','amount':10,
      'note':'','visibility':'private','status':status,'expires_at':'2020-01-01T00:00:00+00:00'}
    users=holds.seed(100,authorizations=[authorization])
    exported=p.call('GET','/_test/export')[1]
    observed,_=p.call('POST','/_test/import',exported)
    print(json.dumps({'seeded_status':status,'expected_import_status':204,'observed_import_status':observed}))
    if observed!=204:
        failures.append(status)
        continue
    holds.wallet(users['a'],100,0)
    code,wallet=p.call('GET','/me?as_of=2021-01-01T00:00:00%2B00:00',token=users['a'])
    p.check(code==200 and wallet['held']==0,'no invented pre-reset terminal hold')
if len(sys.argv)>3:
    target=p.BASE
    image,network=sys.argv[2:4]
    name='gatekeeper-s3-seeded-upgrade-source'
    exports=[]
    try:
        subprocess.run(['docker','run','-d','--name',name,'--network',network,'--cpus','2','--memory','2g',image],stdout=subprocess.DEVNULL,check=True)
        ip=subprocess.check_output(['docker','inspect','--format','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',name],text=True).strip()
        p.BASE='http://'+ip+':8080'
        for _ in range(100):
            try:
                if p.call('GET','/health')[0]==200:break
            except Exception:time.sleep(.05)
        for status in ['open','expired','voided','captured']:
            authorization['status']=status
            users=holds.seed(100,authorizations=[authorization])
            exports.append((status,users,p.call('GET','/_test/export')[1]))
    finally:
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        p.BASE=target
    for status,users,exported in exports:
        observed,_=p.call('POST','/_test/import',exported)
        print(json.dumps({'source_stage':2,'seeded_status':status,'expected_import_status':204,'observed_import_status':observed}))
        if observed!=204:
            failures.append('legacy '+status)
            continue
        holds.wallet(users['a'],100,0)
        upgraded=p.call('GET','/_test/export')[1]
        repeated=p.call('POST','/_test/import',upgraded)[0]
        print(json.dumps({'source_stage':2,'seeded_status':status,'upgraded_reimport_status':repeated}))
        if repeated!=204:failures.append('upgraded '+status)
p.check(not failures,'valid seeded history export imports: '+', '.join(failures))
print(json.dumps({'result':'PASS','assertions':p.COUNT,'cases':8 if len(sys.argv)>3 else 4}))
