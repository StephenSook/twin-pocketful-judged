#!/usr/bin/env python3
"""One-command stage3 model acceptance; all URLs are destructive isolated targets."""
import argparse
from pathlib import Path
import subprocess
import sys

p=argparse.ArgumentParser(description=__doc__)
for name in ['base-url','second-url','stage1-url','stage2-url','stage3-url']:p.add_argument('--'+name,required=True)
p.add_argument('--no-shrink',action='store_true')
a=p.parse_args();root=Path(__file__).resolve().parent
commands=[
    [sys.executable,'-u',str(root/'driver.py'),'--base-url',a.base_url,'--second-url',a.second_url,
     '--stage1-url',a.stage1_url,'--steps','100'],
    [sys.executable,'-u',str(root/'temporal_driver.py'),'--base-url',a.base_url,
     '--second-url',a.second_url,'--stage1-url',a.stage1_url,'--stage2-url',a.stage2_url,'--steps','30'],
    [sys.executable,'-u',str(root/'refund_batch_driver.py'),'--base-url',a.base_url,
     '--second-url',a.second_url,'--stage1-url',a.stage1_url,'--stage2-url',a.stage2_url,'--stage3-url',a.stage3_url,'--steps','40']]
for command in commands:
    if a.no_shrink:command.append('--no-shrink')
    result=subprocess.run(command)
    if result.returncode:raise SystemExit(result.returncode)
print('STAGE4 MODEL SUITE PASS inherited=pass temporal=pass refunds-batches=pass three-legacy-imports=pass')
