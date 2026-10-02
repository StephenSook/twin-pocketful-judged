#!/usr/bin/env python3
"""Independent stage4 refund/batch witnesses atop the pure temporal oracle."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import random
import tempfile

from temporal_driver import Runner,fixture,correction,now,T0,T1,T2,T3,T4,T5,FUTURE,matches
from driver import http,require,Mismatch
import temporal_model as model


def item(pid,revision=1,amount=0,effective=T1):
    return {'payment_id':pid,'expected_revision':revision,'amount':amount,'effective_at':effective,'reason':'batch adjustment'}


def batch(items,key='batch',user='ada'):
    return {'kind':'batch','user':user,'key':key,'body':{'corrections':items}}


def refund(pid,amount,key='refund',user='bob'):
    return {'kind':'refund','id':pid,'user':user,'key':key,'body':{'amount':amount}}


def refund_cases(base):
    r=Runner(base)
    p=r.run({'kind':'payment','user':'ada','key':'original','body':{'to_handle':'bob','amount':400,'note':'  refund ☕ ','visibility':'private'}})
    pid=p['payment_id'];at=p['created_at']
    token=r.run({'kind':'statement','user':'ada','query':{'to':FUTURE}})['snapshot']
    for who in [None,'ada','cy']:r.run(refund(pid,1,'role',who))
    r.run(refund('missing',1,'missing'))
    for key in [None,'','x'*256]:r.run(refund(pid,1,key))
    for n in [None,True,'1',0,-1,1.5,1000000001]:r.run(refund(pid,n,'invalid'))
    missing=refund(pid,1,'invalid');missing['body']={};r.run(missing)
    first=r.run(refund(pid,100),observe=True)
    r.run(refund(pid,100));r.run(refund(pid,101))
    r.run(refund(first['payment_id'],1,'nested','ada'))
    r.run(correction(first['payment_id'],'bob',1,0,at,'immutable'))
    r.run(batch([item(first['payment_id'],1,0,at)],'immutable-refund'))
    r.run(correction(pid,'ada',1,50,at,'cap'))
    r.run(correction(pid,'ada',1,100,at,'cap'),observe=True)
    r.run(refund(pid,1,'cap-full'))
    r.run(correction(pid,'ada',2,200,at,'increase'),observe=True)
    r.run(refund(pid,100,'remainder'),observe=True)
    r.run(refund(pid,1,'over-cap'))
    r.run(refund(pid,100))
    r.run({'kind':'statement','user':'ada','query':{'snapshot':token}})
    status,replay=http(base,'POST','/payments',{'to_handle':'bob','amount':400,'note':'  refund ☕ ','visibility':'private'},token=r.tokens['ada'],key='original')
    require(status==200 and replay==p,'R4 original payment receipt immutable')
    # Funds are total minus holds, and a failed refund key remains reusable.
    r=Runner(base)
    a=r.run({'kind':'authorize','user':'bob','key':'held','body':{'to_handle':'cy','amount':200}})
    r.run(refund('p_a',1,'funds'))
    r.run({'kind':'void','user':'bob','id':a['authorization_id'],'body':{}})
    r.run(refund('p_a',1,'funds'),observe=True)
    r.run(batch([item('p_a',1,0)],'refund-cap'))


def settlement_fixture():
    f=fixture();f['payments']=[
        {'id':'s_a','from_user_id':'u_ada','to_user_id':'u_bob','amount':100,'created_at':T1,'settlement_id':'s_seed'},
        {'id':'s_b','from_user_id':'u_bob','to_user_id':'u_ada','amount':100,'created_at':T1,'settlement_id':'s_seed'}]
    for u in f['users']:u['balance']=0 if u['handle'] in ('ada','bob') else 100
    return f


def batch_cases(base):
    # Both reversals are affordable in aggregate although either alone is not.
    r=Runner(base,settlement_fixture())
    frozen=r.run({'kind':'statement','user':'ada','query':{'to':FUTURE}})['snapshot']
    all_items=[item('s_b'),item('s_a',effective='2020-01-02T01:00:00+01:00')]
    for who in [None,'bob','cy']:r.run(batch(all_items,'role',who))
    for key in [None,'','x'*256]:r.run(batch(all_items,key))
    for body in [{},{'corrections':None},{'corrections':[]},{'corrections':[None]},
                 {'corrections':[item('s_a')]*33},{'corrections':[item('s_a'),item('s_a')]}]:
        r.run({'kind':'batch','user':'ada','key':'shape','body':body})
    r.run(batch([item('s_a')],'partial'))
    r.run(batch([item('s_a'),item('missing')],'order'))
    r.run(batch([item('missing'),dict(item('s_a'),reason='')],'order'))
    r.run(batch([dict(item('s_a'),reason=''),item('missing')],'order'))
    r.run(batch([item('s_a',2),item('missing')],'order'))
    r.run(batch([item('s_a'),item('s_b',effective=T2)],'unequal'))
    successful=r.run(batch(all_items),observe=True)
    r.run(batch(all_items))
    r.run(batch([dict(all_items[0],amount=None),all_items[1]]))
    r.run(batch([item('s_a'),item('s_b')],'stale'))
    r.run({'kind':'statement','user':'ada','query':{'snapshot':frozen}})
    r.run(correction('s_a','ada',2,1,T1,'single-member'))
    for pid in ['s_a','s_b']:r.run({'kind':'revisions','user':'ada','id':pid})
    # Different ordinary targets may use different effective times; operator is not sender.
    r=Runner(base)
    r.run(batch([item('p_b',1,150,T2),item('p_a',1,350,T1)],'ordinary'),observe=True)
    r.run(batch([item('p_b',2,150,T0),item('p_a',2,350,T3)],'history'))
    r.run(batch([item('p_a',2,1000000000,T3)],'funds-before-history'))
    r.run(batch([item('p_a',2,350,T1)],'history'),observe=True)
    # Refunding a settlement member never changes the membership requirement.
    f=settlement_fixture()
    for u in f['users']:u['balance']=100
    r=Runner(base,f)
    r.run(refund('s_a',20,'settlement-refund'),observe=True)
    r.run(batch([item('s_a',1,10)],'cap-before-completeness'))
    r.run(batch([item('s_a',1,50)],'membership'))
    r.run(batch([item('s_a',1,50),item('s_b',1,50)],'membership'),observe=True)
    # Total stays nonnegative, but moving this debit into an old hold is forbidden.
    f=fixture()
    for u in f['users']:u['balance']=300
    f['payments']=[{'id':'p_out','from_user_id':'u_ada','to_user_id':'u_bob','amount':200,'created_at':T4},
                   {'id':'p_in','from_user_id':'u_bob','to_user_id':'u_ada','amount':200,'created_at':T5}]
    f['authorizations']=[{'id':'a_old','from_user_id':'u_ada','to_user_id':'u_bob','amount':250,
                         'status':'open','created_at':T1,'expires_at':T3}]
    r=Runner(base,f)
    r.run(batch([item('p_out',1,200,T2)],'historical-available'),observe=True)
    r.run(batch([item('p_out',1,200,T3)],'historical-available'),observe=True)
    return successful


def request_capture_targets(base):
    r=Runner(base)
    status,request=http(base,'POST','/requests',{'payer_handle':'ada','amount':100,'note':'request refund'},token=r.tokens['bob'],key='rq')
    require(status==201,'R4 request setup')
    status,p=http(base,'POST','/requests/'+request['request_id']+'/pay',{'visibility':'private'},token=r.tokens['ada'],key='rq-pay')
    require(status==201,'R4 request pay setup')
    model.add_payment(r.state,p)
    r.run(refund(p['payment_id'],50),observe=True)
    r.run(batch([item(p['payment_id'],1,80,p['created_at'])],'request-batch'),observe=True)
    status,requests=http(base,'GET','/requests',token=r.tokens['bob'])
    require(status==200 and next(x for x in requests['requests'] if x['request_id']==request['request_id'])['status']=='paid','R4 request never reopened')
    a=r.run({'kind':'authorize','user':'ada','key':'authorize','body':{'to_handle':'bob','amount':100,'visibility':'private'}})
    captured=r.run({'kind':'capture','user':'bob','id':a['authorization_id'],'key':'capture','body':{}})
    r.run(refund(captured['payment_id'],100,'capture-refund'),observe=True)
    r.run(batch([item(captured['payment_id'],1,0,captured['created_at'])],'immutable'))
    status,auths=http(base,'GET','/authorizations',token=r.tokens['ada'])
    saved=next(x for x in auths['authorizations'] if x['authorization_id']==a['authorization_id'])
    require(status==200 and saved['status']=='captured' and saved['remaining_amount']==0,'R4 authorization never reopened')


def replay_sequence(base,ops):
    r=Runner(base)
    for operation in ops:r.run(operation,observe=True)
    return r


def reduce_sequence(base,ops,label):
    reduced=list(ops);i=0;attempts=0
    while i<len(reduced) and attempts<60:
        trial=reduced[:i]+reduced[i+1:];attempts+=1
        try:replay_sequence(base,trial)
        except Mismatch as error:
            if error.label==label:reduced=trial;continue
        i+=1
    return reduced,attempts


def random_sequence(base,seed,steps,no_shrink=False):
    r=Runner(base);rng=random.Random(seed);ops=[]
    for i in range(steps):
        pid=rng.choice(['p_a','p_b','p_c']);p=r.state['payments'][pid]
        if rng.randrange(2):
            operation=refund(pid,rng.choice([1,10,50,100,300]),'random-refund-'+str(i),p['to_handle'])
        else:
            targets=rng.sample(['p_a','p_b','p_c'],rng.choice([1,2,3]))
            entries=[item(t,r.state['revisions'][t][-1]['revision'],rng.choice([0,50,100,200,400]),rng.choice([T1,T2,T3])) for t in targets]
            operation=batch(entries,'random-batch-'+str(i))
        ops.append(operation)
        try:
            response=r.run(operation,observe=True)
            if 'error' not in response:r.run(operation)
        except Mismatch as e:
            reduced,attempts=(ops,0) if no_shrink else reduce_sequence(base,ops,e.label)
            path=Path(tempfile.mkdtemp(prefix='pocketful-stage4-'))/'reproduction.json'
            path.write_text(json.dumps(reduced,indent=2)+'\n')
            print('R4 REPRO operations='+str(len(reduced))+' shrink_attempts='+str(attempts)+' file='+str(path));raise
    return r


def own_roundtrip(r,second=None):
    require({'refund','batch'}.issubset({k[1] for k in r.replays}), 'R4 roundtrip contains refunds and batches')
    token=r.run({'kind':'statement','user':'ada','query':{'to':FUTURE}})['snapshot']
    status,export=http(r.base,'GET','/_test/export');require(status==200,'R4 state export')
    target=second or r.base
    destination=Runner(target)
    require(http(target,'POST','/_test/import',export)[0]==204,'R4 refunds/batches state import')
    require(http(target,'GET','/me',token=destination.tokens['ada'])[0]==401,'R4 import replaces credentials')
    r.base=target
    r.observe()
    r.run({'kind':'statement','user':'ada','query':{'snapshot':token}})
    for operation in list(r.ops):
        if operation['kind'] not in ('refund','batch'):continue
        ck=(operation['user'],operation['kind'],operation.get('id'),operation.get('key'))
        if ck in r.replays:r.run(operation)


def migration(source,base,stage):
    # Sources are real frozen services; no product source or opaque state inspection.
    f=fixture();f['payments']=[]
    for u in f['users']:u['balance']=1000
    require(http(source,'POST','/_test/reset',f)[0]==204,'R4 legacy reset')
    tokens={}
    for u in f['users']:
        status,x=http(source,'POST','/auth/login',{'email':u['email'],'password':u['password']})
        require(status==200,'R4 legacy login');tokens[u['handle']]=x['token']
    settlement_body={'transfers':[{'from_handle':'ada','to_handle':'bob','amount':100},
        {'from_handle':'bob','to_handle':'cy','amount':50}]}
    status,settlement=http(source,'POST','/settlements',settlement_body,token=tokens['ada'],key='legacy-settlement')
    require(status==201,'R4 legacy settlement')
    status,p=http(source,'POST','/payments',{'to_handle':'bob','amount':100},token=tokens['ada'],key='legacy-payment')
    require(status==201,'R4 legacy payment');old_snapshot=None;old_revision=None
    if stage==3:
        status,old_snapshot=http(source,'GET','/statement?to='+urllib_quote(FUTURE),token=tokens['ada'])
        require(status==200,'R4 legacy snapshot')
        status,old_revision=http(source,'POST','/payments/'+p['payment_id']+'/corrections',
            {'expected_revision':1,'amount':80,'effective_at':p['created_at'],'reason':'legacy correction'},token=tokens['ada'],key='legacy-correction')
        require(status==201,'R4 legacy correction')
    status,export=http(source,'GET','/_test/export');require(status==200,'R4 legacy export')
    require(http(base,'POST','/_test/import',export)[0]==204,'R4 legacy import')
    if old_snapshot:
        status,page=http(base,'GET','/statement?snapshot='+urllib_quote(old_snapshot['snapshot']),token=tokens['ada'])
        require(status==200 and page==old_snapshot,'R4 legacy snapshot retained')
        status,revisions=http(base,'GET','/payments/'+p['payment_id']+'/revisions',token=tokens['ada'])
        require(status==200,'R4 legacy correction retained')
        matches(old_revision,revisions['revisions'][-1],'R4 legacy correction fields retained')
        for revision in revisions['revisions']:
            matches({'correction_batch_id':None},revision,'S4-3 imported ordinary revision link')
        status,replayed_revision=http(base,'POST','/payments/'+p['payment_id']+'/corrections',
            {'expected_revision':1,'amount':80,'effective_at':p['created_at'],'reason':'legacy correction'},token=tokens['ada'],key='legacy-correction')
        require(status==200 and replayed_revision==old_revision,'R4 legacy correction replay exact')
    status,partial=http(base,'POST','/correction-batches',{'corrections':[item(settlement['payments'][0]['payment_id'],1,0,settlement['committed_at'])]},token=tokens['ada'],key='legacy-batch')
    require(status==422 and partial['error']['code']=='incomplete_settlement','R4 legacy settlement membership')
    entries=[item(x['payment_id'],1,0,settlement['committed_at']) for x in settlement['payments']]
    require(http(base,'POST','/correction-batches',{'corrections':entries},token=tokens['ada'],key='legacy-batch')[0]==201,'R4 legacy batch correctable')
    status,refunded=http(base,'POST','/payments/'+p['payment_id']+'/refunds',{'amount':50},token=tokens['bob'],key='legacy-refund')
    require(status==201 and refunded['refund_of']==p['payment_id'],'R4 legacy refundable')
    status,replay=http(base,'POST','/payments',{'to_handle':'bob','amount':100},token=tokens['ada'],key='legacy-payment')
    require(status==200 and replay==p,'R4 legacy original retry')
    status,replay=http(base,'POST','/settlements',settlement_body,token=tokens['ada'],key='legacy-settlement')
    require(status==200 and replay==settlement,'R4 legacy settlement retry after batch')


def urllib_quote(value):
    from urllib.parse import quote
    return quote(value,safe='')


def self_test():
    s=model.initial(settlement_fixture(),T5)
    op=batch([item('s_a'),item('s_b')]);op.update(now=FUTURE,recorded_at='2026-01-01T00:00:00Z',batch_id='b_test')
    s,result=model.transition(s,op)
    require(result['status']==201 and len(result['body']['revisions'])==2,'R4 combined-affordability oracle')
    print('REFUND BATCH MODEL SELF-TEST PASS')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base-url');p.add_argument('--self-test',action='store_true')
    for stage in (1,2,3):p.add_argument('--stage'+str(stage)+'-url')
    p.add_argument('--seed',type=int,default=2026);p.add_argument('--steps',type=int,default=40)
    p.add_argument('--no-shrink',action='store_true');p.add_argument('--replay',type=Path)
    p.add_argument('--second-url')
    a=p.parse_args()
    if a.self_test:self_test();return
    if not a.base_url:p.error('--base-url required')
    if a.replay:
        replay_sequence(a.base_url,json.loads(a.replay.read_text()));print('REFUND BATCH REPLAY PASS');return
    try:
        refund_cases(a.base_url);batch_cases(a.base_url);request_capture_targets(a.base_url)
        r=random_sequence(a.base_url,a.seed,a.steps,a.no_shrink);own_roundtrip(r,a.second_url)
        for stage in (1,2,3):
            source=getattr(a,'stage'+str(stage)+'_url')
            if source:migration(source,a.base_url,stage)
    except Mismatch as e:print('REFUND BATCH FAIL '+str(e));raise SystemExit(1)
    print('REFUND BATCH PASS random_operations='+str(a.steps)+' refunds=pass batches=pass precedence=pass state-import=pass imports='+str(sum(bool(getattr(a,'stage'+str(x)+'_url')) for x in (1,2,3)))+'/3')


if __name__=='__main__':main()
