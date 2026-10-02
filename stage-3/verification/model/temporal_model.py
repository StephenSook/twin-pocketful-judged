"""Pure, deliberately slow stage3 temporal oracle. No clock, I/O or product imports.

Operation inputs supply server-owned IDs and event instants as nondeterministic values;
all financial amounts, selection, authorization and state transitions are model-derived.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
import re

from model import Fault, fail, canonical


def instant(value):
    if not isinstance(value, str):
        fail(422, 'validation_failed')
    m = re.fullmatch(r'(\d{4}-\d\d-\d\d)[Tt](\d\d:\d\d:\d\d)(\.\d+)?([Zz]|[+-]\d\d:\d\d)', value)
    if not m:
        fail(422, 'validation_failed')
    try:
        base = datetime.fromisoformat(m[1] + 'T' + m[2]).replace(tzinfo=timezone.utc)
        off = m[4]
        seconds = 0
        if off.lower() != 'z':
            hours, minutes = int(off[1:3]), int(off[4:6])
            if hours > 23 or minutes > 59:
                raise ValueError()
            seconds = (hours * 3600 + minutes * 60) * (1 if off[0] == '+' else -1)
        return Decimal(int(base.timestamp()) - seconds) + Decimal(m[3] or '0')
    except (ValueError, OverflowError):
        fail(422, 'validation_failed')


def initial(fixture, reset_at):
    users = {u['handle']:deepcopy(u) for u in fixture['users']}
    by_id = {u['id']:h for h,u in users.items()}
    s = {'users':users,'opening':{h:u['balance'] for h,u in users.items()},
         'payments':{},'revisions':{},'holds':{},'keys':{},'snapshots':{},
         'currency':fixture['currency'],'minor_units':fixture['minor_units'],
         'total':sum(u['balance'] for u in users.values())}
    for p in fixture.get('payments', []):
        a,b = by_id[p['from_user_id']],by_id[p['to_user_id']]
        when = p.get('created_at',reset_at)
        receipt = {'payment_id':p['id'],'from_user_id':p['from_user_id'],'to_user_id':p['to_user_id'],
            'from_handle':a,'to_handle':b,'amount':p['amount'],'currency':s['currency'],
            'note':p.get('note',''),'visibility':p.get('visibility','public'),'created_at':when,
            'request_id':p.get('request_id'),'settlement_id':p.get('settlement_id'),
            'authorization_id':p.get('authorization_id')}
        add_payment(s,receipt)
        s['opening'][a] += p['amount']
        s['opening'][b] -= p['amount']
    for a in fixture.get('authorizations', []):
        if a['status'] == 'open':
            s['holds'][a['id']] = {'from_handle':by_id[a['from_user_id']],
                'to_handle':by_id[a['to_user_id']], 'amount':a['amount'],
                'created_at':a.get('created_at',reset_at),'expires_at':a['expires_at'],
                'note':a.get('note',''),'visibility':a.get('visibility','public'),'events':[]}
    return s


def add_payment(s,p):
    pid=p['payment_id'];s['payments'][pid]=deepcopy(p)
    s['revisions'][pid]=[{'payment_id':pid,'revision':1,'amount':p['amount'],
        'effective_at':p['created_at'],'recorded_at':p['created_at'],'reason':''}]


def selected(s,known=None):
    result=[]
    for pid,history in s['revisions'].items():
        eligible=[r for r in history if known is None or instant(r['recorded_at']) <= known]
        if eligible:
            result.append((s['payments'][pid],eligible[-1]))
    return result


def total_at(s,user,at,known=None,inclusive=True):
    total=s['opening'][user]
    for p,r in selected(s,known):
        t=instant(r['effective_at'])
        if t < at or inclusive and t == at:
            if p['from_handle']==user:total-=r['amount']
            if p['to_handle']==user:total+=r['amount']
    return total


def held_at(s,user,at,known=None):
    held=0
    for a in s['holds'].values():
        created=instant(a['created_at'])
        if a['from_handle']!=user or created>at or known is not None and created>known:
            continue
        # Expiry is predictable from creation even when known precedes the deadline.
        if at>=instant(a['expires_at']):continue
        remaining=a['amount']
        for e in a['events']:
            t=instant(e['at'])
            if t<=at and (known is None or t<=known):
                remaining=0 if e['final'] else remaining-e['amount']
        held+=remaining
    return held


def historical_valid(s,now):
    boundaries={instant(r['effective_at']) for _,r in selected(s)}
    for a in s['holds'].values():
        boundaries|={instant(a['created_at']),instant(a['expires_at'])}
        boundaries|={instant(e['at']) for e in a['events']}
    for t in sorted(x for x in boundaries if x<=now):
        for user in s['users']:
            total=total_at(s,user,t)
            if total<0 or total-held_at(s,user,t)<0:return False
    return True


def page(full,q):
    parsed={}
    for name,default,low,high in [('limit','50',1,200),('offset','0',0,None)]:
        raw=q.get(name,default)
        if not isinstance(raw,str) or not re.fullmatch('[0-9]+',raw):fail(422,'validation_failed')
        n=int(raw)
        if n<low or high is not None and n>high:fail(422,'validation_failed')
        parsed[name]=n
    result=deepcopy(full);offset,limit=parsed['offset'],parsed['limit']
    result['entries']=full['entries'][offset:offset+limit]
    result['has_more']=offset+limit<len(full['entries'])
    return result


def statement(s,user,q,now,token):
    known=instant(q['known_at']) if 'known_at' in q else None
    start=instant(q['from']) if 'from' in q else Decimal('-Infinity')
    end=instant(q['to']) if 'to' in q else now
    rows=[(p,r) for p,r in selected(s,known) if user in (p['from_handle'],p['to_handle'])]
    rows.sort(key=lambda pr:(instant(pr[1]['effective_at']),pr[0]['payment_id']))
    opening=total_at(s,user,start,known,inclusive=False)
    closing=total_at(s,user,end,known,inclusive=False)
    balance=opening;entries=[]
    for p,r in rows:
        if start<=instant(r['effective_at'])<end:
            delta=r['amount']*(1 if p['to_handle']==user else -1)
            balance+=delta
            payment=deepcopy(p);payment['amount']=r['amount']
            entries.append({'payment':payment,'delta':delta,'balance_after':balance,
                'revision':r['revision'],'effective_at':r['effective_at'],'recorded_at':r['recorded_at']})
    full={'opening_balance':opening,'closing_balance':closing,'entries':entries,'snapshot':token}
    if 'known_at' in q:full['known_at']=q['known_at']
    return full


def transition(state,op):
    s=deepcopy(state)
    try:
        status,body=execute(s,op)
        return s,{'status':status,'body':deepcopy(body)}
    except Fault as error:
        return deepcopy(state),{'status':error.status,'body':{'error':{'code':error.code}}}


def execute(s,op):
    user=op.get('user');now=instant(op['now']);kind=op['kind']
    if user not in s['users']:fail(401,'unauthenticated')
    q=op.get('query',{});body=op.get('body',{})
    if kind=='me':
        at=instant(q['as_of']) if 'as_of' in q else now
        known=instant(q['known_at']) if 'known_at' in q else None
        total=total_at(s,user,at,known);held=held_at(s,user,at,known)
        u=s['users'][user]
        result={'user_id':u['id'],'display_name':u['display_name'],'handle':user,
            'balance':total,'total':total,'held':held,'available':total-held,
            'currency':s['currency'],'minor_units':s['minor_units']}
        for k in ('as_of','known_at'):
            if k in q:result[k]=q[k]
        return 200,result
    if kind=='statement':
        if 'snapshot' in q:
            if any(k in q for k in ('from','to','known_at')):fail(422,'validation_failed')
            token=q['snapshot']
            if token not in s['snapshots'] or s['snapshots'][token][0]!=user:fail(404,'not_found')
            return 200,page(s['snapshots'][token][1],q)
        token=op['snapshot_id'];full=statement(s,user,q,now,token)
        result=page(full,q);s['snapshots'][token]=(user,full)
        return 200,result
    if kind=='revisions':
        pid=op['id'];p=s['payments'].get(pid)
        if not p or user not in (p['from_handle'],p['to_handle']):fail(404,'not_found')
        return 200,{'revisions':s['revisions'][pid]}
    if kind=='correction':
        pid=op['id'];key=op.get('key')
        if key is None or key=='':fail(400,'missing_idempotency_key')
        if len(key)>255:fail(422,'validation_failed')
        ck=(user,pid,key);parsed=json.dumps(canonical(body),sort_keys=True)
        if ck in s['keys']:
            old,result=s['keys'][ck]
            if old!=parsed:fail(409,'idempotency_key_reuse')
            return 200,result
        p=s['payments'].get(pid)
        if p is None:fail(404,'not_found')
        if user!=p['from_handle']:fail(403,'forbidden')
        if p['settlement_id'] or p['authorization_id']:fail(422,'linked_payment_immutable')
        for field,low,high in [('expected_revision',1,None),('amount',0,1000000000)]:
            n=body.get(field)
            if type(n) not in (int,float) or n!=int(n) or n<low or high is not None and n>high:fail(422,'validation_failed')
        reason=body.get('reason')
        if not isinstance(reason,str) or not 1<=len(reason)<=200:fail(422,'validation_failed')
        effective=instant(body.get('effective_at'))
        if effective>now:fail(422,'validation_failed')
        history=s['revisions'][pid];previous=history[-1]
        if body['expected_revision']!=previous['revision']:fail(409,'stale_revision')
        difference=int(body['amount'])-previous['amount']
        debited=p['from_handle'] if difference>=0 else p['to_handle']
        if total_at(s,debited,now)-held_at(s,debited,now)<abs(difference):fail(409,'insufficient_funds')
        recorded=op['recorded_at']
        assert instant(recorded)>instant(previous['recorded_at'])
        result={'payment_id':pid,'revision':previous['revision']+1,'amount':int(body['amount']),
            'effective_at':body['effective_at'],'recorded_at':recorded,'reason':reason}
        history.append(result)
        if not historical_valid(s,now):fail(409,'historical_overdraft')
        s['keys'][ck]=(parsed,deepcopy(result))
        return 201,result
    if kind=='payment':
        p=op['receipt'];n=body['amount'];recipient=body['to_handle']
        if total_at(s,user,now)-held_at(s,user,now)<n:fail(409,'insufficient_funds')
        expected={'payment_id':p['payment_id'],'created_at':p['created_at'],
            'from_handle':user,'to_handle':recipient,'from_user_id':s['users'][user]['id'],
            'to_user_id':s['users'][recipient]['id'],'amount':n,'currency':s['currency'],
            'note':body.get('note',''),'visibility':body.get('visibility','public'),
            'request_id':None,'settlement_id':None,'authorization_id':None}
        add_payment(s,expected);return 201,expected
    if kind=='authorize':
        a=op['receipt'];n=body['amount'];recipient=body['to_handle']
        if total_at(s,user,now)-held_at(s,user,now)<n:fail(409,'insufficient_funds')
        s['holds'][a['authorization_id']]={'from_handle':user,'to_handle':recipient,'amount':n,
            'created_at':a['created_at'],'expires_at':a['expires_at'],'note':body.get('note',''),
            'visibility':body.get('visibility','public'),'events':[]}
        return 201,{'authorization_id':a['authorization_id'],'amount':n,'closed_at':None}
    if kind in ('capture','void'):
        aid=op['id'];a=s['holds'][aid];at=op['event_at']
        if user!=a['to_handle' if kind=='capture' else 'from_handle']:fail(403,'forbidden')
        if kind=='void':
            a['events'].append({'at':at,'amount':0,'final':True})
            return 200,{'authorization_id':aid,'status':'voided','closed_at':at,'remaining_amount':0}
        remaining=a['amount']
        for e in a['events']:remaining=0 if e['final'] else remaining-e['amount']
        n=body.get('amount',remaining);final=body.get('final',True) or n==remaining
        a['events'].append({'at':at,'amount':n,'final':final})
        p=op['receipt'];expected={'payment_id':p['payment_id'],'created_at':at,'from_handle':a['from_handle'],
            'to_handle':a['to_handle'],'from_user_id':s['users'][a['from_handle']]['id'],
            'to_user_id':s['users'][a['to_handle']]['id'],'amount':n,'currency':s['currency'],
            'note':a['note'],'visibility':a['visibility'],'authorization_id':aid,'request_id':None,'settlement_id':None}
        add_payment(s,expected);return 201,expected
    raise AssertionError('unknown temporal operation '+kind)
