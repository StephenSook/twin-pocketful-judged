#!/usr/bin/env python3
"""Destroy Stage3 source, then preserve receipts, corrections, settlements and snapshots."""
import json,subprocess,sys,time
from urllib.parse import urlencode
import probe as p
import refund_batches as r

target,image,network=sys.argv[1:4];name='gatekeeper-s4-stage3-source'
def docker(*args):return subprocess.check_output(['docker',*args],text=True,stderr=subprocess.DEVNULL).strip()
try:
    docker('run','-d','--name',name,'--network',network,'--cpus','2','--memory','2g',image)
    p.BASE='http://'+docker('inspect','--format','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',name)+':8080'
    for _ in range(100):
        try:
            if p.call('GET','/health')[0]==200:break
        except Exception:time.sleep(.05)
    t=p.seed(200)
    settlement=r.settlement(t)
    payment=r.pay(t,50)
    revision=r.expect(r.single(t,payment,40),201)
    saved=r.frozen(t)
    state=r.expect(p.call('GET','/_test/export'),200)
    docker('rm','-f',name);p.BASE=target
    r.expect(p.call('POST','/_test/import',state),204)
    p.check(r.expect(r.single(t,payment,40),200)==revision,'stage3 original correction replay unchanged')
    p.check(r.expect(p.call('GET','/statement?'+urlencode({'snapshot':saved['snapshot']}),token=t['a']),200)==saved,'stage3 source snapshot unchanged')
    fresh=r.expect(p.call('GET','/payments/'+payment['payment_id']+'/revisions',token=t['a']),200)
    p.check(all(x.get('correction_batch_id','missing') is None for x in fresh['revisions']),'fresh migrated revisions gain nullable batch field')
    r.expect(r.refund(t,payment,41),422,'refund_exceeds_payment')
    r.expect(r.refund(t,payment,10),201)
    r.expect(r.batch(t,[r.item(settlement['payments'][0],0)]),422,'incomplete_settlement')
    r.expect(r.batch(t,[r.item(x,0) for x in settlement['payments']]),201)
    p.check([p.balance(t[x]) for x in 'abc']==[170,30,0],'upgraded money and membership retained')
    exported=r.expect(p.call('GET','/_test/export'),200)
    r.expect(p.call('POST','/_test/import',exported),204)
    p.check(r.expect(p.call('GET','/statement?'+urlencode({'snapshot':saved['snapshot']}),token=t['a']),200)==saved,'old snapshot remains after new stage4 writes and reimport')
    print(json.dumps({'result':'PASS','assertions':p.COUNT,'source_stage':3,'source_destroyed_before_import':True}))
finally:subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
