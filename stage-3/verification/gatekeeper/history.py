#!/usr/bin/env python3
"""Independent Stage3 effective/recorded history, snapshot and correction checks.
Usage: python3 history.py URL. Synthetic credentials and snapshots never logged.
"""
import json
import threading
import time
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode
import probe as p

NOW=datetime.now(timezone.utc).replace(microsecond=0)
T0=(NOW-timedelta(days=4)).isoformat()
T1=(NOW-timedelta(days=3)).isoformat()
T2=(NOW-timedelta(days=2)).isoformat()
T3=(NOW-timedelta(days=1)).isoformat()

def seed():
    fx={'currency':'EUR','minor_units':2,'settlement_operator_ids':['u_c'],
        'users':[{'id':'u_'+h,'email':h+'@example.test','password':p.PASSWORD,'display_name':h,'handle':h,'balance':balance} for h,balance in [('a',60),('b',20),('c',20)]],
        'payments':[{'id':'p_one','from_user_id':'u_a','to_user_id':'u_b','amount':40,'note':'original one','visibility':'public','created_at':T1},
                    {'id':'p_two','from_user_id':'u_b','to_user_id':'u_c','amount':20,'note':'original two','visibility':'private','created_at':T2}],
        'requests':[]}
    p.check(p.call('POST','/_test/reset',fx)[0]==204,'history reset')
    return {h:p.call('POST','/auth/login',{'email':h+'@example.test','password':p.PASSWORD})[1]['token'] for h in ['a','b','c']}

def get(path,token,**query):
    return p.call('GET',path+('?' + urlencode(query) if query else ''),token=token)

def correction(token,pid='p_one',revision=1,amount=30,effective=T1,key='correction'):
    body={'expected_revision':revision,'amount':amount,'effective_at':effective,'reason':'Corrected history'}
    return p.call('POST','/payments/'+pid+'/corrections',body,token,key)

def balances(tokens,expected,**query):
    values=[]
    for h in ['a','b','c']:
        status,me=get('/me',tokens[h],**query)
        p.check(status==200 and me['balance']==me['total'] and me['available']==me['total']-me['held']>=0,'historical wallet fields coherent')
        for name,value in query.items():p.check(me[name]==value,'temporal echo exact')
        values.append(me['balance'])
    p.check(values==expected,'historical balances expected')
    p.check(sum(values)==100,'historical total conserved')

def semantics():
    tokens=seed()
    balances(tokens,[100,0,0],as_of=T0)
    balances(tokens,[60,40,0],as_of=T1)
    balances(tokens,[60,20,20],as_of=T2)
    balances(tokens,[60,40,0],as_of=T3,known_at=T1)
    original=p.call('GET','/activity',token=tokens['a'])[1]
    status,snapshot=get('/statement',tokens['b'],**{'from':T0,'to':T3,'limit':1})
    p.check(status==200 and snapshot['opening_balance']==0 and snapshot['closing_balance']==20 and snapshot['has_more'],'full-window balances independent of page')
    p.check(snapshot['entries'][0]['delta']==40 and snapshot['entries'][0]['balance_after']==40,'statement first entry balance')
    status,rev=correction(tokens['a'])
    p.check(status==201 and rev['revision']==2 and rev['amount']==30,'correction appends revision')
    balances(tokens,[70,10,20])
    p.check(p.call('GET','/activity',token=tokens['a'])[1]==original,'original activity unchanged')
    status,st=get('/statement',tokens['b'],**{'from':T0,'to':T3})
    p.check(status==200 and st['opening_balance']==0 and st['closing_balance']==10,'corrected full window')
    p.check([e['delta'] for e in st['entries']]==[30,-20] and [e['balance_after'] for e in st['entries']]==[30,10],'selected revisions replace originals')
    p.check(st['entries'][0]['payment']['amount']==30 and st['entries'][0]['revision']==2,'statement payment amount selected')
    status,page=get('/statement',tokens['b'],snapshot=snapshot['snapshot'],limit=1,offset=1)
    p.check(status==200 and page['opening_balance']==0 and page['closing_balance']==20 and page['entries'][0]['balance_after']==20 and not page['has_more'],'snapshot frozen after correction')
    p.check(get('/statement',tokens['a'],snapshot=snapshot['snapshot'])[0]==404,'snapshot bound to user')
    for name in ['from','to','known_at']:
        p.check(get('/statement',tokens['b'],snapshot=snapshot['snapshot'],**{name:T1})[0]==422,'snapshot excludes temporal fields')
    status,last=get('/statement',tokens['b'],snapshot=snapshot['snapshot'],offset=99,ignored='anything')
    p.check(status==200 and last['entries']==[] and not last['has_more'] and last['closing_balance']==20,'snapshot beyond end and unknown parameter')
    status,err=correction(tokens['a'],revision=2,amount=30,effective=T3,key='historical-failure')
    p.check(status==409 and err['error']['code']=='historical_overdraft','future-effective funding removal rejected')
    status,err=correction(tokens['a'],revision=2,amount=10,key='current-failure')
    p.check(status==409 and err['error']['code']=='insufficient_funds','current debit failure precedes history')
    p.check(correction(tokens['a'],revision=1,key='stale')[0]==409,'stale expected revision')
    p.check(correction(tokens['b'],key='wrong-sender')[0]==403,'receiver cannot correct sender payment')
    p.check(get('/payments/p_one/revisions',tokens['c'])[0]==404,'public receipt revisions private to parties')
    p.check(get('/payments/p_one/revisions',tokens['b'])[0]==200,'receiver may read revisions')
    status,revs=get('/payments/p_one/revisions',tokens['a'])
    p.check([r['revision'] for r in revs['revisions']]==[1,2] and revs['revisions'][0]['reason']=='','failed corrections leave history untouched')
    status,zero=correction(tokens['b'],pid='p_two',amount=0,key='reverse-two')
    p.check(status==201,'zero reversal')
    balances(tokens,[70,30,0])
    status,new=correction(tokens['a'],revision=2,amount=0,key='reverse-one')
    p.check(status==201 and datetime.fromisoformat(new['recorded_at'].replace('Z','+00:00'))>datetime.fromisoformat(rev['recorded_at'].replace('Z','+00:00')),'recorded times strictly increase')
    balances(tokens,[100,0,0])
    status,replay=correction(tokens['a'])
    p.check(status==200 and replay==rev,'older successful correction replay immutable')
    st=get('/statement',tokens['b'],**{'from':T0,'to':T3})[1]
    p.check(len(st['entries'])==2 and all(e['delta']==0 for e in st['entries']),'zero revisions retained once')
    old=snapshot['snapshot'];seed()
    p.check(get('/statement',p.call('POST','/auth/login',{'email':'b@example.test','password':p.PASSWORD})[1]['token'],snapshot=old)[0]==404,'reset invalidates snapshot')

def validation():
    tokens=seed()
    for path,key in [('/me','as_of'),('/me','known_at'),('/statement','from'),('/statement','to')]:
        status,value=p.call('GET',path+'?'+key+'='+T1,token=tokens['a'])
        p.check(status==200,'raw plus offset accepted under S3-2')
        if path=='/me':p.check(value[key]==T1,'raw plus temporal echo restored')
    invalid=['','2026-01-01','2026-01-01T12:00:00','2026-02-30T12:00:00+00:00','not-a-date']
    for value in invalid:
        for key in ['as_of','known_at']:p.check(get('/me',tokens['a'],**{key:value})[0]==422,'invalid temporal instant422')
    future=(NOW+timedelta(days=1)).isoformat()
    for field,values in [('amount',[None,True,'30',-1,1000000001,1.5]),('expected_revision',[None,True,'1',0,1.5]),('reason',[None,False,'','x'*201]),('effective_at',[None,*invalid,future])]:
        for value in values:
            body={'expected_revision':1,'amount':30,'effective_at':T1,'reason':'Correction'};body[field]=value
            status,error=p.call('POST','/payments/p_one/corrections',body,tokens['a'],'bad')
            p.check(status==422 and error['error']['code']=='validation_failed','all invalid correction fields422')

def races():
    tokens=seed()
    results=p.burst(lambda i:correction(tokens['a'],amount=30+i%10,key='race-'+str(i)))
    p.check(sum(s==201 for s,_ in results)==1,'one correction wins same expected revision')
    p.check(all(s==201 or (s==409 and v['error']['code']=='stale_revision') for s,v in results),'all correction losers stale')
    revs=get('/payments/p_one/revisions',tokens['a'])[1]['revisions']
    p.check(len(revs)==2,'race appends once')
    tokens=seed()
    results=p.burst(lambda i:correction(tokens['a'],key='identical'))
    p.check(sum(s==201 for s,_ in results)==1 and sum(s==200 for s,_ in results)==49,'50identical correction retries')
    p.check(all(value==results[0][1] for _,value in results),'concurrent correction replay identical')
    original=get('/statement',tokens['a'],**{'from':T0,'to':T3})[1]
    snap=original['snapshot']
    def concurrent(i):
        if i%2:
            return p.call('POST','/payments',{'to_handle':'b','amount':1},tokens['a'],'snapshot-write-'+str(i))
        status,page=get('/statement',tokens['a'],snapshot=snap)
        p.check(status==200 and page==original,'snapshot immutable during concurrent writes')
        return status,page
    results=p.burst(concurrent)
    p.check(all(s in [200,201] for s,_ in results),'snapshot/write race statuses')

def snapshot_import():
    source=seed()
    status,frozen=get('/statement',source['b'],**{'from':T0,'to':T3,'limit':1})
    p.check(status==200,'source snapshot before export')
    status,export=p.call('GET','/_test/export')
    p.check(status==200,'snapshot state export')
    destination=seed()
    _,discarded=get('/statement',destination['b'])
    p.check(p.call('POST','/_test/import',export)[0]==204,'import snapshot state replacement')
    status,restored=get('/statement',source['b'],snapshot=frozen['snapshot'],limit=1)
    p.check(status==200 and restored==frozen,'source snapshot token survives import exactly')
    p.check(get('/statement',source['b'],snapshot=discarded['snapshot'])[0]==404,'destination-only snapshot removed by import')
    p.check(get('/me',destination['b'])[0]==401,'destination session removed by import')

if __name__=='__main__':
    try:
        semantics();validation();races();snapshot_import()
        print(json.dumps({'result':'PASS','assertions':p.COUNT,'max_request_seconds':round(p.MAX_LATENCY,4)}))
    except Exception as exc:
        print(json.dumps({'result':'FAIL','assertions':p.COUNT,'check':str(exc) if isinstance(exc,AssertionError) else type(exc).__name__}));raise SystemExit(1)
