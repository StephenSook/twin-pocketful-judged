#!/usr/bin/env python3
"""Run clean-image limits and cross-process restoration; no private outputs.

Usage: python3 environment.py IMAGE INTERNAL_NETWORK
"""
import importlib.util
import json
import pathlib
import subprocess
import sys
import time

IMAGE, NETWORK = sys.argv[1:3]
spec = importlib.util.spec_from_file_location('probe', pathlib.Path(__file__).with_name('probe.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def docker(*args):
    return subprocess.check_output(['docker', *args], stderr=subprocess.DEVNULL, text=True).strip()


def start(name):
    before = time.monotonic()
    docker('run', '-d', '--name', name, '--network', NETWORK, '--cpus', '2', '--memory', '2g', '-e', 'PORT=18080', IMAGE)
    ip = docker('inspect', '--format', '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', name)
    p.BASE = 'http://' + ip + ':18080'
    while True:
        try:
            status, value = p.call('GET', '/health')
            if status == 200 and value == {'status': 'ok'}:
                break
        except Exception:
            pass
        p.check(time.monotonic() - before < 60, 'startup under 60 seconds')
        time.sleep(.05)
    elapsed = time.monotonic() - before
    configuration = json.loads(docker('inspect', name))[0]
    p.check(configuration['HostConfig']['NanoCpus'] == 2000000000, 'two CPU limit')
    p.check(configuration['HostConfig']['Memory'] == 2147483648, '2 GiB limit')
    p.check(json.loads(docker('network', 'inspect', NETWORK))[0]['Internal'], 'outbound network disabled')
    return elapsed


names = ['gatekeeper-limits-source', 'gatekeeper-limits-target']
try:
    startup = start(names[0])
    tokens = p.seed(100)
    results = p.burst(lambda i: p.call('POST', '/auth/login', {'email': 'a@example.test', 'password': p.PASSWORD}))
    p.check(all(s == 200 for s, _ in results), '50 concurrent logins')
    status, receipt = p.call('POST', '/payments', {'to_handle': 'b', 'amount': 4}, tokens['a'], 'migration')
    p.check(status == 201, 'migration write')
    status, export = p.call('GET', '/_test/export')
    p.check(status == 200, 'migration export')
    users = export['state']['users']
    p.check(all(u['password_hash'].startswith('$argon2id$') and 'password' not in u for u in users), 'passwords hashed')
    p.check(len({u['password_hash'] for u in users}) == len(users), 'same password has unique salt')
    docker('rm', '-f', names[0])
    startup2 = start(names[1])
    destination_tokens = p.seed(999)
    p.check(p.call('POST', '/_test/import', export)[0] == 204, 'import after source destruction')
    p.check([p.balance(tokens[h]) for h in ['a', 'b', 'c']] == [96, 4, 0], 'restored old sessions and balances')
    p.check(p.call('GET', '/me', token=destination_tokens['a'])[0] == 401, 'destination sessions removed')
    status, replay = p.call('POST', '/payments', {'to_handle': 'b', 'amount': 4}, tokens['a'], 'migration')
    p.check(status == 200 and replay == receipt, 'cross-process exact retry')
    p.check(p.call('POST', '/auth/login', {'email': 'a@example.test', 'password': p.PASSWORD})[0] == 200, 'cross-process password login')
    print(json.dumps({'result': 'PASS', 'assertions': p.COUNT, 'startup_seconds': [round(startup, 4), round(startup2, 4)], 'max_request_seconds': round(p.MAX_LATENCY, 4), 'origin': 'plain HTTP on non-loopback container IP'}))
finally:
    for name in names:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
