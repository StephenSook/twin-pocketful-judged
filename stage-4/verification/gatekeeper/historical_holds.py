#!/usr/bin/env python3
"""Historical available-funds boundaries and immutable linked movements."""
import json,time
from datetime import datetime,timedelta,timezone
import history as h
p=h.p

def instant(value):return datetime.fromisoformat(value.replace('Z','+00:00'))

def read(token,total,held,**query):
    status,me=h.get('/me',token,**query)
    p.check(status==200 and (me['total'],me['balance'],me['held'],me['available'])==(total,total,held,total-held),'historical hold wallet coherent')

def boundaries():
    tokens=h.seed()
    _,auth=p.call('POST','/authorizations',{'to_handle':'c','amount':60},tokens['a'],'history-hold')
    aid=auth['authorization_id'];created=auth['created_at']
    p.check(auth['closed_at'] is None,'open authorization closed_at null')
    read(tokens['a'],60,60,as_of=created)
    read(tokens['a'],60,0,as_of=(instant(created)-timedelta(seconds=1)).isoformat())
    status,err=h.correction(tokens['a'],amount=50,key='overdraft-scope')
    p.check(status==409 and err['error']['code']=='insufficient_funds','current available debit failure precedes history')
    time.sleep(max(0,instant(created).timestamp()+1.1-time.time()))
    status,voided=p.call('POST','/authorizations/'+aid+'/void',{},tokens['a'])
    p.check(status==200 and voided['closed_at'] is not None,'void has event timestamp')
    read(tokens['a'],60,0)
    read(tokens['a'],60,60,as_of=created)
    read(tokens['a'],60,0,as_of=voided['closed_at'])
    read(tokens['a'],60,60,as_of=voided['closed_at'],known_at=created)
    status,err=h.correction(tokens['a'],amount=50,key='overdraft-scope')
    p.check(status==409 and err['error']['code']=='historical_overdraft','past held funds reject otherwise affordable correction')
    p.check(len(h.get('/payments/p_one/revisions',tokens['a'])[1]['revisions'])==1,'historical rejection adds no revision')
    status,revision=h.correction(tokens['a'],amount=30,key='overdraft-scope')
    p.check(status==201,'failed key remains reusable')
    read(tokens['a'],70,60,as_of=created)
    read(tokens['a'],70,0)

def linked():
    tokens=h.seed()
    _,settlement=p.call('POST','/settlements',{'transfers':[{'from_handle':'a','to_handle':'b','amount':1},{'from_handle':'b','to_handle':'a','amount':1}]},tokens['c'],'linked-settlement')
    for payment in settlement['payments']:
        sender=tokens['a'] if payment['from_handle']=='a' else tokens['b']
        status,err=h.correction(sender,pid=payment['payment_id'],amount=0,key='linked-'+payment['payment_id'])
        p.check(status==422 and err['error']['code']=='linked_payment_immutable','settlement members immutable')
        revs=h.get('/payments/'+payment['payment_id']+'/revisions',sender)[1]['revisions']
        p.check(len(revs)==1 and revs[0]['effective_at']==settlement['committed_at'] and revs[0]['recorded_at']==settlement['committed_at'],'settlement original revision time shared')
    _,auth=p.call('POST','/authorizations',{'to_handle':'b','amount':20},tokens['a'],'linked-hold')
    _,capture=p.call('POST','/authorizations/'+auth['authorization_id']+'/capture',{'amount':5,'final':False},tokens['b'],'linked-capture')
    status,err=h.correction(tokens['a'],pid=capture['payment_id'],amount=0,key='linked-correction')
    p.check(status==422 and err['error']['code']=='linked_payment_immutable','captures immutable')
    _,statement=h.get('/statement',tokens['a'],to=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    p.check(sum(e['payment']['payment_id']==capture['payment_id'] for e in statement['entries'])==1,'capture counted once in statement')
    p.check(len(statement['entries'])==4,'no hold/release statement entries')

if __name__=='__main__':
    try:
        boundaries();linked()
        print(json.dumps({'result':'PASS','assertions':p.COUNT,'max_request_seconds':round(p.MAX_LATENCY,4)}))
    except Exception as exc:
        print(json.dumps({'result':'FAIL','assertions':p.COUNT,'check':str(exc) if isinstance(exc,AssertionError) else type(exc).__name__}));raise SystemExit(1)
