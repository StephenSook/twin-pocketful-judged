#!/usr/bin/env python3
"""Bounded source/dependency inventory; prints counts and paths, never values.

Usage: python3 integrity.py CANDIDATE_REPO PROVIDED_ROOT BASELINE_JSON
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys

repo, provided, baseline = map(pathlib.Path, sys.argv[1:4])
expected = json.loads(baseline.read_text())
changed = [name for name, digest in expected.items() if hashlib.sha256((provided / name).read_bytes()).hexdigest() != digest]
files = [repo / name for name in subprocess.check_output(['git', '-C', str(repo), 'ls-files'], text=True).splitlines()]
secret_patterns = [re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
                   re.compile(r'(?:ghp_|github_pat_|sk_live_)[A-Za-z0-9_]{20,}'),
                   re.compile(r'AKIA[A-Z0-9]{16}')]
secret_hits = [str(f.relative_to(repo)) for f in files if any(p.search(f.read_text(errors='ignore')) for p in secret_patterns)]
product = list((repo / 'stage-2/src').rglob('*.js'))
test_names = re.compile(r'pytest|test_sample|test_me_payments|harness|u_ada|u_bob')
branches = [str(f.relative_to(repo)) for f in product if test_names.search(f.read_text())]
package = json.loads((repo / 'stage-2/package.json').read_text())
dependencies = {k: package.get(k, {}) for k in ['dependencies', 'devDependencies', 'optionalDependencies']}
dependency_count = sum(len(v) for v in dependencies.values())
result = {'provided_files': len(expected), 'provided_changed': changed,
          'tracked_files_scanned': len(files), 'credential_pattern_hit_files': secret_hits,
          'product_files': len(product), 'check_identifier_hit_files': branches,
          'declared_package_dependencies': dependency_count,
          'advisory_audit': 'empty package inventory' if dependency_count == 0 else 'required'}
passed = not changed and not secret_hits and not branches and dependency_count == 0
result['result'] = 'PASS' if passed else 'FAIL'
print(json.dumps(result))
raise SystemExit(0 if passed else 1)
