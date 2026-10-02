#!/usr/bin/env python3
"""Plant observable refund/batch faults in disposable clean-copy containers."""
import json,pathlib,shutil,subprocess,sys,time,urllib.request
source,network,scratch=sys.argv[1:4];scratch=pathlib.Path(scratch);scratch.mkdir(parents=True,exist_ok=True)
faults=[
 ('refund_cap','store.js','if ((this.s.refundedTotal.get(id) || 0) + amount > current)','if (false)'),
 ('refund_target','store.js','if (target.refund_of)','if (false)'),
 ('refund_direction','store.js','if (target.to_user_id !== caller.id)','if (false)'),
 ('correction_refund_floor','store.js','if (amount < (this.s.refundedTotal.get(id) || 0))','if (false)'),
 ('settlement_complete','store.js','if (!this.s.settlementMembers.get(id).every((m) => included.has(m)))','if (false)'),
 ('settlement_instant','store.js','if (!members.every((c) => same(c.effective_at, members[0].effective_at)))','if (false)'),
 ('refund_note_import','snapshot.js',"if (p.note !== target.note || p.visibility !== target.visibility)","if (p.visibility !== target.visibility)"),
]
results=[]
for name,file,old,new in faults:
 folder=scratch/name;shutil.copytree(source,folder);path=folder/'src'/file;code=path.read_text()
 if old not in code:raise RuntimeError('unmatched mutation anchor: '+name)
 path.write_text(code.replace(old,new));image='gatekeeper-s4-mutant-'+name.replace('_','-')
 try:
  with (scratch/(name+'-build.log')).open('w') as log:subprocess.run(['docker','build','-t',image,str(folder)],stdout=log,stderr=log,check=True)
  subprocess.run(['docker','run','-d','--name',image,'--network',network,'--cpus','2','--memory','2g',image],stdout=subprocess.DEVNULL,check=True)
  ip=subprocess.check_output(['docker','inspect','--format','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',image],text=True).strip();url='http://'+ip+':8080'
  for _ in range(100):
   try:urllib.request.urlopen(url+'/health',timeout=1).close();break
   except Exception:time.sleep(.05)
  check=pathlib.Path(__file__).with_name('refund_batch_import.py' if name.endswith('_import') else 'refund_batches.py')
  with (scratch/(name+'-check.log')).open('w') as log:result=subprocess.run([sys.executable,str(check),url],stdout=log,stderr=log,timeout=60)
  report=json.loads((scratch/(name+'-check.log')).read_text().splitlines()[-1]);assertion=report.get('check') or report.get('failed_cases')
  caught=result.returncode==1 and report.get('result')=='FAIL' and bool(assertion) and assertion not in ['TimeoutError','URLError','KeyError','TypeError']
  results.append({'fault':name,'exit':result.returncode,'caught':caught,'assertion':assertion})
 finally:subprocess.run(['docker','rm','-f',image],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print(json.dumps({'planted':len(faults),'caught':sum(x['caught'] for x in results),'results':results}))
sys.exit(0 if all(x['caught'] for x in results) else 1)
