#!/usr/bin/env python3
"""Plant observable faults in disposable copies; run independent HTTP probes.

Usage: python3 mutate.py CLEAN_STAGE_FOLDER INTERNAL_NETWORK SCRATCH_DIRECTORY
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
probe = pathlib.Path(__file__).with_name('probe.py').resolve()
faults = [
    ('overdraft', 'if (next < 0n)', 'if (false)'),
    ('credit', 'user.balance = next;', 'user.balance = Math.min(next, user.balance);'),
    ('idempotency', 'const prior = this.s.idem.get(scope);', 'const prior = null;'),
    ('request_guard', "if (r.status !== 'pending')", 'if (false)'),
    ('private_feed', "if (p.visibility !== 'public' && p.from_user_id !== caller.id && p.to_user_id !== caller.id) continue;", 'if (false) continue;'),
]
results = []
for name, old, new in faults:
    folder = scratch / name
    shutil.copytree(source, folder)
    file = folder / 'src/store.js'
    code = file.read_text()
    if old not in code:
        raise RuntimeError('mutation source not found: ' + name)
    file.write_text(code.replace(old, new))
    image = 'gatekeeper-mutant-' + name.replace('_', '-')
    try:
        with (scratch / (name + '-build.log')).open('w') as log:
            subprocess.run(['docker', 'build', '-t', image, str(folder)], stdout=log, stderr=log, check=True)
        subprocess.run(['docker', 'run', '-d', '--name', image, '--network', network, '--cpus', '2', '--memory', '2g', image], stdout=subprocess.DEVNULL, check=True)
        ip = subprocess.check_output(['docker', 'inspect', '--format', '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', image], text=True).strip()
        url = 'http://' + ip + ':8080'
        for attempt in range(100):
            try:
                urllib.request.urlopen(url + '/health', timeout=1).close()
                break
            except Exception:
                time.sleep(.05)
        with (scratch / (name + '-probe.log')).open('w') as log:
            run = subprocess.run([sys.executable, str(probe), url], stdout=log, stderr=log, timeout=60)
        output = json.loads((scratch / (name + '-probe.log')).read_text())
        caught = run.returncode == 1 and output.get('result') == 'FAIL' and output.get('check') not in ['TimeoutError', 'URLError', 'HTTPError']
        results.append({'fault': name, 'caught': caught, 'exit': run.returncode, 'check': output.get('check')})
    finally:
        subprocess.run(['docker', 'rm', '-f', image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(json.dumps({'planted': len(faults), 'caught': sum(r['caught'] for r in results), 'results': results}))
sys.exit(0 if all(r['caught'] for r in results) else 1)
