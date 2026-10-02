#!/usr/bin/env python3
"""Observable temporal faults in discarded clean-copy containers.
Usage: python3 mutate_history.py CLEAN_STAGE_FOLDER INTERNAL_NETWORK SCRATCH
"""
import json
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.request

source, network, scratch = sys.argv[1:4]
scratch = pathlib.Path(scratch)
scratch.mkdir(parents=True, exist_ok=True)
check = pathlib.Path(__file__).with_name('history.py').resolve()
faults = [
    ('stale_revision', 'store.js', 'if (expected_revision !== last.revision)', 'if (false)'),
    ('historical_overdraft', 'store.js', 'if (!ledger.historyIsSound(this.s, u, override, Math.max(now, recMs)))', 'if (false)'),
    ('known_at', 'ledger.js', 'revs[i].recMs <= K', 'true'),
    ('snapshot_cutoff', 'ledger.js', 'revs[i].seq <= cutoff', 'true'),
    ('snapshot_owner', 'snapshots.js', 'snap.userId !== userId', 'false'),
    ('inclusive_boundary', 'ledger.js', 'if (e.t <= T)', 'if (e.t < T)'),
    ('original_receipt', 'store.js', 'revs.push(rev);', 'p.amount = amount; revs.push(rev);'),
]
results = []
for name, filename, old, new in faults:
    folder = scratch / name
    shutil.copytree(source, folder)
    path = folder / 'src' / filename
    code = path.read_text()
    if old not in code:
        raise RuntimeError('unmatched mutation anchor: '+name)
    path.write_text(code.replace(old, new))
    image = 'gatekeeper-history-mutant-'+name.replace('_','-')
    try:
        with (scratch/(name+'-build.log')).open('w') as log:
            subprocess.run(['docker','build','-t',image,str(folder)],stdout=log,stderr=log,check=True)
        subprocess.run(['docker','run','-d','--name',image,'--network',network,'--cpus','2','--memory','2g',image],stdout=subprocess.DEVNULL,check=True)
        ip = subprocess.check_output(['docker','inspect','--format','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',image],text=True).strip()
        url = 'http://'+ip+':8080'
        for _ in range(100):
            try:
                urllib.request.urlopen(url+'/health',timeout=1).close()
                break
            except Exception:
                time.sleep(.05)
        with (scratch/(name+'-check.log')).open('w') as log:
            result = subprocess.run([sys.executable,str(check),url],stdout=log,stderr=log,timeout=60)
        output = (scratch/(name+'-check.log')).read_text()
        assertions = [line for line in output.splitlines() if line.startswith('AssertionError:')]
        caught = result.returncode == 1 and bool(assertions)
        results.append({'fault':name,'exit':result.returncode,'caught':caught,'assertion':assertions[-1] if assertions else 'no semantic assertion'})
    finally:
        subprocess.run(['docker','rm','-f',image],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print(json.dumps({'planted':len(faults),'caught':sum(x['caught'] for x in results),'results':results}))
sys.exit(0 if all(x['caught'] for x in results) else 1)
