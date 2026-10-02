#!/usr/bin/env python3
"""Stage3 temporal HTTP differential checks; standard library, isolated services only."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
from pathlib import Path
import random
import tempfile
import time
import urllib.parse

from driver import http, require, Mismatch, FIXTURE
import temporal_model as model

T0='2020-01-01T00:00:00+00:00'
T1='2020-01-02T00:00:00+00:00'
T2='2020-01-03T00:00:00+00:00'
T3='2020-01-04T00:00:00+00:00'
T4='2020-01-05T00:00:00+00:00'
T5='2020-01-06T00:00:00+00:00'
FUTURE='2099-01-01T00:00:00+00:00'


def now():
    return datetime.now(timezone.utc).isoformat()


def fixture():
    f=deepcopy(FIXTURE)
    balances={'ada':700,'bob':200,'cy':100,'dee':1000}
    for u in f['users']:u['balance']=balances[u['handle']]
    f['requests']=[]
    f['payments']=[{'id':pid,'from_user_id':'u_'+a,'to_user_id':'u_'+b,'amount':n,
        'note':pid,'visibility':vis,'created_at':t} for pid,a,b,n,t,vis in [
        ('p_a','ada','bob',400,T1,'public'),('p_b','bob','cy',200,T2,'private'),
        ('p_c','cy','ada',100,T3,'public')]]
    return f


def matches(expected,actual,label='temporal'):
    if isinstance(expected,dict):
        require(isinstance(actual,dict),label+' object')
        for k,v in expected.items():
            require(k in actual,label+'.'+k+' required')
            matches(v,actual[k],label+'.'+k)
    elif isinstance(expected,list):
        require(isinstance(actual,list) and len(actual)==len(expected),label+' length')
        for i,(a,b) in enumerate(zip(expected,actual)):matches(a,b,label+'['+str(i)+']')
    else:
        require(expected==actual and (type(expected)==type(actual) or type(expected) in (int,float) and type(actual) in (int,float)),
                label+' value','expected '+repr(expected)+', observed '+repr(actual))


class Runner:
    def __init__(self,base,f=None):
        self.base=base;self.fixture=deepcopy(f or fixture());self.tokens={};self.ops=[];self.replays={}
        require(http(base,'POST','/_test/reset',self.fixture)[0]==204,'R3 reset')
        self.state=model.initial(self.fixture,now())
        for u in self.fixture['users']:
            status,r=http(base,'POST','/auth/login',{'email':u['email'],'password':u['password']})
            require(status==200,'R3 login');self.tokens[u['handle']]=r['token']

    def run(self,operation,observe=False):
        op=deepcopy(operation);kind=op['kind'];user=op.get('user');q=op.get('query',{})
        path={'me':'/me','statement':'/statement','payment':'/payments','authorize':'/authorizations'}.get(kind)
        if kind in ('revisions','correction'):path='/payments/'+op['id']+('/revisions' if kind=='revisions' else '/corrections')
        if kind in ('capture','void'):path='/authorizations/'+op['id']+'/'+kind
        method='GET' if kind in ('me','statement','revisions') else 'POST'
        if q:path+='?'+op.get('raw_query',urllib.parse.urlencode(q))
        started=now()
        status,actual=http(self.base,method,path,op.get('body',{}) if method=='POST' else None,
                           token=self.tokens.get(user),key=op.get('key'))
        op['now']=now()
        if kind=='statement':
            op['snapshot_id']=actual.get('snapshot','@unissued')
            if status==200:require(isinstance(actual.get('snapshot'),str) and bool(actual['snapshot']),'R3 opaque snapshot')
        if kind=='correction':
            # Only server-owned recorded time enters the oracle. Amount/revision/reason do not.
            previous=self.state['revisions'].get(op['id'],[{'recorded_at':T0}])[-1]['recorded_at']
            fallback=(datetime.fromisoformat(previous)+timedelta(seconds=1)).isoformat()
            op['recorded_at']=actual.get('recorded_at',max(now(),fallback))
            if status==201:
                recorded=model.instant(op['recorded_at'])
                require(recorded>=model.instant(started)-Decimal('.001') and
                        recorded<=max(model.instant(op['now']),model.instant(previous)+Decimal('.001'))+Decimal('.001'),
                        'R3 server-assigned recorded time near request')
        if kind in ('payment','authorize','capture'):
            op['receipt']=actual if status==201 else {'payment_id':'@failed','created_at':started,'authorization_id':'@failed','expires_at':FUTURE}
        if kind in ('capture','void'):
            op['event_at']=actual.get('created_at') if kind=='capture' else actual.get('closed_at')
            if op['event_at'] is None:op['event_at']=started
        state,expected=model.transition(self.state,op)
        self.ops.append(operation)
        require(status==expected['status'],'R3 status '+kind,'expected '+str(expected['status'])+', observed '+str(status)+' '+str(actual.get('error',{}).get('code','')))
        matches(expected['body'],actual,'R3 '+kind+' user='+str(user)+' query='+json.dumps(q,sort_keys=True))
        if kind=='correction' and status in (200,201):
            ck=(user,op['id'],op['key'])
            if status==201:self.replays[ck]=deepcopy(actual)
            else:require(actual==self.replays[ck],'R3 exact correction replay')
        self.state=state
        if observe:self.observe()
        return actual

    def observe(self):
        # Explicit broad end avoids read-time truncation of the current second.
        for user in self.tokens:
            self.run({'kind':'me','user':user})
            self.run({'kind':'statement','user':user,'query':{'from':T0,'to':FUTURE,'limit':'200'}})
        sums={}
        for t in [T0,T1,T2,T3,T4,T5]:
            total=0
            for user in self.tokens:
                r=self.run({'kind':'me','user':user,'query':{'as_of':t}});total+=r['total']
            require(total==self.state['total'],'R3 historical conservation')
            sums[t]=total


def correction(pid='p_a',user='ada',revision=1,amount=300,effective=T1,key='correct',reason='correction'):
    return {'kind':'correction','id':pid,'user':user,'key':key,
            'body':{'expected_revision':revision,'amount':amount,'effective_at':effective,'reason':reason}}


def sequence(seed=42,steps=30):
    operations=[]
    for user in ['ada','bob','dee',None]:operations.append({'kind':'revisions','user':user,'id':'p_a'})
    for user in ['bob','dee',None]:operations.append(correction(user=user,key='role'))
    operations.append(correction(pid='missing',key='missing'))
    for key in [None,'','x'*256]:operations.append(correction(key=key))
    for field,values in [('expected_revision',[None,0,-1,1.5,True,'1']),('amount',[None,-1,1000000001,1.5,True,'1']),
                         ('reason',[None,'','x'*201,1]),('effective_at',[None,'','2020-01-01','2020-01-01T00:00:00',FUTURE])]:
        for v in values:
            op=correction(key='invalid');op['body'][field]=v;operations.append(op)
        op=correction(key='invalid');del op['body'][field];operations.append(op)
    operations += [correction(effective=T3,key='historical'),correction(amount=0,key='short'),correction(),
                   correction(),correction(revision=1,amount=350,key='stale'),
                   correction(revision=2,amount=320,effective=T0,key='second'),correction(),
                   correction(revision=3,amount=300,effective=T1,key='historical')]
    changed=correction();changed['body']['amount']=None;operations.append(changed)
    # Random proposed amounts/times/revisions; model derives funds/history failures.
    rng=random.Random(seed)
    for i in range(steps):
        pid=rng.choice(['p_a','p_b','p_c']);sender={'p_a':'ada','p_b':'bob','p_c':'cy'}[pid]
        operations.append(correction(pid,sender,rng.choice([1,2,3,4]),rng.choice([0,50,100,200,400,700]),
                                     rng.choice([T0,T1,T2,T3,T4]),'random-'+str(i)))
    return operations


def run_sequence(base,operations):
    r=Runner(base)
    for op in operations:r.run(op,observe=op['kind']=='correction')
    return r


def shrink(base,operations,label):
    result=list(operations);attempts=0
    # Single-deletion minimization, bounded to avoid unbounded expensive resets.
    i=0
    while i<len(result) and attempts<60:
        trial=result[:i]+result[i+1:];attempts+=1
        try:run_sequence(base,trial)
        except Mismatch as e:
            if e.label==label:result=trial;continue
        i+=1
    return result,attempts


def temporal_queries(r):
    for pid,p in r.state['payments'].items():
        history=r.run({'kind':'revisions','user':p['from_handle'],'id':pid})['revisions']
        for rev in history:
            at=rev['recorded_at']
            before=(datetime.fromisoformat(at)-timedelta(microseconds=1)).isoformat()
            for known in [before,at,FUTURE]:
                for user in [p['from_handle'],p['to_handle']]:
                    r.run({'kind':'me','user':user,'query':{'as_of':T3,'known_at':known}})
                    r.run({'kind':'statement','user':user,'query':{'from':T0,'to':T4,'known_at':known,'limit':'200'}})
    for field in ['as_of','known_at']:
        for v in ['', '2020-01-01','2020-01-01T00:00:00','2020-02-30T00:00:00Z','x']:
            r.run({'kind':'me','user':'ada','query':{field:v}})
    for field in ['from','to','known_at']:
        for v in ['', '2020-01-01','2020-01-01T00:00:00','x']:
            r.run({'kind':'statement','user':'ada','query':{field:v}})
    for q in [{'limit':'0'},{'limit':'201'},{'offset':'-1'},{'offset':'1e2'},{'limit':'1.0'}]:
        r.run({'kind':'statement','user':'ada','query':q})
    r.run({'kind':'me','user':'ada','query':{'as_of':'2020-01-02T02:30:00.000+02:30','known_at':FUTURE}})
    for field in ['as_of','known_at']:
        r.run({'kind':'me','user':'ada','query':{field:T2},'raw_query':field+'='+T2})
    for field in ['from','to','known_at']:
        r.run({'kind':'statement','user':'ada','query':{field:T2},'raw_query':field+'='+T2})


def snapshots(base):
    r=Runner(base)
    original=r.run({'kind':'statement','user':'ada','query':{'from':T0,'to':T3,'limit':'1'}})
    token=original['snapshot']
    default_token=r.run({'kind':'statement','user':'ada','query':{'limit':'1'}})['snapshot']
    r.run(correction(amount=300,effective=T0),observe=True)
    r.run({'kind':'payment','user':'ada','key':'new-payment','body':{'to_handle':'bob','amount':1}})
    for offset in ['0','1','2','999']:
        r.run({'kind':'statement','user':'ada','query':{'snapshot':token,'limit':'1','offset':offset,'unknown':'ignored'}})
        r.run({'kind':'statement','user':'ada','query':{'snapshot':default_token,'limit':'1','offset':offset}})
    for field in ['from','to','known_at']:
        r.run({'kind':'statement','user':'ada','query':{'snapshot':token,field:''}})
    r.run({'kind':'statement','user':'dee','query':{'snapshot':token}})
    r.run({'kind':'statement','user':'ada','query':{'snapshot':'not-a-token'}})
    new=Runner(base)
    new.run({'kind':'statement','user':'ada','query':{'snapshot':token}})


def historical_holds(base):
    f=fixture();f['payments']=[]
    for u in f['users']:u['balance']=300
    f['payments']=[{'id':'p_out','from_user_id':'u_ada','to_user_id':'u_bob','amount':200,'created_at':T4},
                   {'id':'p_in','from_user_id':'u_bob','to_user_id':'u_ada','amount':200,'created_at':T5}]
    f['authorizations']=[{'id':'a_old','from_user_id':'u_ada','to_user_id':'u_bob','amount':250,
                         'status':'open','created_at':T1,'expires_at':T3}]
    r=Runner(base,f)
    for t in [T0,T1,T2,T3,T4,T5]:
        for k in [T0,T1,T2,FUTURE]:
            r.run({'kind':'me','user':'ada','query':{'as_of':t,'known_at':k}})
    r.run(correction('p_out','ada',1,200,T2,'hold-overdraft'),observe=True)
    r.run(correction('p_out','ada',1,200,T3,'after-release'),observe=True)


def tied_boundaries(base):
    f=fixture();f['payments']=[
        {'id':'a_debit','from_user_id':'u_bob','to_user_id':'u_cy','amount':100,'created_at':T2},
        {'id':'z_credit','from_user_id':'u_ada','to_user_id':'u_bob','amount':100,'created_at':T1}]
    for u in f['users']:u['balance']={'ada':200,'bob':0,'cy':100,'dee':0}[u['handle']]
    r=Runner(base,f)
    r.run(correction('z_credit','ada',1,100,T2,'same-boundary'),observe=True)
    # Sorting a_debit before z_credit gives a negative intermediate statement entry,
    # but the combined effective-time boundary is0 and must be accepted.
    r.run({'kind':'statement','user':'bob','query':{'from':T0,'to':T3}})


def snapshot_roundtrip(base,second=None):
    r=Runner(base)
    token=r.run({'kind':'statement','user':'ada','query':{'from':T0,'to':T3,'limit':'1'}})['snapshot']
    r.run(correction(amount=300,effective=T0))
    status,export=http(base,'GET','/_test/export');require(status==200,'R3 snapshot export')
    exported_state=deepcopy(r.state)
    r.run(correction(revision=2,amount=350,effective=T1,key='post-export'))
    destination=second or base
    other=Runner(destination)
    stale=other.run({'kind':'statement','user':'ada','query':{'to':FUTURE}})['snapshot']
    require(http(destination,'POST','/_test/import',export)[0]==204,'R3 snapshot import')
    r.base=destination;r.state=exported_state
    for offset in ['0','1','999']:
        r.run({'kind':'statement','user':'ada','query':{'snapshot':token,'limit':'1','offset':offset}})
    r.run({'kind':'statement','user':'ada','query':{'snapshot':stale}})
    r.observe()


def lifecycle(base):
    r=Runner(base)
    a=r.run({'kind':'authorize','user':'ada','key':'hold','body':{'to_handle':'bob','amount':300}})
    aid=a['authorization_id'];hold=r.state['holds'][aid]
    # Separate seconds make known_at event-cutoff tests unambiguous under inherited precision.
    time.sleep(1.05)
    p=r.run({'kind':'capture','user':'bob','id':aid,'key':'partial','body':{'amount':100,'final':False}})
    time.sleep(1.05)
    closed=r.run({'kind':'void','user':'ada','id':aid,'body':{}})
    for t in [hold['created_at'],p['created_at'],closed['closed_at'],hold['expires_at']]:
        for k in [T0,hold['created_at'],p['created_at'],closed['closed_at'],FUTURE]:
            r.run({'kind':'me','user':'ada','query':{'as_of':t,'known_at':k}})
    r.run(correction(p['payment_id'],'ada',1,50,T1,'linked'))
    r.observe()


def immediate_lifecycle(base):
    """No sleeps: detect payment timestamp truncation before the releasing void."""
    for attempt in range(3):
        f=fixture();f['payments']=[]
        for u in f['users']:u['balance']=100
        r=Runner(base,f)
        a=r.run({'kind':'authorize','user':'ada','key':'immediate-hold','body':{'to_handle':'bob','amount':100}})
        aid=a['authorization_id'];created=r.state['holds'][aid]['created_at']
        released=r.run({'kind':'void','user':'ada','id':aid,'body':{}})
        p=r.run({'kind':'payment','user':'ada','key':'immediate-spend','body':{'to_handle':'bob','amount':100}})
        require(model.instant(created)<=model.instant(released['closed_at'])<=model.instant(p['created_at']),
                'R3 immediate lifecycle chronology', 'payment must not predate the releasing void')
        require(model.historical_valid(r.state,model.instant(now())), 'R3 immediate lifecycle historical available')
        for at in [created,released['closed_at'],p['created_at']]:
            view=r.run({'kind':'me','user':'ada','query':{'as_of':at}})
            require(view['total']>=0 and view['available']>=0,'R3 lifecycle nonnegative historical view')
        at_payment=r.run({'kind':'me','user':'ada','query':{'as_of':p['created_at']}})
        require(at_payment['total']==at_payment['available']==at_payment['held']==0,'R3 immediate payment view')
        status,snapshot=http(base,'GET','/_test/export');require(status==200,'R3 immediate lifecycle export')
        require(http(base,'POST','/_test/import',snapshot)[0]==204,'R3 immediate lifecycle own export imports')
        r.run({'kind':'me','user':'ada','query':{'as_of':p['created_at']}})


def reset_error(base):
    r=Runner(base);before=r.run({'kind':'statement','user':'ada','query':{'to':FUTURE}})
    f=fixture();f['payments'][0]['created_at']=FUTURE
    status,body=http(base,'POST','/_test/reset',f)
    require(status==422 and body['error']['code']=='validation_failed','R3 future seeded reset')
    r.run({'kind':'statement','user':'ada','query':{'snapshot':before['snapshot']}})
    r.observe()


def settlement_history(base):
    r=Runner(base)
    body={'transfers':[{'from_handle':'ada','to_handle':'bob','amount':1},
                       {'from_handle':'bob','to_handle':'cy','amount':1,'visibility':'private'}]}
    status,receipt=http(base,'POST','/settlements',body,token=r.tokens['ada'],key='linked-settlement')
    require(status==201,'R3 settlement setup')
    for supplied,p in zip(body['transfers'],receipt['payments']):
        expected={'payment_id':p['payment_id'],'from_handle':supplied['from_handle'],
            'to_handle':supplied['to_handle'],'from_user_id':'u_'+supplied['from_handle'],
            'to_user_id':'u_'+supplied['to_handle'],'amount':1,'note':'','visibility':supplied.get('visibility','public'),
            'currency':'EUR','created_at':receipt['committed_at'],'settlement_id':receipt['settlement_id'],
            'authorization_id':None,'request_id':None}
        matches(expected,p,'R3 settlement receipt')
        model.add_payment(r.state,expected)
        r.run({'kind':'revisions','user':supplied['from_handle'],'id':p['payment_id']})
        r.run(correction(p['payment_id'],supplied['from_handle'],1,0,T1,'linked'))
    r.observe()


def original_receipt(base):
    r=Runner(base);body={'to_handle':'bob','amount':10,'note':'immutable original','visibility':'private'}
    p=r.run({'kind':'payment','user':'ada','key':'original','body':body})
    r.run(correction(p['payment_id'],'ada',1,20,p['created_at'],'amend'),observe=True)
    status,replayed=http(base,'POST','/payments',body,token=r.tokens['ada'],key='original')
    require(status==200 and replayed==p,'R3 original payment replay immutable')
    status,feed=http(base,'GET','/activity',token=r.tokens['ada'])
    require(status==200,'R3 activity after correction')
    rows=[x for x in feed['payments'] if x['payment_id']==p['payment_id']]
    require(len(rows)==1 and rows[0]==p,'R3 original feed immutable')
    r.observe()


def upgrade(source,base,with_holds):
    f=fixture()
    require(http(source,'POST','/_test/reset',f)[0]==204,'R3 legacy reset')
    tokens={}
    for u in f['users']:
        status,logged=http(source,'POST','/auth/login',{'email':u['email'],'password':u['password']})
        require(status==200,'R3 legacy login');tokens[u['handle']]=logged['token']
    state=model.initial(f,now());a=None
    if with_holds:
        body={'to_handle':'bob','amount':300,'note':'upgrade hold','visibility':'private'}
        status,a=http(source,'POST','/authorizations',body,token=tokens['ada'],key='upgrade-hold')
        require(status==201,'R3 legacy hold')
        state,_=model.transition(state,{'kind':'authorize','user':'ada','now':now(),'body':body,'receipt':a})
        time.sleep(1.05)
        body={'amount':100,'final':False}
        status,capture=http(source,'POST','/authorizations/'+a['authorization_id']+'/capture',body,token=tokens['bob'],key='upgrade-capture')
        require(status==201,'R3 legacy partial capture')
        state,_=model.transition(state,{'kind':'capture','id':a['authorization_id'],'user':'bob','now':now(),
            'event_at':capture['created_at'],'body':body,'receipt':capture})
    status,export=http(source,'GET','/_test/export');require(status==200,'R3 legacy export')
    r=Runner(base);old=r.run({'kind':'statement','user':'ada','query':{'to':FUTURE}})['snapshot']
    require(http(base,'POST','/_test/import',export)[0]==204,'R3 legacy import')
    r.tokens=tokens;r.state=state
    r.observe()
    for pid,payment in r.state['payments'].items():r.run({'kind':'revisions','user':payment['from_handle'],'id':pid})
    # Import starts a new snapshot epoch according to the assigned snapshots contract.
    r.run({'kind':'statement','user':'ada','query':{'snapshot':old}})
    if a:
        for t in [a['created_at'],capture['created_at'],a['expires_at']]:
            for k in [a['created_at'],capture['created_at'],FUTURE]:
                r.run({'kind':'me','user':'ada','query':{'as_of':t,'known_at':k}})
        status,replay=http(base,'POST','/authorizations/'+a['authorization_id']+'/capture',{'amount':100,'final':False},token=tokens['bob'],key='upgrade-capture')
        require(status==200 and replay==capture,'R3 imported capture replay unchanged')
        r.run(correction(capture['payment_id'],'ada',1,50,T1,'linked-upgrade'))


def self_test():
    s=model.initial(fixture(),T5)
    require(s['opening']=={'ada':1000,'bob':0,'cy':0,'dee':1000},'R3 opening inference')
    op=correction(effective=T3);op.update(now=FUTURE,recorded_at='2026-01-01T00:00:00Z')
    _,r=model.transition(s,op);require(r['body']['error']['code']=='historical_overdraft','R3 effective overdraft')
    op=correction();op.update(now=FUTURE,recorded_at='2026-01-01T00:00:00Z')
    s,r=model.transition(s,op);require(r['status']==201,'R3 correction selftest')
    require(model.total_at(s,'ada',model.instant(T1))==700,'R3 latest balance')
    require(model.total_at(s,'ada',model.instant(T1),model.instant(T5))==600,'R3 original known balance')
    require(model.instant('2020-01-02T02:30:00+02:30')==model.instant(T1),'R3 offset equivalence')
    print('TEMPORAL MODEL SELF-TEST PASS')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base-url');p.add_argument('--self-test',action='store_true')
    p.add_argument('--seed',type=int,default=42);p.add_argument('--steps',type=int,default=30)
    p.add_argument('--no-shrink',action='store_true');p.add_argument('--replay',type=Path)
    p.add_argument('--stage1-url');p.add_argument('--stage2-url');p.add_argument('--second-url')
    a=p.parse_args()
    if a.self_test:self_test();return
    if not a.base_url:p.error('--base-url required')
    ops=json.loads(a.replay.read_text()) if a.replay else sequence(a.seed,a.steps)
    try:r=run_sequence(a.base_url,ops)
    except Mismatch as error:
        print('TEMPORAL DIFFERENTIAL FAIL '+str(error))
        reduced,attempts=(ops,0) if a.no_shrink else shrink(a.base_url,ops,error.label)
        path=Path(tempfile.mkdtemp(prefix='pocketful-temporal-'))/'reproduction.json'
        path.write_text(json.dumps(reduced,indent=2)+'\n')
        print('REPRO operations='+str(len(reduced))+' attempts='+str(attempts)+' file='+str(path));raise SystemExit(1)
    if not a.replay:
        try:
            temporal_queries(r);snapshots(a.base_url);tied_boundaries(a.base_url);snapshot_roundtrip(a.base_url,a.second_url)
            historical_holds(a.base_url);lifecycle(a.base_url);immediate_lifecycle(a.base_url)
            reset_error(a.base_url);settlement_history(a.base_url);original_receipt(a.base_url)
            if a.stage1_url:upgrade(a.stage1_url,a.base_url,False)
            if a.stage2_url:upgrade(a.stage2_url,a.base_url,True)
        except Mismatch as e:print('TEMPORAL CONTRACT FAIL '+str(e));raise SystemExit(1)
    print('TEMPORAL DIFFERENTIAL PASS operations='+str(len(ops))+' revisions=pass known-effective=pass snapshots=pass holds=pass stage1-import='+('pass' if a.stage1_url else 'NOT_RUN')+' stage2-import='+('pass' if a.stage2_url else 'NOT_RUN'))


if __name__=='__main__':main()
