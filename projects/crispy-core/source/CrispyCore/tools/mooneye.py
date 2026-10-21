#!/usr/bin/env python3
"""Run a named, bounded subset and retain every result; failures are not hidden."""
from pathlib import Path
import argparse,subprocess,json,time
p=argparse.ArgumentParser();p.add_argument('runner');p.add_argument('suite');p.add_argument('--output',default='build/crispy-core/mooneye-results.json');p.add_argument('--system',choices=['gb','gbc'],default='gb');a=p.parse_args()
root=Path(a.suite)/'acceptance'
paths=sorted(p for p in root.glob('*.gb') if not p.name.startswith('boot_'))+sorted((root/'instr').glob('*.gb'))+sorted((root/'timer').glob('*.gb'))
if a.system=='gbc': paths=[p for p in paths if '-GS.' not in p.name]
if not paths: raise SystemExit('No Mooneye ROMs found')
results=[]
for rom in paths:
 t=time.monotonic()
 try:
  r=subprocess.run([a.runner,str(rom),'--system',a.system,'--mooneye','3000000'],capture_output=True,text=True,timeout=20)
  row=dict(test=str(rom.relative_to(root)),status='pass' if r.returncode==0 else 'timeout' if r.returncode==3 else 'fail',detail=(r.stdout+r.stderr).strip(),seconds=round(time.monotonic()-t,3))
 except subprocess.TimeoutExpired: row=dict(test=str(rom.relative_to(root)),status='timeout',detail='20-second wall limit',seconds=20)
 results.append(row);print(row['status'].upper(),row['test'],flush=True)
output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(dict(suite=Path(a.suite).name,system=a.system,instructionLimit=3000000,scope='top-level non-boot acceptance, instr and timer; not the full suite',tests=results),indent=2))
summary={s:sum(r['status']==s for r in results) for s in ['pass','fail','timeout']};print('SUMMARY',summary,flush=True)
raise SystemExit(0 if summary['fail']==summary['timeout']==0 else 1)
