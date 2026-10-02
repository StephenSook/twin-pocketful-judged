#!/usr/bin/env python3
"""Destroy accepted Stage2 source before importing its live hold/capture state.
Usage: python3 upgrade_holds.py TARGET_URL STAGE2_IMAGE INTERNAL_NETWORK
"""
import json
import subprocess
import sys
import time
from urllib.parse import urlencode
import holds
import probe as p

target, image, network = sys.argv[1:4]
name = 'gatekeeper-s3-stage2-upgrade-source'
def docker(*args):
    return subprocess.check_output(['docker',*args],text=True,stderr=subprocess.DEVNULL).strip()

try:
    docker('run','-d','--name',name,'--network',network,'--cpus','2','--memory','2g',image)
    p.BASE = 'http://'+docker('inspect','--format','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',name)+':8080'
    for _ in range(100):
        try:
            if p.call('GET','/health')[0] == 200:break
        except Exception:time.sleep(.05)
    tokens = holds.seed(1000)
    authorization = holds.hold(tokens,200)
    path = '/authorizations/'+authorization['authorization_id']+'/capture'
    body = {'amount':50,'final':False}
    status, capture = p.call('POST',path,body,tokens['b'],'capture')
    p.check(status==201,'source nonfinal capture')
    pay_body = {'to_handle':'b','amount':10}
    status, payment = p.call('POST','/payments',pay_body,tokens['a'],'payment')
    p.check(status==201,'source payment')
    status, request = p.call('POST','/requests',{'payer_handle':'a','amount':5},tokens['b'],'request')
    p.check(status==201,'source pending request')
    _, source_auths = p.call('GET','/authorizations',token=tokens['a'])
    status, exported = p.call('GET','/_test/export')
    p.check(status==200,'source export')
    docker('rm','-f',name)
    p.BASE = target
    p.check(p.call('POST','/_test/import',exported)[0]==204,'import with source removed')
    holds.wallet(tokens['a'],940,150)
    holds.wallet(tokens['b'],60,0)
    p.check(p.call('POST',path,body,tokens['b'],'capture')==(200,capture),'capture retry unchanged after migration')
    p.check(p.call('POST','/payments',pay_body,tokens['a'],'payment')==(200,payment),'payment retry unchanged after migration')
    auths = p.call('GET','/authorizations',token=tokens['a'])[1]
    current = auths['authorizations'][0]
    p.check(all(current[k]==v for k,v in source_auths['authorizations'][0].items()),'hold fields preserved')
    p.check(current['closed_at'] is None,'open imported hold closed_at null')
    future = '/me?'+urlencode({'as_of':current['expires_at']})
    status, wallet = p.call('GET',future,token=tokens['a'])
    p.check(status==200 and wallet['held']==0 and wallet['available']==940,'imported expiry deadline known')
    correction={'expected_revision':1,'amount':0,'effective_at':capture['created_at'],'reason':'Linked receipt'}
    status,error=p.call('POST','/payments/'+capture['payment_id']+'/corrections',correction,tokens['a'],'immutable')
    p.check(status==422 and error['error']['code']=='linked_payment_immutable','imported capture immutable')
    p.check(p.call('POST','/requests/'+request['request_id']+'/pay',{},tokens['a'],'request-pay')[0]==201,'imported pending request payable')
    holds.wallet(tokens['a'],935,150)
    print(json.dumps({'result':'PASS','assertions':p.COUNT,'source_destroyed_before_import':True,'source_stage':2}))
finally:
    subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
